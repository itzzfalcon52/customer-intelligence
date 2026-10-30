"""Autonomy settings, guardrails, the monitoring schedule and the digest.

Autonomy levels decide what a scheduled cycle may do on its own:
- observe: re-score with the active model, check drift and realized performance, write a digest;
- recommend: also list the accounts to review first in the digest;
- act_with_approval: also propose retraining in the Inbox when monitoring raises an alert.
Nothing at any level contacts customers, and every proposal waits for a person.

Guardrails are enforced in backend code: a kill switch (pauses AI calls, cycles and proposals),
a daily AI token budget and a daily proposal quota.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import httpx
from sqlalchemy import func
from sqlmodel import Session, col, select

from customer_intelligence.core.config import Settings
from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.models.operations import DigestItem
from customer_intelligence.models.trace import AgentTrace
from customer_intelligence.models.workspace import PendingAction, WorkspaceFact
from customer_intelligence.schemas.operations import (
    AutonomySettings,
    AutonomyUpdate,
    Schedule,
    ScheduleUpdate,
)

AUTONOMY = "autonomy"
SCHEDULE = "schedule"
LEVELS = ("observe", "recommend", "act_with_approval")
# Tests replace this with httpx.MockTransport; production uses the network.
transport: httpx.BaseTransport | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _fact(session: Session, key: str) -> dict:
    fact = session.get(WorkspaceFact, key)
    return dict(fact.value) if fact else {}


def _store(session: Session, key: str, value: dict) -> None:
    fact = session.get(WorkspaceFact, key)
    if fact is None:
        fact = WorkspaceFact(key=key, value=value, source="user")
    else:
        fact.value, fact.source, fact.updated_at = value, "user", _now()
    session.add(fact)
    session.commit()


# ------------------------------------------------------------------ settings and guardrails


def read_autonomy(session: Session) -> AutonomySettings:
    stored = _fact(session, AUTONOMY)
    stored.pop("slack_ciphertext", None)
    return AutonomySettings.model_validate(
        {**stored, "slack_connected": bool(_fact(session, AUTONOMY).get("slack_ciphertext"))}
    )


def update_autonomy(
    session: Session, settings: Settings, update: AutonomyUpdate
) -> AutonomySettings:
    slack_url = update.slack_webhook_url
    value = update.model_dump(exclude={"slack_connected", "slack_webhook_url"})
    previous = _fact(session, AUTONOMY)
    if slack_url == "":
        value["slack_ciphertext"] = None
    elif slack_url:
        if not slack_url.startswith("https://hooks.slack.com/"):
            raise WorkflowError("Use a Slack incoming-webhook URL (https://hooks.slack.com/...).")
        from customer_intelligence.services.connectors import _fernet

        value["slack_ciphertext"] = _fernet(settings).encrypt(slack_url.encode()).decode()
    else:
        value["slack_ciphertext"] = previous.get("slack_ciphertext")
    _store(session, AUTONOMY, value)
    return read_autonomy(session)


def tokens_today(session: Session) -> int:
    start = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    total = session.exec(
        select(
            func.coalesce(func.sum(AgentTrace.input_tokens), 0)
            + func.coalesce(func.sum(AgentTrace.output_tokens), 0)
        ).where(col(AgentTrace.created_at) >= start)
    ).one()
    return int(total or 0)


def check_ai_allowed(session: Session) -> None:
    """Called before every traced AI operation. Raises when the workspace forbids it."""
    autonomy = read_autonomy(session)
    if autonomy.paused:
        raise WorkflowError("AI operations are paused for this workspace (kill switch).", 423)
    if autonomy.daily_token_budget is not None:
        if tokens_today(session) >= autonomy.daily_token_budget:
            raise WorkflowError("Today's AI token budget for this workspace is used up.", 429)


def check_action_quota(session: Session) -> None:
    autonomy = read_autonomy(session)
    if autonomy.paused:
        raise WorkflowError("Proposals are paused for this workspace (kill switch).", 423)
    since = _now() - timedelta(days=1)
    created = session.exec(
        select(func.count())
        .select_from(PendingAction)
        .where(col(PendingAction.created_at) >= since)
    ).one()
    if created >= autonomy.daily_action_quota:
        raise WorkflowError("The daily proposal quota for this workspace is used up.", 429)


def usage(session: Session) -> dict:
    autonomy = read_autonomy(session)
    since = _now() - timedelta(days=1)
    proposals = session.exec(
        select(func.count())
        .select_from(PendingAction)
        .where(col(PendingAction.created_at) >= since)
    ).one()
    return {
        "tokens_today": tokens_today(session),
        "daily_token_budget": autonomy.daily_token_budget,
        "proposals_last_24h": int(proposals),
        "daily_action_quota": autonomy.daily_action_quota,
    }


# ------------------------------------------------------------------ schedule


def read_schedule(session: Session) -> Schedule:
    return Schedule.model_validate(_fact(session, SCHEDULE))


def update_schedule(session: Session, settings: Settings, update: ScheduleUpdate) -> Schedule:
    current = read_schedule(session)
    if update.connection_id:
        from customer_intelligence.models.connection import Connection

        if session.get(Connection, update.connection_id) is None:
            raise WorkflowError("Connection not found.", 404)
    if update.source_id:
        from customer_intelligence.services.sources import read_source

        read_source(settings, update.source_id)
    if update.connection_id and update.source_id:
        raise WorkflowError("Choose either a connection or a source, not both.")
    if update.enabled:
        check_schedule_model(session, settings, update.connection_id, update.source_id)
    value = update.model_dump(mode="json")
    value["history"] = current.model_dump(mode="json")["history"]
    value["last_run_at"] = current.model_dump(mode="json")["last_run_at"]
    value["next_run_at"] = (_now() + timedelta(minutes=1)).isoformat() if update.enabled else None
    _store(session, SCHEDULE, value)
    return read_schedule(session)


def check_schedule_model(
    session: Session, settings: Settings, connection_id: UUID | None, source_id: UUID | None
) -> None:
    """Refuse a schedule whose data the active model can't score (it would fail every day).

    A connection that hasn't synced yet is checked on its first run instead.
    """
    from customer_intelligence.ml.snapshots import SnapshotError, current_snapshot
    from customer_intelligence.models.connection import Connection
    from customer_intelligence.services.monitoring import active_model
    from customer_intelligence.services.runs import read_training_run
    from customer_intelligence.services.sources import load_tables

    if connection_id:
        connection = session.get(Connection, connection_id)
        source_id = connection.last_source_id if connection else None
    run_id = active_model(session)["run_id"]
    if not source_id or not run_id:
        return
    run = read_training_run(UUID(run_id), settings.data_directory)
    try:
        columns = set(current_snapshot(load_tables(settings, source_id)).columns)
    except SnapshotError as exc:
        raise WorkflowError(f"This data source can't be scored yet: {exc}") from exc
    missing = [c for c in run.task.feature_columns if c not in columns]
    if missing:
        shown = ", ".join(missing[:4]) + ("…" if len(missing) > 4 else "")
        raise WorkflowError(
            "The active model was trained on different data, so it can't score this source "
            f"(missing {shown}). Train a model from this source and make it active first."
        )


def detach_connection(session: Session, connection_id: UUID) -> None:
    """Pause the schedule when the connection it reads from is removed."""
    value = dict(_fact(session, SCHEDULE))
    if value.get("connection_id") == str(connection_id):
        value.update(connection_id=None, enabled=False, next_run_at=None)
        _store(session, SCHEDULE, value)


def submit_cycle(session: Session, reason: str, slot: str) -> Any:
    from customer_intelligence.services.jobs import submit_job

    key = uuid5(NAMESPACE_URL, f"monitoring-cycle:{slot}")
    return submit_job(session, "cycle", {"reason": reason, "slot": slot}, key)


def apply_due_retention(session: Session) -> bool:
    """Apply the data-retention policy at most once a day (worker loop)."""
    from customer_intelligence.services import governance

    policy = governance.read_retention(session)
    last = policy["last_applied_at"]
    if not policy["days"] or (
        last and _now() - _aware(datetime.fromisoformat(last)) < timedelta(days=1)
    ):
        return False
    governance.apply_retention(session, session.info["settings"])
    return True


def tick(session: Session) -> bool:
    """Queue a cycle when one is due. Called by the worker loop; cheap when nothing is due."""
    apply_due_retention(session)
    schedule = read_schedule(session)
    if not schedule.enabled or schedule.next_run_at is None:
        return False
    if read_autonomy(session).paused or _now() < _aware(schedule.next_run_at):
        return False
    slot = _aware(schedule.next_run_at).isoformat()
    try:
        submit_cycle(session, "scheduled", slot)
    except WorkflowError:
        return False
    value = schedule.model_dump(mode="json")
    value["next_run_at"] = (_now() + timedelta(hours=schedule.cadence_hours)).isoformat()
    _store(session, SCHEDULE, value)
    return True


# ------------------------------------------------------------------ the cycle


def run_cycle(session: Session, settings: Settings, job_id: UUID) -> UUID:
    """Sync → score with the active model → drift → realized performance → digest."""
    from customer_intelligence.schemas.workflow import ScoreRequest
    from customer_intelligence.services import connectors, monitoring, playbooks, sources
    from customer_intelligence.services.scoring import read_customers, read_score, score_dataset

    schedule = read_schedule(session)
    autonomy = read_autonomy(session)
    if autonomy.paused:
        raise WorkflowError("Cycles are paused for this workspace (kill switch).", 423)
    active = monitoring.active_model(session)["run_id"]
    if not active:
        raise WorkflowError("Choose an active model on the Models page before monitoring.", 409)
    if schedule.connection_id:
        source = connectors.sync(session, settings, schedule.connection_id)
    elif schedule.source_id:
        source = sources.read_source(settings, schedule.source_id)
    else:
        raise WorkflowError("Choose a data source for the schedule first.", 409)
    source_id = UUID(source["id"])
    built = sources.build_dataset(session, settings, source_id, schedule.horizon_days, "scoring")
    score_id = score_dataset(
        session,
        settings,
        ScoreRequest(
            run_id=UUID(active),
            dataset_id=UUID(built["dataset_id"]),
            contact_count=min(schedule.contact_count, built["rows"]),
            holdout_rate=schedule.holdout_rate,
            idempotency_key=uuid5(NAMESPACE_URL, f"{job_id}:score"),
        ),
    )
    drift = monitoring.feature_drift(session, settings, score_id)
    measured = []
    history = schedule.model_dump(mode="json")["history"]
    for entry in history:
        if entry.get("evaluated") or not entry.get("score_id"):
            continue
        earlier = UUID(entry["score_id"])
        try:
            outcomes, segments = monitoring.outcomes_from_source(
                settings, earlier, source_id, schedule.horizon_days
            )
            basis = {
                "kind": "source_sync",
                "source_id": str(source_id),
                "horizon_days": schedule.horizon_days,
            }
            report = monitoring.measure_performance(session, settings, earlier, outcomes, basis)
        except WorkflowError:
            continue
        entry["evaluated"] = str(report.id)
        measured.append(report)
        if read_score(earlier, settings.data_directory).holdout_count:
            try:
                lift = monitoring.measure_lift(
                    session, settings, earlier, outcomes, basis, segments
                )
            except WorkflowError:
                continue
            measured.append(lift)
    severity = max(
        [drift.status, *[m.status for m in measured]],
        key=["stable", "watch", "alert"].index,
    )
    score = read_score(score_id, settings.data_directory)
    lines = [f"Scored {score.row_count} accounts with the active model.", drift.summary]
    lines += [m.summary for m in measured]
    links = [
        {"label": "Risk scores", "href": f"/app/scores/{score_id}"},
        {"label": "Drift report", "href": f"/app/monitoring/{drift.id}"},
        *[
            {
                "label": "Outreach result" if m.kind == "lift" else "How predictions held up",
                "href": f"/app/monitoring/{m.id}",
            }
            for m in measured
        ],
    ]
    if autonomy.level in ("recommend", "act_with_approval"):
        top = sorted(
            (c for c in read_customers(score, settings.data_directory) if c.group != "holdout"),
            key=lambda c: c.rank,
        )[:5]
        lines.append("Review first: " + ", ".join(c.customer_id for c in top) + ".")
        if playbooks.list_playbooks(settings):
            moved = [
                f["feature"].replace("_", " ")
                for f in drift.payload["features"]
                if f["band"] != "stable"
            ]
            query = " ".join(moved[:3]) or "renewal churn risk"
            hit = playbooks.search(settings, query, 1)["results"]
            if hit:
                first = hit[0]
                lines.append(f"Related playbook passage: {first['playbook']} › {first['heading']}.")
                href = f"/app/playbooks/{first['playbook_id']}"
                links.append({"label": "Playbook", "href": href})
    if autonomy.level == "act_with_approval" and severity == "alert":
        try:
            proposal = propose_retraining(
                session, settings, UUID(active), source_id, schedule.horizon_days
            )
            lines.append(
                "Monitoring raised an alert, so retraining on the latest data is waiting "
                "for your approval in the Inbox."
            )
            links.append({"label": "Approve retraining", "href": f"/app/inbox#{proposal.id}"})
        except WorkflowError as exc:
            lines.append(f"Retraining was not proposed: {exc}")
    item = DigestItem(
        kind="cycle",
        severity="info" if severity == "stable" else severity,
        title={
            "stable": "Scheduled check: no material change",
            "watch": "Scheduled check: something to watch",
            "alert": "Scheduled check: monitoring alert",
        }[severity],
        body="\n".join(lines)[:2000],
        links=links,
        job_id=job_id,
    )
    session.add(item)
    history.insert(
        0, {"score_id": str(score_id), "source_id": str(source_id), "at": _now().isoformat()}
    )
    value = schedule.model_dump(mode="json")
    value["history"] = history[:24]
    value["last_run_at"] = _now().isoformat()
    _store(session, SCHEDULE, value)
    session.refresh(item)
    from customer_intelligence.services.audit import record

    record(session, "scheduler", f"ran a check ({severity})", str(score_id))
    if autonomy.ai_briefs:
        _brief_for(session, settings, item, score_id)
    notify(session, settings, item)
    return score_id


def _brief_for(session: Session, settings: Settings, item: DigestItem, score_id: UUID) -> None:
    """Nemotron's brief for this check. A failure never undoes the measured results."""
    from customer_intelligence.services import briefs, reasons

    try:
        brief = briefs.write_brief(session, settings, score_id)
    except WorkflowError as exc:
        session.rollback()
        briefs.record_failure(session, score_id, str(exc))
        item.body = (item.body + f"\nNemotron brief unavailable: {exc}")[:2000]
    else:
        item.title = "Nemotron brief: " + str(brief.content["headline"])[:150]
        item.links = [{"label": "Read the brief", "href": f"/app?brief={brief.id}"}, *item.links]
        try:
            reasons.write_notes(session, settings, score_id)
        except WorkflowError:
            session.rollback()
    session.add(item)
    session.commit()


