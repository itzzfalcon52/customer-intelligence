from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from customer_intelligence.api.streaming import event_stream
from customer_intelligence.core.config import Settings, get_settings
from customer_intelligence.core.database import get_session
from customer_intelligence.schemas.investigation import InvestigationRequest
from customer_intelligence.services.investigation import run_investigation

router = APIRouter(prefix="/investigations", tags=["Investigations"])
Config = Annotated[Settings, Depends(get_settings)]


@router.post("")
def investigate(
    request: InvestigationRequest,
    session: Annotated[Session, Depends(get_session)],
    settings: Config,
) -> dict:
    """Plan, run and verify a churn investigation; returns the saved analysis artifact."""
    return run_investigation(request, session, settings)


@router.post("/stream")
def investigate_stream(
    request: InvestigationRequest, http: Request, settings: Config
) -> StreamingResponse:
    """The same investigation as server-sent events: stages, analyses and model calls, then the
    saved artifact as `answer`."""
    return event_stream(
        http,
        lambda session, listener: run_investigation(request, session, settings, listener=listener),
        "investigation",
    )
