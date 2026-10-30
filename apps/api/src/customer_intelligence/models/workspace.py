from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class WorkspaceFact(SQLModel, table=True):
    """A confirmed fact the user stated once, reused by forms and the assistant."""

    key: str = Field(primary_key=True, max_length=64)
    value: dict = Field(sa_column=Column(JSON, nullable=False))
    source: str = Field(max_length=64)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PendingAction(SQLModel, table=True):
    """An action the assistant proposed; nothing runs until a person approves it."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    kind: str = Field(index=True)
    summary: str = Field(max_length=500)
    payload: dict = Field(sa_column=Column(JSON, nullable=False))
    status: str = Field(default="pending", index=True)
    origin: str = Field(default="assistant", max_length=64)
    trace_id: UUID | None = None
    result_id: UUID | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    decided_at: datetime | None = None
