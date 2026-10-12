from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from customer_intelligence.core.config import Settings, get_settings
from customer_intelligence.core.database import get_session
from customer_intelligence.models.dataset import Dataset
from customer_intelligence.schemas.target import TargetCheckRequest, TargetCheckResponse
from customer_intelligence.services.profiling import DatasetProfileError
from customer_intelligence.services.targets import TargetCheckError, check_target

router = APIRouter(prefix="/datasets", tags=["Targets"])


@router.post("/{dataset_id}/target-check", response_model=TargetCheckResponse)
def check_dataset_target(
    dataset_id: UUID,
    request: TargetCheckRequest,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TargetCheckResponse:
    dataset = session.get(Dataset, dataset_id)

    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found.")

    try:
        return check_target(dataset, request, settings)
    except TargetCheckError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DatasetProfileError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
