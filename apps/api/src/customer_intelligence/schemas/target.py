from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TargetCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_column: str = Field(min_length=1)
    positive_label: str = Field(min_length=1)


class TargetCheckResponse(BaseModel):
    dataset_id: UUID
    target_column: str
    positive_label: str
    missing_label_count: int
    distinct_class_count: int
    class_counts: dict[str, int]
    class_counts_truncated: bool
    label_mapping: dict[str, int]
    target_valid: bool
    blockers: list[str]
