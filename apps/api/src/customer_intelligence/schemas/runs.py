from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from customer_intelligence.schemas.comparison import ComparisonReport
from customer_intelligence.schemas.split import SplitArtifact
from customer_intelligence.schemas.task import TaskResponse


class TrainingRunManifest(BaseModel):
    format_version: Literal[1] = 1
    run_id: UUID
    created_at: datetime
    fit_partition: Literal["train"] = "train"
    pipeline_filename: Literal["pipeline.joblib"] = "pipeline.joblib"
    pipeline_sha256: str
    package_versions: dict[str, str]
    source_sha256: dict[str, str]
    task: TaskResponse
    split: SplitArtifact
    report: ComparisonReport
    calibration: dict | None = None


class TrainingRunResponse(BaseModel):
    run_id: UUID
    created_at: datetime
    fit_partition: Literal["train"]
    report: ComparisonReport
    calibration: dict | None = None
