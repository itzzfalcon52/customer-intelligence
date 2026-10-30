from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class MonitorReport(SQLModel, table=True):
    """A computed monitoring check: feature drift, score shift or realized performance."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    kind: str = Field(index=True)  # "drift" | "performance" | "lift"
    run_id: UUID = Field(index=True)
    score_id: UUID | None = Field(default=None, index=True)
    status: str = "stable"  # "stable" | "watch" | "alert"
    summary: str = Field(max_length=500)
    payload: dict = Field(sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)


class DigestItem(SQLModel, table=True):
    """One entry in the workspace digest, each linked to the evidence that produced it."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    kind: str = Field(index=True)
    severity: str = "info"  # "info" | "watch" | "alert"
    title: str = Field(max_length=200)
    body: str = Field(max_length=2000)
    links: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    job_id: UUID | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    read_at: datetime | None = None
    notified: str | None = None  # "slack" once delivered, or a short delivery error
    emailed_at: datetime | None = None  # set once, so an item is never emailed twice
    emailed: str | None = Field(default=None, max_length=300)  # "sent to N" or a short error


class AuditEvent(SQLModel, table=True):
    """Who changed what in this workspace. Request bodies are never stored."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    actor: str = Field(max_length=200)  # a user ID, or "system:<component>"
    role: str = Field(max_length=20)
    action: str = Field(max_length=300)
    target: str | None = Field(default=None, max_length=300)
    status_code: int | None = None


class Brief(SQLModel, table=True):
    """Nemotron's daily brief for a scoring batch, kept only after deterministic verification."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    score_id: UUID = Field(index=True)
    trace_id: UUID | None = None
    status: str = "ready"  # "ready" | "failed"
    content: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    verification: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    error: str | None = Field(default=None, max_length=500)
