from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from customer_intelligence.schemas.retention import AIRequest, RuleCondition
from customer_intelligence.schemas.workflow import StrictRequest

CheckTool = Literal["segment_rates", "compare_cohorts"]


class InvestigationRequest(AIRequest):
    run_id: UUID
    question: str = Field(min_length=1, max_length=1000)

    @field_validator("question")
    @classmethod
    def clean_question(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Question cannot be blank.")
        return value.strip()


class Check(StrictRequest):
    """One deterministic analysis the planner asks for. Flat on purpose: easier for models."""

    hypothesis: str = Field(min_length=1, max_length=300)
    tool: CheckTool
    column: str | None = Field(default=None, max_length=250)
    cohort_label: str | None = Field(default=None, max_length=80)
    cohort_a: list[RuleCondition] | None = Field(default=None, max_length=3)
    cohort_b: list[RuleCondition] | None = Field(default=None, max_length=3)

    @model_validator(mode="after")
    def arguments_match_tool(self) -> "Check":
        if self.tool == "segment_rates" and not self.column:
            raise ValueError("segment_rates requires column.")
        if self.tool == "compare_cohorts" and not self.cohort_a:
            raise ValueError("compare_cohorts requires cohort_a (cohort_b defaults to the rest).")
        return self


class InvestigationPlan(StrictRequest):
    restated_question: str = Field(min_length=1, max_length=300)
    checks: list[Check] = Field(min_length=1, max_length=4)


class FollowUp(StrictRequest):
    done: bool
    rationale: str = Field(min_length=1, max_length=300)
    checks: list[Check] = Field(default_factory=list, max_length=2)


class Finding(StrictRequest):
    statement: str = Field(min_length=1, max_length=400)
    kind: Literal["association", "measurement", "data_quality", "model_performance"]
    evidence: list[str] = Field(min_length=1, max_length=4)


class InvestigationReport(StrictRequest):
    headline: str = Field(min_length=1, max_length=240)
    findings: list[Finding] = Field(min_length=1, max_length=6)
    caveats: list[str] = Field(default_factory=list, max_length=5)
    next_steps: list[str] = Field(default_factory=list, max_length=4)
