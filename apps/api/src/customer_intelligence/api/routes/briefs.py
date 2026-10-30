from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlmodel import Session

from customer_intelligence.core.config import Settings, get_settings
from customer_intelligence.core.database import get_session
from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.models.operations import Brief
from customer_intelligence.services import autonomy, briefs, reasons

router = APIRouter(tags=["Nemotron briefs and account reasons"])
DB = Annotated[Session, Depends(get_session)]
Config = Annotated[Settings, Depends(get_settings)]


class Consent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Sends aggregates, computed drivers and pseudonymous labels; never raw rows or real IDs.
    provider_consent: Literal[True]


class BriefRequest(Consent):
    score_id: UUID


def _brief(brief: Brief | None) -> dict | None:
    return brief.model_dump(mode="json") if brief else None


@router.get("/briefs/latest")
def latest(session: DB) -> dict:
    return {
        "brief": _brief(briefs.latest(session)),
        "enabled": autonomy.read_autonomy(session).ai_briefs,
    }


@router.get("/briefs/{brief_id}")
def read(brief_id: UUID, session: DB) -> dict:
    return briefs.get(session, brief_id).model_dump(mode="json")


@router.post("/briefs", status_code=201)
def create(request: BriefRequest, session: DB, settings: Config) -> dict:
    brief = briefs.write_brief(session, settings, request.score_id).model_dump(mode="json")
    try:
        reasons.write_notes(session, settings, request.score_id)
    except WorkflowError:
        pass  # notes are optional; the brief stands on its own
    return brief


@router.get("/scores/{score_id}/reasons")
def read_reasons(score_id: UUID, session: DB, settings: Config) -> dict:
    return reasons.drivers(session, settings, score_id)


@router.post("/scores/{score_id}/reasons/notes")
def write_notes(score_id: UUID, request: Consent, session: DB, settings: Config) -> dict:
    return reasons.write_notes(session, settings, score_id)
