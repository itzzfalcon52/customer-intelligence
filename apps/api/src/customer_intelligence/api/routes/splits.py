from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from customer_intelligence.core.config import Settings, get_settings
from customer_intelligence.core.database import get_session
from customer_intelligence.ml.splitting import SplitValidationError
from customer_intelligence.models.dataset import Dataset
from customer_intelligence.models.task import Task
from customer_intelligence.schemas.split import SplitResponse
from customer_intelligence.services.profiling import (
    DatasetChangedError,
    DatasetProfileError,
)
from customer_intelligence.services.splits import prepare_split

router = APIRouter(tags=["Splits"])


@router.post("/tasks/{task_id}/split", response_model=SplitResponse)
def create_split(
    task_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SplitResponse:
    task = session.get(Task, task_id)

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")

    dataset = session.get(Dataset, task.dataset_id)

    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found.")

    try:
        return prepare_split(task, dataset, settings)
    except (SplitValidationError, DatasetChangedError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DatasetProfileError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc