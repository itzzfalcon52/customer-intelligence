from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InspectDatasetArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_id: UUID = Field(description="The uploaded dataset to inspect.")


class ReadTaskArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: UUID = Field(description="The saved task supplied in this request.")


class InspectionResult(BaseModel):
    dataset_id: UUID
    task_id: UUID | None = None
    model: str
    answer: str
    completed_tools: list[str]
    model_call_count: int