from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AutonomySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: Literal["observe", "recommend", "act_with_approval"] = "observe"
    # Kill switch: pauses AI calls, scheduled cycles and new proposals for this workspace.
    paused: bool = False
    daily_token_budget: int | None = Field(default=None, ge=1_000, le=50_000_000)
    daily_action_quota: int = Field(default=5, ge=0, le=100)
    # Explicit workspace consent for Nemotron to write a brief after every scheduled check.
    # Only aggregates, computed drivers and pseudonymous account labels are sent.
    ai_briefs: bool = False
    slack_connected: bool = False


class AutonomyUpdate(AutonomySettings):
    # Write-only. Empty string disconnects; omitted keeps the stored webhook.
    slack_webhook_url: str | None = Field(default=None, max_length=500)


class Schedule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    cadence_hours: int = Field(default=24, ge=1, le=24 * 31)
    connection_id: UUID | None = None
    source_id: UUID | None = None
    horizon_days: int = Field(default=90, ge=14, le=365)
    contact_count: int = Field(default=50, ge=1, le=10_000_000)
    holdout_rate: float = Field(default=0.0, ge=0.0, le=0.5)
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    history: list[dict] = Field(default_factory=list)


class ScheduleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    cadence_hours: int = Field(default=24, ge=1, le=24 * 31)
    connection_id: UUID | None = None
    source_id: UUID | None = None
    horizon_days: int = Field(default=90, ge=14, le=365)
    contact_count: int = Field(default=50, ge=1, le=10_000_000)
    holdout_rate: float = Field(default=0.0, ge=0.0, le=0.5)


class PromoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: UUID


class OutcomesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    score_id: UUID
    dataset_id: UUID
    id_column: str = Field(min_length=1, max_length=250)
    outcome_column: str = Field(min_length=1, max_length=250)
    positive_label: str = Field(min_length=1, max_length=250)
    segment_column: str | None = Field(default=None, min_length=1, max_length=250)


class SourceOutcomesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    score_id: UUID
    source_id: UUID
    horizon_days: int = Field(default=90, ge=14, le=365)


class MonitorReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    kind: str
    run_id: UUID
    score_id: UUID | None
    status: str
    summary: str
    payload: dict
    created_at: datetime


class DigestItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    kind: str
    severity: str
    title: str
    body: str
    links: list
    job_id: UUID | None
    created_at: datetime
    read_at: datetime | None
    notified: str | None
