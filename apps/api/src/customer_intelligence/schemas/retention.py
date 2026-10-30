"""Bounded agent actions. No arbitrary code, filesystem paths, or send-mail tools."""

from typing import Literal
from uuid import UUID

from pydantic import Field

from customer_intelligence.schemas.workflow import StrictRequest


class AIRequest(StrictRequest):
    idempotency_key: UUID
    provider_consent: Literal[True]


class SchemaReviewRequest(AIRequest):
    task_id: UUID


class ColumnFinding(StrictRequest):
    column: str = Field(min_length=1, max_length=250)
    decision: Literal["keep", "exclude", "review"]
    reason: str = Field(min_length=1, max_length=600)


class SchemaReasoning(StrictRequest):
    summary: str = Field(min_length=1, max_length=1600)
    findings: list[ColumnFinding] = Field(max_length=250)
    questions: list[str] = Field(max_length=8)


class ApplySchemaRequest(StrictRequest):
    review_id: UUID
    features_available_at_prediction: Literal[True]


class CampaignRequest(AIRequest):
    score_id: UUID
    channel: Literal["email", "sms"] = "email"
    product_name: str = Field(default="our service", min_length=1, max_length=100)
    approved_offer: str = Field(
        default="Offer a helpful check-in; no discount promised.", min_length=1, max_length=400
    )
    permitted_features: list[str] = Field(default_factory=list, max_length=12)


class OutreachDraft(StrictRequest):
    row_reference: int = Field(ge=1, le=50000)
    subject: str = Field(min_length=1, max_length=180)
    body: str = Field(min_length=1, max_length=1800)
    evidence_features: list[str] = Field(max_length=12)


class CampaignDrafts(StrictRequest):
    drafts: list[OutreachDraft] = Field(min_length=1, max_length=5)


class ROIRequest(StrictRequest):
    run_id: UUID
    budget: float = Field(ge=0, le=1e9, allow_inf_nan=False)
    contact_cost: float = Field(gt=0, le=1e6, allow_inf_nan=False)
    offer_cost: float = Field(default=0, ge=0, le=1e6, allow_inf_nan=False)
    assumed_save_rate: float = Field(ge=0, le=1, allow_inf_nan=False)
    retained_value: float = Field(gt=0, le=1e9, allow_inf_nan=False)
    currency: str = Field(default="INR", pattern=r"^[A-Z]{3}$")
    population_size: int = Field(default=1000, ge=1, le=50000)
    score_id: UUID | None = None


class RuleCondition(StrictRequest):
    column: str = Field(min_length=1, max_length=250)
    operator: Literal["lt", "le", "gt", "ge", "eq", "ne"]
    value: str = Field(max_length=150)


class RuleProposal(StrictRequest):
    name: str = Field(min_length=1, max_length=150)
    rationale: str = Field(min_length=1, max_length=1000)
    conditions: list[RuleCondition] = Field(min_length=1, max_length=3)


class RuleRequest(AIRequest):
    run_id: UUID


class BriefingRequest(AIRequest):
    run_id: UUID


class ExecutiveBriefing(StrictRequest):
    paragraphs: list[str] = Field(min_length=3, max_length=3)
