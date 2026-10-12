from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from customer_intelligence.schemas.comparison import BinaryMetrics


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TrainRequest(StrictRequest):
    task_id: UUID
    idempotency_key: UUID
    search_trials: int = Field(default=0, ge=0, le=8)
    threshold: float = Field(default=0.5, ge=0, le=1)


class RunActionRequest(StrictRequest):
    run_id: UUID
    idempotency_key: UUID


class ScoreRequest(RunActionRequest):
    dataset_id: UUID
    contact_count: int = Field(default=50, ge=1, le=50_000)
    value_column: str | None = Field(default=None, min_length=1, max_length=250)
    value_unit: str | None = Field(default=None, max_length=30)
    ranking: Literal["risk", "risk_x_value"] = "risk"

    @field_validator("value_unit")
    @classmethod
    def clean_unit(cls, value: str | None) -> str | None:
        return value.strip() if value else value


class DiagnosticsRequest(RunActionRequest):
    segment_column: str | None = Field(default=None, max_length=250)
    heuristic_column: str | None = Field(default=None, max_length=250)
    heuristic_direction: Literal["higher_risk", "lower_risk"] = "higher_risk"


class ExplanationRequest(StrictRequest):
    score_id: UUID
    row_reference: int = Field(ge=1, le=50_000)
    idempotency_key: UUID


class LeakageRequest(StrictRequest):
    task_id: UUID
    idempotency_key: UUID


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    kind: str
    state: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    stage: str
    cancel_requested: bool
    result_id: UUID | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    heartbeat_at: datetime | None


class ContactMetrics(BaseModel):
    k: int
    true_positive: int
    precision: float
    recall: float
    lift: float


class FinalEvaluation(BaseModel):
    run_id: UUID
    partition: Literal["test"] = "test"
    evaluated_at: datetime
    threshold: float
    metrics: BinaryMetrics
    contact_metrics: list[ContactMetrics]
    calibration_checks: dict = Field(default_factory=dict)
    frozen_candidate_id: str
    warning: str = "Final test metrics must not be used to retune this run."


class CustomerScore(BaseModel):
    customer_id: str
    row_reference: int
    risk_score: float
    rank: int
    customer_value: float | None = None
    exposure_proxy: float | None = None
    priority_rank: int | None = None


class ScoreManifest(BaseModel):
    id: UUID
    run_id: UUID
    dataset_id: UUID
    dataset_sha256: str
    created_at: datetime
    row_count: int
    contact_count: int
    ranking: Literal["risk", "risk_x_value"]
    value_column: str | None
    value_unit: str | None
    rows_sha256: str
    warnings: list[str]


class ScorePage(BaseModel):
    score_id: UUID
    total: int
    offset: int
    customers: list[CustomerScore]


class ToolEvent(BaseModel):
    tool: str
    resource_id: str | None = None
    evidence_path: str | None = None
    status: Literal["completed"] = "completed"


class AssistantRequest(StrictRequest):
    dataset_id: UUID
    task_id: UUID | None = None
    run_id: UUID | None = None
    job_id: UUID | None = None
    score_id: UUID | None = None
    analysis_id: UUID | None = None
    conversation_id: UUID | None = None
    idempotency_key: UUID
    question: str = Field(min_length=1, max_length=2000)
    allow_training: bool = False

    @field_validator("question")
    @classmethod
    def clean_question(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Question cannot be blank.")
        return value.strip()


class AssistantResponse(BaseModel):
    conversation_id: UUID
    turn_id: UUID
    model: str
    answer: str
    events: list[ToolEvent]
    model_call_count: int


class RunComparisonRequest(StrictRequest):
    run_ids: list[UUID] = Field(min_length=2, max_length=5)
