from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session

from customer_intelligence.core.config import Settings, get_settings
from customer_intelligence.core.database import get_session
from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.models.workspace import PendingAction
from customer_intelligence.schemas.workspace import (
    MemoryResponse,
    MemoryUpdate,
    PendingActionResponse,
)
from customer_intelligence.services import plays, workspace

router = APIRouter(tags=["Workspace memory and approvals"])
DB = Annotated[Session, Depends(get_session)]
Config = Annotated[Settings, Depends(get_settings)]


class PlayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    score_id: UUID
    title: str = Field(min_length=1, max_length=200)
    instructions: str = Field(min_length=1, max_length=4000)
    accounts: int = Field(default=50, ge=1, le=plays.MAX_ACCOUNTS)
    connection_id: UUID | None = None


@router.get("/memory", response_model=MemoryResponse)
def memory(session: DB) -> dict:
    return workspace.read_memory(session)


@router.put("/memory", response_model=MemoryResponse)
def update_memory(update: MemoryUpdate, session: DB) -> dict:
    return workspace.update_memory(session, update)


@router.get("/actions", response_model=list[PendingActionResponse])
def actions(
    session: DB,
    status: Annotated[str | None, Query(pattern="^(pending|approved|rejected)$")] = None,
) -> list[PendingAction]:
    return workspace.list_actions(session, status)


@router.post("/actions/plays", response_model=PendingActionResponse, status_code=201)
def propose_play(request: PlayRequest, session: DB, settings: Config) -> PendingAction:
    return plays.propose(
        session,
        settings,
        request.score_id,
        request.title,
        request.instructions,
        request.accounts,
        request.connection_id,
    )


@router.get("/actions/{action_id}/export")
def export_play(action_id: UUID, session: DB) -> Response:
    action = session.get(PendingAction, action_id)
    if action is None:
        raise WorkflowError("Action not found.", 404)
    return Response(
        plays.export(action),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="play-{action_id}.csv"'},
    )


@router.post("/actions/{action_id}/approve", response_model=PendingActionResponse)
def approve(action_id: UUID, session: DB) -> PendingAction:
    return workspace.decide(session, action_id, approve=True)


@router.post("/actions/{action_id}/reject", response_model=PendingActionResponse)
def reject(action_id: UUID, session: DB) -> PendingAction:
    return workspace.decide(session, action_id, approve=False)
