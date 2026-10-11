from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from customer_intelligence.core.config import Settings, get_settings
from customer_intelligence.core.database import get_session
from customer_intelligence.models.dataset import Dataset
from customer_intelligence.models.task import Task
from customer_intelligence.schemas.task import TaskCreateRequest, TaskResponse
from customer_intelligence.services.profiling import DatasetProfileError
from customer_intelligence.services.targets import TargetCheckError
from customer_intelligence.services.tasks import TaskValidationError, create_task

router = APIRouter(tags=["Tasks"])


@router.post("/datasets/{dataset_id}/tasks", response_model=TaskResponse, status_code=201)
def save_task(
    dataset_id: UUID,
    request: TaskCreateRequest,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TaskResponse:
    dataset = session.get(Dataset, dataset_id)

    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found.")

    try:
        task = create_task(dataset, request, settings, session)
    except (TaskValidationError, TargetCheckError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DatasetProfileError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return TaskResponse.model_validate(task)


@router.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(
    task_id: UUID,
    session: Annotated[Session, Depends(get_session)],
) -> TaskResponse:
    task = session.get(Task, task_id)

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")

    return TaskResponse.model_validate(task)