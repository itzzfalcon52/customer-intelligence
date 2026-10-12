from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlmodel import Session

from customer_intelligence.core.config import Settings, get_settings
from customer_intelligence.core.database import get_session
from customer_intelligence.models.dataset import Dataset
from customer_intelligence.schemas.dataset import DatasetUploadResponse
from customer_intelligence.schemas.profile import DatasetProfileResponse
from customer_intelligence.services.datasets import (
    DatasetLimitError,
    DatasetUploadError,
    save_dataset,
)
from customer_intelligence.services.profiling import (
    DatasetProfileError,
    profile_dataset,
)

router = APIRouter(prefix="/datasets", tags=["Datasets"])


@router.post(
    "/upload",
    response_model=DatasetUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_dataset(
    file: Annotated[UploadFile, File()],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    sheet_name: str | None = None,
) -> DatasetUploadResponse:
    try:
        dataset = save_dataset(
            source=file.file,
            filename=file.filename,
            settings=settings,
            session=session,
            sheet_name=sheet_name,
        )
    except DatasetLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=str(exc),
        ) from exc
    except DatasetUploadError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return DatasetUploadResponse.model_validate(dataset)


@router.get(
    "/{dataset_id}/profile",
    response_model=DatasetProfileResponse,
)
def get_dataset_profile(
    dataset_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DatasetProfileResponse:
    dataset = session.get(Dataset, dataset_id)

    if dataset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found.",
        )

    try:
        return profile_dataset(dataset, settings)
    except DatasetProfileError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
