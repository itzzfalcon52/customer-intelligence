from typing import Annotated

from fastapi import APIRouter, Depends

from customer_intelligence.core.config import Settings, get_settings
from customer_intelligence.schemas.health import HealthResponse

router = APIRouter(tags=["System"])


@router.get("/health", response_model=HealthResponse)
def check_health(
    settings: Annotated[Settings, Depends(get_settings)],
) -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.service_name,
        environment=settings.environment,
    )