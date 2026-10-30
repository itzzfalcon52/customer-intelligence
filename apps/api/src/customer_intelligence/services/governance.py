"""Usage metering and data-retention controls for a workspace.

Usage is computed from records the product already keeps (AI traces, jobs, scoring manifests);
nothing is estimated. Retention deletes ageing derived data and unused uploads, but never the
audit log, trained models, or datasets a churn definition (and therefore a model) depends on.
"""

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from sqlalchemy import func
from sqlmodel import Session, col, select

from customer_intelligence.core.config import Settings
from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.models.conversation import Conversation, ConversationTurn
from customer_intelligence.models.dataset import Dataset
from customer_intelligence.models.job import Job
from customer_intelligence.models.operations import DigestItem, MonitorReport
from customer_intelligence.models.task import Task
from customer_intelligence.models.trace import AgentSpan, AgentTrace
from customer_intelligence.models.workspace import WorkspaceFact

RETENTION = "retention_policy"


def _month(month: str | None) -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    try:
        start = (
            datetime.strptime(month, "%Y-%m").replace(tzinfo=UTC)
            if month
            else now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        )
    except ValueError as exc:
        raise WorkflowError("Use a month like 2026-10.") from exc
    end = (start + timedelta(days=32)).replace(day=1)
    return start, end


def usage(session: Session, settings: Settings, month: str | None) -> dict:
    start, end = _month(month)
    in_month = (col(AgentTrace.created_at) >= start) & (col(AgentTrace.created_at) < end)
    calls, tokens_in, tokens_out, cost = session.exec(
        select(
            func.count(),
            func.coalesce(func.sum(AgentTrace.input_tokens), 0),
            func.coalesce(func.sum(AgentTrace.output_tokens), 0),
            func.sum(AgentTrace.cost_usd),
        ).where(in_month)
    ).one()
    jobs = session.exec(
        select(Job.kind, func.count())
        .where(col(Job.created_at) >= start, col(Job.created_at) < end)
        .group_by(Job.kind)
    ).all()
    scored = 0
    directory = settings.data_directory / "scores"
    from customer_intelligence.services.scoring import read_score

    for path in directory.iterdir() if directory.exists() else []:
        try:
            score = read_score(UUID(path.name), settings.data_directory)
        except (ValueError, WorkflowError):
            continue
        if start <= score.created_at.astimezone(UTC) < end:
            scored += score.row_count
    return {
        "month": start.strftime("%Y-%m"),
        "ai_operations": int(calls),
        "ai_tokens": {"input": int(tokens_in or 0), "output": int(tokens_out or 0)},
        # Only priced when CI_MODEL_PRICES is configured; never estimated.
        "ai_cost_usd": round(float(cost), 4) if cost is not None else None,
        "jobs": {kind: int(count) for kind, count in jobs},
        "accounts_scored": scored,
    }


def read_retention(session: Session) -> dict:
    fact = session.get(WorkspaceFact, RETENTION)
    value = fact.value if fact else {}
    return {"days": value.get("days"), "last_applied_at": value.get("last_applied_at")}


def update_retention(session: Session, days: int | None) -> dict:
    current = read_retention(session)
    value = {"days": days, "last_applied_at": current["last_applied_at"]}
    fact = session.get(WorkspaceFact, RETENTION)
    if fact is None:
        fact = WorkspaceFact(key=RETENTION, value=value, source="user")
    else:
        fact.value, fact.source, fact.updated_at = value, "user", datetime.now(UTC)
    session.add(fact)
    session.commit()
    return read_retention(session)


def _old_folders(root: Path, cutoff: datetime) -> list[Path]:
    if not root.exists():
        return []
    return [
        p
        for p in root.iterdir()
        if p.is_dir()
        and not p.name.startswith(".")
        and datetime.fromtimestamp(p.stat().st_mtime, UTC) < cutoff
    ]


def apply_retention(session: Session, settings: Settings, days: int | None = None) -> dict:
    """Delete derived data older than the policy. Returns what was removed."""
    days = days or read_retention(session)["days"]
    if not days:
        raise WorkflowError("Set a retention period first.", 409)
    cutoff = datetime.now(UTC) - timedelta(days=days)
    removed = {"scores": 0, "analyses": 0, "conversations": 0, "traces": 0, "reports": 0}
    for kind in ("scores", "analyses"):
        for folder in _old_folders(settings.data_directory / kind, cutoff):
            shutil.rmtree(folder, ignore_errors=True)
            removed[kind] += 1
    for conversation in session.exec(
        select(Conversation).where(col(Conversation.created_at) < cutoff)
    ).all():
        for turn in session.exec(
            select(ConversationTurn).where(ConversationTurn.conversation_id == conversation.id)
        ).all():
            session.delete(turn)
        session.delete(conversation)
        removed["conversations"] += 1
    for trace in session.exec(select(AgentTrace).where(col(AgentTrace.created_at) < cutoff)).all():
        for span in session.exec(select(AgentSpan).where(AgentSpan.trace_id == trace.id)).all():
            session.delete(span)
        session.delete(trace)
        removed["traces"] += 1
    for model in (MonitorReport, DigestItem):
        for row in session.exec(select(model).where(col(model.created_at) < cutoff)).all():
            session.delete(row)
            removed["reports"] += 1
    # Uploads no churn definition uses; datasets behind a task stay so models keep working.
    used = {t.dataset_id for t in session.exec(select(Task)).all()}
    removed["datasets"] = 0
    for dataset in session.exec(select(Dataset).where(col(Dataset.created_at) < cutoff)).all():
        if dataset.id in used:
            continue
        (settings.data_directory / "uploads" / dataset.storage_key).unlink(missing_ok=True)
        session.delete(dataset)
        removed["datasets"] += 1
    fact = session.get(WorkspaceFact, RETENTION)
    if fact is not None:
        fact.value = {**fact.value, "last_applied_at": datetime.now(UTC).isoformat()}
        session.add(fact)
    session.commit()
    from customer_intelligence.services.audit import record

    record(session, "retention", f"deleted data older than {days} days", str(removed))
    return {"days": days, "removed": removed}
