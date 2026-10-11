from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

ModelName = Literal["dummy_prior", "logistic_regression"]


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


class ModelResult(BaseModel):
    model_name: ModelName
    parameters: dict[str, int | float | str]
    validation: BinaryMetrics
    warnings: list[str] = Field(default_factory=list)


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
    test_evaluated: Literal[False] = False