def propose_retraining(
    session: Session, settings: Settings, run_id: UUID, source_id: UUID, horizon_days: int
) -> PendingAction:
    from customer_intelligence.services.runs import read_training_run

    run = read_training_run(run_id, settings.data_directory)
    pending = session.exec(
        select(PendingAction).where(
            PendingAction.kind == "retrain", PendingAction.status == "pending"
        )
    ).all()
    if pending:
        return pending[0]
    check_action_quota(session)
    action = PendingAction(
        kind="retrain",
        summary=f"Retrain {run.task.target_column} on the latest data from this source "
        f"({len(run.task.feature_columns)} inputs, {horizon_days}-day horizon), using the same "
        "churn definition as the active model.",
        payload={
            "base_run_id": str(run_id),
            "source_id": str(source_id),
            "horizon_days": horizon_days,
        },
        origin="monitoring",
    )
    session.add(action)
    session.commit()
    from customer_intelligence.services.audit import record

    record(session, "monitoring", "proposed retraining", str(action.id))
    session.refresh(action)
    return action


def approve_retraining(session: Session, settings: Settings, action: PendingAction) -> UUID:
    """Build fresh snapshots, recreate the confirmed definition on them, and queue training."""
    from customer_intelligence.models.dataset import Dataset
    from customer_intelligence.schemas.task import TaskCreateRequest
    from customer_intelligence.services import sources
    from customer_intelligence.services.jobs import submit_job
    from customer_intelligence.services.runs import read_training_run
    from customer_intelligence.services.tasks import create_task

    run = read_training_run(UUID(action.payload["base_run_id"]), settings.data_directory)
    built = sources.build_dataset(
        session,
        settings,
        UUID(action.payload["source_id"]),
        int(action.payload["horizon_days"]),
        "training",
    )
    recommended = built["recommended_task"] or {}
    features = [c for c in run.task.feature_columns if c in recommended.get("feature_columns", [])]
    if run.task.target_column != recommended.get("target_column") or not features:
        raise WorkflowError("The latest data no longer matches the active model's definition.", 409)
    dataset = session.get(Dataset, UUID(built["dataset_id"]))
    if dataset is None:
        raise WorkflowError("The rebuilt dataset is missing.", 409)
    task = create_task(
        dataset,
        TaskCreateRequest(
            target_column=run.task.target_column,
            positive_label=run.task.positive_label,
            id_column=run.task.id_column,
            time_column=run.task.time_column,
            feature_columns=features,
            features_available_at_prediction=True,
        ),
        settings,
        session,
    )
    key = uuid5(NAMESPACE_URL, f"pending-action:{action.id}")
    job = submit_job(
        session,
        "train",
        {
            "task_id": str(task.id),
            "search_trials": 0,
            "threshold": 0.5,
            "cv_folds": 3,
            "idempotency_key": str(key),
        },
        key,
    )
    return job.id


