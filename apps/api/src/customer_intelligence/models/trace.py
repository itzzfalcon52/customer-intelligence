from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class AgentTrace(SQLModel, table=True):
    """One AI operation (assistant turn, structured action, provider check).

    Traces live in the account's own metadata database, so workspace isolation also scopes them.
    Prompts, evidence and answers are not copied here; only metadata, hashes and IDs.
    """

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    kind: str = Field(index=True)
    status: str = "running"
    error_code: str | None = None
    dataset_id: UUID | None = Field(default=None, index=True)
    conversation_id: UUID | None = Field(default=None, index=True)
    turn_id: UUID | None = None
    prompt_version: str | None = None
    model_calls: int = 0
    tool_calls: int = 0
    retries: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    duration_ms: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)


class AgentSpan(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    trace_id: UUID = Field(index=True)
    sequence: int
    kind: str  # "model" or "tool"
    name: str
    status: str
    parent: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    attempts: int = 1
    finish_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    duration_ms: int = 0
    error_code: str | None = None
    arguments_sha256: str | None = None
    evidence_path: str | None = None
    detail: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
