import shutil
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Query, Response
from sqlalchemy import text
from sqlmodel import col, select

from customer_intelligence.api.routes.workflow import DB, Config
from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.models.conversation import AssistantLease, Conversation, ConversationTurn
from customer_intelligence.models.dataset import Dataset
from customer_intelligence.models.job import Job
from customer_intelligence.models.task import Task
from customer_intelligence.schemas.dataset import DatasetUploadResponse
from customer_intelligence.schemas.task import TaskResponse
from customer_intelligence.services.artifacts import read_json
from customer_intelligence.services.runs import read_training_run
from customer_intelligence.services.scoring import read_score

router = APIRouter(tags=["Catalog"])


@router.get("/datasets", response_model=list[DatasetUploadResponse])
def datasets(
    session: DB, limit: int = Query(default=25, ge=1, le=100), offset: int = Query(default=0, ge=0)
) -> list[Dataset]:
    return list(
        session.exec(
            select(Dataset).order_by(col(Dataset.created_at).desc()).offset(offset).limit(limit)
        ).all()
    )


@router.get("/datasets/{dataset_id}", response_model=DatasetUploadResponse)
def dataset_metadata(dataset_id: UUID, session: DB) -> Dataset:
    dataset = session.get(Dataset, dataset_id)
    if dataset is None:
        raise WorkflowError("Dataset not found.", 404)
    return dataset


@router.get("/tasks", response_model=list[TaskResponse])
def tasks(
    session: DB,
    dataset_id: UUID | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[Task]:
    query = select(Task)
    if dataset_id:
        query = query.where(Task.dataset_id == dataset_id)
    return list(
        session.exec(query.order_by(col(Task.created_at).desc()).offset(offset).limit(limit)).all()
    )


def artifact_ids(directory: Path) -> Iterator[UUID]:
    if directory.exists():
        for path in directory.iterdir():
            if path.is_dir() and not path.name.startswith("."):
                try:
                    yield UUID(path.name)
                except ValueError:
                    continue


@router.delete("/datasets/{dataset_id}", status_code=204)
def delete_dataset(
    dataset_id: UUID, session: DB, settings: Config, cascade: bool = False
) -> Response:
    session.rollback()
    session.exec(text("BEGIN IMMEDIATE"))  # type: ignore[call-overload]
    moved = []
    trash = settings.data_directory / ".trash" / str(uuid4())
    try:
        dataset = session.get(Dataset, dataset_id)
        if dataset is None:
            raise WorkflowError("Dataset not found.", 404)
        from datetime import UTC, datetime

        leases = session.exec(
            select(AssistantLease).where(AssistantLease.dataset_id == dataset_id)
        ).all()
        if any(
            (datetime.now(UTC) - lease.created_at.replace(tzinfo=UTC)).total_seconds() < 300
            for lease in leases
        ):
            raise WorkflowError(
                "Finish active assistant messages before deleting this dataset.", 409
            )
        for lease in leases:
            session.delete(lease)
        task_records = list(session.exec(select(Task).where(Task.dataset_id == dataset_id)).all())
        task_ids = {task.id for task in task_records}
        run_ids = {
            uid
            for uid in artifact_ids(settings.data_directory / "runs")
            if read_training_run(uid, settings.data_directory).task.dataset_id == dataset_id
        }
        score_ids = {
            uid
            for uid in artifact_ids(settings.data_directory / "scores")
            if (score := read_score(uid, settings.data_directory)).dataset_id == dataset_id
            or score.run_id in run_ids
        }
        analysis_ids = set()
        for uid in artifact_ids(settings.data_directory / "analyses"):
            item = read_json(settings.data_directory / "analyses" / str(uid) / "manifest.json")
            if isinstance(item, dict) and (
                item.get("task_id") in {str(v) for v in task_ids}
                or item.get("run_id") in {str(v) for v in run_ids}
                or item.get("score_id") in {str(v) for v in score_ids}
            ):
                analysis_ids.add(uid)
        affected_jobs = []
        for job in session.exec(select(Job)).all():
            payload = job.payload
            if (
                payload.get("dataset_id") == str(dataset_id)
                or payload.get("task_id") in {str(v) for v in task_ids}
                or payload.get("run_id") in {str(v) for v in run_ids}
                or payload.get("score_id") in {str(v) for v in score_ids}
            ):
                affected_jobs.append(job)
        if any(job.state in {"queued", "running"} for job in affected_jobs):
            raise WorkflowError("Cancel and finish related jobs before deleting this dataset.", 409)
        if (task_records or run_ids or score_ids or analysis_ids) and not cascade:
            raise WorkflowError(
                "Dependent artifacts exist. Set cascade=true to delete them together.", 409
            )
        paths = [settings.data_directory / "uploads" / f"{dataset_id}.csv"]
        paths += [settings.data_directory / "splits" / f"{uid}.json" for uid in task_ids]
        paths += [settings.data_directory / "finalized_tasks" / f"{uid}.json" for uid in task_ids]
        for folder, ids in (("runs", run_ids), ("scores", score_ids), ("analyses", analysis_ids)):
            paths += [settings.data_directory / folder / str(uid) for uid in ids]
        trash.mkdir(parents=True)
        for index, path in enumerate(paths):
            if path.exists():
                target = trash / str(index)
                path.rename(target)
                moved.append((path, target))
        conversations = session.exec(
            select(Conversation).where(Conversation.dataset_id == dataset_id)
        ).all()
        for conversation in conversations:
            for turn in session.exec(
                select(ConversationTurn).where(ConversationTurn.conversation_id == conversation.id)
            ).all():
                session.delete(turn)
            session.delete(conversation)
        for job in affected_jobs:
            session.delete(job)
        for task in task_records:
            session.delete(task)
        session.flush()
        session.delete(dataset)
        session.commit()
    except BaseException:
        session.rollback()
        for original, backup in reversed(moved):
            backup.rename(original)
        shutil.rmtree(trash, ignore_errors=True)
        raise
    shutil.rmtree(trash, ignore_errors=True)
    return Response(status_code=204)