# ------------------------------------------------------------------ digest


def list_digest(session: Session, limit: int = 30) -> list[DigestItem]:
    return list(
        session.exec(select(DigestItem).order_by(col(DigestItem.created_at).desc()).limit(limit))
    )


def mark_read(session: Session, item_id: UUID) -> DigestItem:
    item = session.get(DigestItem, item_id)
    if item is None:
        raise WorkflowError("Digest item not found.", 404)
    item.read_at = item.read_at or _now()
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def record_failure(session: Session, job_id: UUID, error: str) -> None:
    item = DigestItem(
        kind="cycle",
        severity="watch",
        title="Scheduled check did not complete",
        body=error[:2000],
        links=[{"label": "Job", "href": f"/app/jobs#{job_id}"}],
        job_id=job_id,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    settings = session.info.get("settings")
    if settings is not None:
        notify(session, settings, item)


def notify(session: Session, settings: Settings, item: DigestItem) -> None:
    """Post the digest headline to Slack when the workspace connected a webhook.

    Only the title, the aggregate lines and links are sent: account IDs stay in the app. People who
    opted in also get it by email; neither channel can undo or block the check's results.
    """
    from customer_intelligence.services.email import send_digest

    try:
        send_digest(session, settings, item)
    except Exception:  # noqa: BLE001 - delivery must never fail a finished check
        session.rollback()
        item.emailed = "Email could not be sent."
        session.add(item)
        session.commit()
    ciphertext = _fact(session, AUTONOMY).get("slack_ciphertext")
    if not ciphertext:
        return
    from cryptography.fernet import InvalidToken

    from customer_intelligence.services.connectors import _fernet

    try:
        url = _fernet(settings).decrypt(ciphertext.encode()).decode()
    except (InvalidToken, WorkflowError):
        item.notified = "Slack webhook could not be decrypted with this key."
    else:
        lines = [line for line in item.body.splitlines() if not line.startswith("Review first:")]
        origin = settings.auth_public_origin.rstrip("/")
        text = f"*{item.title}*\n" + "\n".join(lines)
        text += "\n" + " · ".join(f"<{origin}{x['href']}|{x['label']}>" for x in item.links)
        try:
            with httpx.Client(timeout=10, transport=transport, follow_redirects=False) as client:
                response = client.post(url, json={"text": text})
            item.notified = (
                "slack"
                if response.status_code < 300
                else (f"Slack returned HTTP {response.status_code}.")
            )
        except httpx.HTTPError:
            item.notified = "Slack could not be reached."
    session.add(item)
    session.commit()
