from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, col, select

from customer_intelligence.agent.inspection import AgentInspectionError
from customer_intelligence.agent.workflow import chat
from customer_intelligence.core.config import Settings, get_settings
from customer_intelligence.core.database import get_session
from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.models.conversation import Conversation, ConversationTurn
from customer_intelligence.models.dataset import Dataset
from customer_intelligence.models.task import Task
from customer_intelligence.schemas.inspection import InspectionRequest, InspectionResult
from customer_intelligence.schemas.workflow import AssistantRequest, AssistantResponse
from customer_intelligence.services.assistant import (
    ProviderConfigurationError,
    inspect_with_agent,
)

router = APIRouter(prefix="/assistant", tags=["Assistant"])


@router.post("/inspect", response_model=InspectionResult)
def inspect(
    request: InspectionRequest,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> InspectionResult:
    dataset = session.get(Dataset, request.dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found.")

    if request.task_id is not None:
        task = session.get(Task, request.task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found.")

        if task.dataset_id != dataset.id:
            raise HTTPException(status_code=400, detail="The task belongs to another dataset.")

    try:
        return inspect_with_agent(request, settings, session)
    except ProviderConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AgentInspectionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/messages")
def message(
    request: AssistantRequest,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AssistantResponse:
    return chat(request, session, settings)


@router.get("/conversations/{conversation_id}")
def conversation(conversation_id: UUID, session: Annotated[Session, Depends(get_session)]) -> dict:
    record = session.get(Conversation, conversation_id)
    if record is None:
        raise WorkflowError("Conversation not found.", 404)
    turns = session.exec(
        select(ConversationTurn)
        .where(ConversationTurn.conversation_id == conversation_id)
        .order_by(col(ConversationTurn.created_at))
        .limit(100)
    ).all()
    return {
        "conversation_id": str(record.id),
        "dataset_id": str(record.dataset_id),
        "turns": [
            {
                "question": turn.question,
                "response": turn.response,
                "created_at": turn.created_at.isoformat(),
            }
            for turn in turns
        ],
    }
