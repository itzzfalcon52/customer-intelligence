from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TaskCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_column: str = Field(min_length=1)
    positive_label: str = Field(min_length=1)
    id_column: str | None = None
    feature_columns: list[str] = Field(min_length=1, max_length=250)
    features_available_at_prediction: Literal[True]
    # A date column for time-ordered evaluation (snapshot datasets). Never a model input.
    time_column: str | None = None


class TaskResponse(TaskCreateRequest):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dataset_id: UUID
    label_mapping: dict[str, int]
    dataset_sha256: str
    evaluation_strategy: str
    random_seed: int


def fingerprint_payload(task: TaskResponse) -> dict:
    """Task configuration for split/run fingerprints. Fields added later are omitted while
    unset, so splits and runs saved before they existed keep matching."""
    payload = task.model_dump(mode="json")
    if payload.get("time_column") is None:
        payload.pop("time_column", None)
    return payload
