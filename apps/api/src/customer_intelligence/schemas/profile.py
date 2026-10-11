from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class NumericSummary(BaseModel):
    minimum: float | None
    maximum: float | None
    mean: float | None
    median: float | None


class ColumnProfile(BaseModel):
    name: str
    inferred_type: Literal["numeric", "string", "empty"]
    missing_count: int
    missing_percentage: float
    unique_count: int
    numeric_summary: NumericSummary | None


class DatasetProfileResponse(BaseModel):
    dataset_id: UUID
    original_filename: str
    row_count: int
    column_count: int
    duplicate_row_count: int
    columns: list[ColumnProfile]
    preview: list[dict[str, str | None]]
    warnings: list[str]