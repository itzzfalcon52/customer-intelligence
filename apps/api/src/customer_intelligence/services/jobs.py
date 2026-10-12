import json
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID

from sqlalchemy import text
from sqlmodel import Session, col, select

from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.models.dataset import Dataset
from customer_intelligence.models.job import Job
from customer_intelligence.models.task import Task


def utcnow() -> datetime:
    return datetime.now(UTC)


def get_job(session: Session, job_id: UUID) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        raise WorkflowError("Job not found.", 404, "job_not_found")
    return job


def submit_job(session: Session, kind: str, payload: dict, key: UUID) -> Job:
    digest = sha256(
        json.dumps({"kind": kind, "payload": payload}, sort_keys=True).encode()
    ).hexdigest()
    # SQLite serializes this short transaction, including the queue bound.
    session.rollback()
    session.exec(text("BEGIN IMMEDIATE"))  # type: ignore[call-overload]
    try:
        existing = session.exec(select(Job).where(Job.idempotency_key == str(key))).first()
        if existing is not None:
            if existing.request_sha256 != digest:
                raise WorkflowError("Idempotency key was used for a different request.", 409)
            session.commit()
            return existing
        busy = session.exec(select(Job).where(col(Job.state).in_(["queued", "running"]))).all()
        if len(busy) >= 20:
            raise WorkflowError("The local worker queue is full. Try again later.", 429)
        settings = session.info.get("settings")
        if settings is None:
            from customer_intelligence.core.config import get_settings

            settings = get_settings()
        if payload.get("run_id"):
            from customer_intelligence.services.runs import read_training_run

            run = read_training_run(UUID(payload["run_id"]), settings.data_directory)
            if (
                kind == "calibrate"
                and (settings.data_directory / "finalized_tasks" / f"{run.task.id}.json").exists()
            ):
                raise WorkflowError("Final test results were revealed; this task is frozen.", 409)
        if payload.get("score_id"):
            from customer_intelligence.services.scoring import read_score

            read_score(UUID(payload["score_id"]), settings.data_directory)
        if "task_id" in payload:
            task = session.get(Task, UUID(payload["task_id"]))
            if task is None:
                raise WorkflowError("Task not found.", 404)
            if (
                kind == "train"
                and (settings.data_directory / "finalized_tasks" / f"{task.id}.json").exists()
            ):
                raise WorkflowError("Final test results were revealed; this task is frozen.", 409)
            if not task.features_available_at_prediction:
                raise WorkflowError("Feature availability must be confirmed.")
        if kind == "score":
            dataset = session.get(Dataset, UUID(payload["dataset_id"]))
            if dataset is None:
                raise WorkflowError("Scoring dataset not found.", 404)
            if payload["contact_count"] > dataset.row_count:
                raise WorkflowError("Contact count exceeds the number of scoring rows.")
            if payload["ranking"] == "risk_x_value" and not payload.get("value_column"):
                raise WorkflowError("Value-based ranking requires a value column.")
        job = Job(idempotency_key=str(key), request_sha256=digest, kind=kind, payload=payload)
        session.add(job)
        session.commit()
        session.refresh(job)
        return job
    except BaseException:
        session.rollback()
        raise


def cancel_job(session: Session, job_id: UUID) -> Job:
    session.rollback()
    session.exec(text("BEGIN IMMEDIATE"))  # type: ignore[call-overload]
    try:
        job = get_job(session, job_id)
        if job.state not in {"succeeded", "failed", "cancelled"}:
            job.cancel_requested = True
            if job.state == "queued":
                job.state = "cancelled"
                job.stage = "cancelled"
                job.finished_at = utcnow()
            session.add(job)
        session.commit()
        session.refresh(job)
        return job
    except BaseException:
        session.rollback()
        raise


def claim_job(session: Session) -> Job | None:
    session.rollback()
    session.exec(text("BEGIN IMMEDIATE"))  # type: ignore[call-overload]
    try:
        job = session.exec(
            select(Job).where(Job.state == "queued").order_by(col(Job.created_at), col(Job.id))
        ).first()
        if job is not None:
            job.state = "running"
            job.stage = "starting"
            job.started_at = utcnow()
            job.heartbeat_at = utcnow()
            session.add(job)
        session.commit()
        if job is not None:
            session.refresh(job)
        return job
    except BaseException:
        session.rollback()
        raise


def set_stage(session: Session, job_id: UUID, stage: str) -> None:
    job = get_job(session, job_id)
    if job.state != "running" or job.cancel_requested:
        raise WorkflowError("Job is no longer permitted to run.", 409)
    job.stage = stage
    job.heartbeat_at = utcnow()
    session.add(job)
    session.commit()


def finish_job(
    session: Session, job_id: UUID, result_id: UUID | None, error: str | None = None
) -> None:
    session.rollback()
    session.exec(text("BEGIN IMMEDIATE"))  # type: ignore[call-overload]
    job = get_job(session, job_id)
    if job.state != "running":
        session.commit()
        return
    job.state = "cancelled" if job.cancel_requested else ("failed" if error else "succeeded")
    job.stage = job.state
    job.result_id = result_id if job.state == "succeeded" else None
    job.error = error
    job.finished_at = utcnow()
    session.add(job)
    session.commit()


def recover_interrupted_jobs(session: Session) -> int:
    jobs = session.exec(select(Job).where(Job.state == "running")).all()
    for job in jobs:
        job.state = "cancelled" if job.cancel_requested else "failed"
        job.stage = "interrupted"
        job.error = "Worker stopped before completion. Retry with a new idempotency key."
        job.finished_at = utcnow()
        session.add(job)
    session.commit()
    return len(jobs)
