from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from customer_intelligence.schemas.workflow import StrictRequest


class BusinessAssumptions(StrictRequest):
    """Assumptions the user confirmed for budget planning. Never measured outcomes."""

    budget: float | None = Field(default=None, ge=0, le=1e9, allow_inf_nan=False)
    contact_cost: float | None = Field(default=None, gt=0, le=1e6, allow_inf_nan=False)
    offer_cost: float | None = Field(default=None, ge=0, le=1e6, allow_inf_nan=False)
    assumed_save_rate: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    retained_value: float | None = Field(default=None, gt=0, le=1e9, allow_inf_nan=False)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")


class Decision(StrictRequest):
    text: str = Field(min_length=1, max_length=300)


class MemoryUpdate(StrictRequest):
    assumptions: BusinessAssumptions | None = None
    decisions: list[Decision] | None = Field(default=None, max_length=20)


class MemoryResponse(BaseModel):
    assumptions: dict
    assumptions_source: str | None
    decisions: list[dict]
    updated_at: datetime | None


class PendingActionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: str
    summary: str
    payload: dict
    status: Literal["pending", "approved", "rejected"]
    origin: str
    trace_id: UUID | None
    result_id: UUID | None
    created_at: datetime
    decided_at: datetime | None
