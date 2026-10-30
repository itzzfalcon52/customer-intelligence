from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import or_
from sqlmodel import Session, col, select

from customer_intelligence.agent.inspection import AgentInspectionError
from customer_intelligence.agent.workflow import chat
from customer_intelligence.api.streaming import event_stream
from customer_intelligence.core.config import Settings, get_settings
from customer_intelligence.core.database import get_session
from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.models.conversation import Conversation, ConversationTurn
from customer_intelligence.models.dataset import Dataset
from customer_intelligence.models.task import Task
from customer_intelligence.models.trace import AgentSpan, AgentTrace
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


@router.post("/messages/stream")
def message_stream(
    request: AssistantRequest,
    http: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> StreamingResponse:
    """Server-sent events for one turn: model/tool steps as they happen, then the answer.

    The turn runs to completion even if the browser disconnects; it is idempotent, bounded by
    the same budgets as /messages, and its result is saved to the conversation and trace.
    """
    return event_stream(
        http,
        lambda session, listener: chat(request, session, settings, listener=listener).model_dump(
            mode="json"
        ),
        "assistant",
    )


@router.get("/traces")
def traces(
    session: Annotated[Session, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    kind: str | None = None,
) -> list[AgentTrace]:
    query = select(AgentTrace)
    if kind:
        query = query.where(AgentTrace.kind == kind)
    return list(session.exec(query.order_by(col(AgentTrace.created_at).desc()).limit(limit)))


@router.get("/traces/{trace_id}")
def trace(trace_id: UUID, session: Annotated[Session, Depends(get_session)]) -> dict:
    record = session.get(AgentTrace, trace_id)
    if record is None:
        raise WorkflowError("Trace not found.", 404, "trace_not_found")
    spans = session.exec(
        select(AgentSpan).where(AgentSpan.trace_id == trace_id).order_by(col(AgentSpan.sequence))
    ).all()
    return {
        "trace": record.model_dump(mode="json"),
        "spans": [span.model_dump(mode="json") for span in spans],
    }


@router.get("/conversations/{conversation_id}")
def conversation(conversation_id: UUID, session: Annotated[Session, Depends(get_session)]) -> dict:
    record = session.get(Conversation, conversation_id)
    actor = session.info.get("actor")
    if record is None or (record.owner_id and record.owner_id != actor):
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


@router.get("/conversations")
def conversation_history(
    session: Annotated[Session, Depends(get_session)], dataset_id: UUID | None = None
) -> list[dict]:
    actor = session.info.get("actor")
    query = select(Conversation).where(
        or_(col(Conversation.owner_id).is_(None), col(Conversation.owner_id) == actor)
    )
    if dataset_id:
        query = query.where(Conversation.dataset_id == dataset_id)
    records = session.exec(query.order_by(col(Conversation.created_at).desc()).limit(100)).all()
    return [
        {
            "id": str(record.id),
            "dataset_id": str(record.dataset_id),
            "created_at": record.created_at.isoformat(),
        }
        for record in records
    ]
