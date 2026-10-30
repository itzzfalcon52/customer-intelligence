"""Workspace memory (confirmed facts) and the approval queue for assistant-proposed actions."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlmodel import Session, col, select

from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.models.dataset import Dataset
from customer_intelligence.models.task import Task
from customer_intelligence.models.workspace import PendingAction, WorkspaceFact
from customer_intelligence.schemas.workspace import BusinessAssumptions, MemoryUpdate
from customer_intelligence.services.jobs import submit_job

ASSUMPTIONS = "business_assumptions"
DECISIONS = "decisions"


def read_memory(session: Session) -> dict:
    facts = {f.key: f for f in session.exec(select(WorkspaceFact)).all()}
    assumptions = facts.get(ASSUMPTIONS)
    decisions = facts.get(DECISIONS)
    stamps = [f.updated_at for f in facts.values()]
    return {
        "assumptions": assumptions.value if assumptions else {},
        "assumptions_source": assumptions.source if assumptions else None,
        "decisions": decisions.value.get("items", []) if decisions else [],
        "updated_at": max(stamps) if stamps else None,
    }


def _put(session: Session, key: str, value: dict, source: str) -> None:
    fact = session.get(WorkspaceFact, key)
    if fact is None:
        fact = WorkspaceFact(key=key, value=value, source=source)
    else:
        fact.value, fact.source, fact.updated_at = value, source, datetime.now(UTC)
    session.add(fact)


def update_memory(session: Session, update: MemoryUpdate, source: str = "user") -> dict:
    if update.assumptions is not None:
        _put(session, ASSUMPTIONS, update.assumptions.model_dump(exclude_none=True), source)
    if update.decisions is not None:
        _put(session, DECISIONS, {"items": [d.model_dump() for d in update.decisions]}, source)
    session.commit()
    return read_memory(session)


def remember_assumptions(session: Session, assumptions: BusinessAssumptions, source: str) -> None:
    """Keep the latest assumptions a person entered; the assistant never writes these."""
    _put(session, ASSUMPTIONS, assumptions.model_dump(exclude_none=True), source)
    session.commit()


def propose_training(session: Session, task_id: UUID, trace_id: UUID | None) -> PendingAction:
    task = session.get(Task, task_id)
    if task is None:
        raise WorkflowError("Task not found.", 404)
    existing = session.exec(
        select(PendingAction).where(
            PendingAction.kind == "train", PendingAction.status == "pending"
        )
    ).all()
    for action in existing:
        if action.payload.get("task_id") == str(task_id):
            return action
    from customer_intelligence.services.autonomy import check_action_quota

    check_action_quota(session)
    action = PendingAction(
        kind="train",
        summary=f"Train models for {task.target_column} = {task.positive_label} "
        f"({len(task.feature_columns)} inputs) with the default plan.",
        payload={"task_id": str(task_id), "search_trials": 0, "threshold": 0.5, "cv_folds": 3},
        trace_id=trace_id,
    )
    session.add(action)
    session.commit()
    session.refresh(action)
    return action


def list_actions(session: Session, status: str | None) -> list[PendingAction]:
    query = select(PendingAction)
    if status:
        query = query.where(PendingAction.status == status)
    return list(session.exec(query.order_by(col(PendingAction.created_at).desc()).limit(50)).all())


def decide(session: Session, action_id: UUID, approve: bool) -> PendingAction:
    action = session.get(PendingAction, action_id)
    if action is None:
        raise WorkflowError("Action not found.", 404)
    if action.status != "pending":
        raise WorkflowError(f"This action was already {action.status}.", 409)
    if approve:
        if action.kind == "train":
            key = uuid5(NAMESPACE_URL, f"pending-action:{action.id}")
            job = submit_job(session, "train", {**action.payload, "idempotency_key": str(key)}, key)
            action.result_id = job.id
        elif action.kind == "play":
            from customer_intelligence.services.plays import execute

            action.payload = {
                **action.payload,
                "result": execute(session, session.info["settings"], action),
            }
        elif action.kind == "retrain":
            from customer_intelligence.services.autonomy import approve_retraining

            action.result_id = approve_retraining(session, session.info["settings"], action)
        else:
            raise WorkflowError("Unsupported action.", 400)
    action.status = "approved" if approve else "rejected"
    action.decided_at = datetime.now(UTC)
    session.add(action)
    session.commit()
    session.refresh(action)
    return action


def workspace_resources(session: Session, data_directory: Path) -> dict:
    """Owner-scoped catalogue for assistant discovery: IDs, names and headline numbers only."""
    from customer_intelligence.services.runs import read_training_run
    from customer_intelligence.services.scoring import read_score

    def ids(kind: str) -> list[UUID]:
        directory = data_directory / kind
        if not directory.exists():
            return []
        paths = sorted(
            (p for p in directory.iterdir() if p.is_dir() and not p.name.startswith(".")),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        out = []
        for p in paths[:10]:
            try:
                out.append(UUID(p.name))
            except ValueError:
                continue
        return out

    runs = []
    for run_id in ids("runs"):
        try:
            run = read_training_run(run_id, data_directory)
        except Exception:
            continue
        runs.append(
            {
                "run_id": str(run_id),
                "task_id": str(run.task.id),
                "selected_model": run.report.best_validation_model,
                "validation_average_precision": max(
                    r.validation.average_precision for r in run.report.results
                ),
            }
        )
    scores = []
    for score_id in ids("scores"):
        try:
            score = read_score(score_id, data_directory)
        except Exception:
            continue
        scores.append(
            {"score_id": str(score_id), "run_id": str(score.run_id), "accounts": score.row_count}
        )
    return {
        "datasets": [
            {"dataset_id": str(d.id), "file": d.original_filename, "rows": d.row_count}
            for d in session.exec(select(Dataset).limit(20)).all()
        ],
        "tasks": [
            {
                "task_id": str(t.id),
                "dataset_id": str(t.dataset_id),
                "outcome": f"{t.target_column} = {t.positive_label}",
                "inputs": len(t.feature_columns),
            }
            for t in session.exec(select(Task).limit(20)).all()
        ],
        "runs": runs,
        "scoring_batches": scores,
    }


def top_accounts(score_id: UUID, data_directory: Path, limit: int = 20) -> dict:
    from customer_intelligence.services.scoring import read_customers, read_score

    score = read_score(score_id, data_directory)
    customers = sorted(read_customers(score, data_directory), key=lambda c: c.rank)
    return {
        "score_id": str(score_id),
        "total_accounts": len(customers),
        "note": "Risk scores rank accounts within this batch; they are not probabilities. "
        "Accounts in the holdout group must not be contacted.",
        "highest_risk": [
            {
                "rank": c.rank,
                "customer_id": c.customer_id,
                "risk_score": round(c.risk_score, 3),
                **({"value": c.customer_value} if c.customer_value is not None else {}),
                **({"group": c.group} if c.group else {}),
            }
            for c in customers[:limit]
        ],
    }
