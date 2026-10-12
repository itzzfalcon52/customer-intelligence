from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class PartitionSummary(BaseModel):
    row_count: int
    class_counts: dict[str, int]


class SplitResponse(BaseModel):
    task_id: UUID
    dataset_id: UUID
    dataset_sha256: str
    random_seed: int
    strategy: Literal["stratified_random"]
    train: PartitionSummary
    validation: PartitionSummary
    test: PartitionSummary


class SplitArtifact(BaseModel):
    format_version: Literal[1] = 1
    task_fingerprint: str
    sklearn_version: str
    summary: SplitResponse
    row_assignments: dict[str, list[int]]
