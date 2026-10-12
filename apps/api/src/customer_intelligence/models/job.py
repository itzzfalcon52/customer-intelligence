from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class Job(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    idempotency_key: str = Field(unique=True, index=True)
    request_sha256: str
    kind: str
    payload: dict = Field(sa_column=Column(JSON, nullable=False))
    state: str = Field(default="queued", index=True)
    stage: str = "queued"
    cancel_requested: bool = False
    result_id: UUID | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    finished_at: datetime | None = None
    heartbeat_at: datetime | None = None
