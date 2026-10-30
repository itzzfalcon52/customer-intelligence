from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

ModelName = Literal[
    "dummy_prior",
    "logistic_regression",
    "random_forest",
    "xgboost",
]


class BinaryMetrics(BaseModel):
    row_count: int
    positive_count: int
    predicted_positive_count: int
    accuracy: float
    precision: float | None
    recall: float
    f1: float
    roc_auc: float
    average_precision: float
    true_negative: int
    false_positive: int
    false_negative: int
    true_positive: int


class ModelFailure(BaseModel):
    model_name: ModelName
    candidate_id: str
    error: str
    elapsed_seconds: float


class ModelResult(BaseModel):
    model_name: ModelName
    candidate_id: str = ""
    elapsed_seconds: float = 0
    parameters: dict[str, int | float | str]
    validation: BinaryMetrics
    warnings: list[str] = Field(default_factory=list)
    training_cv_average_precision: float | None = None
    training_cv_std: float | None = None


class ComparisonReport(BaseModel):
    task_id: UUID
    dataset_id: UUID
    dataset_sha256: str
    sklearn_version: str
    random_seed: int
    target_column: str
    positive_label: str
    feature_columns: list[str]
    label_mapping: dict[str, int]
    training_row_count: int
    evaluation_partition: Literal["validation"] = "validation"
    selection_metric: Literal["average_precision"] = "average_precision"
    classification_threshold: float = 0.5
    best_validation_model: ModelName
    results: list[ModelResult]
    best_validation_candidate_id: str | None = None
    failures: list[ModelFailure] = Field(default_factory=list)
    selection_warning: str | None = None
    training_cv_folds: int = 0
    threshold_policy: str = "fixed"
    threshold_selection: dict = Field(default_factory=dict)
    executive_briefing: dict = Field(default_factory=dict)
    test_evaluated: Literal[False] = False
