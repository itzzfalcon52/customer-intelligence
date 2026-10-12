from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class Conversation(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    dataset_id: UUID = Field(index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ConversationTurn(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    conversation_id: UUID = Field(index=True)
    idempotency_key: str = Field(unique=True, index=True)
    request_sha256: str
    question: str
    response: dict = Field(sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AssistantLease(SQLModel, table=True):
    idempotency_key: str = Field(primary_key=True)
    dataset_id: UUID = Field(index=True)
    owner_id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
