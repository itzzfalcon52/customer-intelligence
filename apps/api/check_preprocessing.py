import argparse
from uuid import UUID

import numpy as np
import pandas as pd
from sqlmodel import Session

from customer_intelligence.core.config import get_settings
from customer_intelligence.core.database import engine
from customer_intelligence.ml.preprocessing import (
    PreprocessingError,
    build_preprocessing_pipeline,
)
from customer_intelligence.models.dataset import Dataset
from customer_intelligence.models.task import Task
from customer_intelligence.schemas.split import SplitArtifact
from customer_intelligence.services.profiling import load_dataset_frame
from customer_intelligence.services.splits import prepare_split


def check_training_only_fit() -> None:
    training = pd.DataFrame(
        {"amount": ["1", "3", None], "plan": ["A", "B", "A"]},
        dtype="string",
    )
    pipeline = build_preprocessing_pipeline(["amount", "plan"])
    pipeline.fit(training)

    validation = pd.DataFrame(
        {"amount": ["999", None], "plan": ["NEW", "B"]},
        dtype="string",
    )
    transformed = pipeline.transform(validation)
    numeric = pipeline.named_steps["columns"].named_transformers_["numeric"]
    categorical = pipeline.named_steps["columns"].named_transformers_["categorical"]

    assert numeric.named_steps["imputer"].statistics_.tolist() == [2.0]
    assert categorical.named_steps["encoder"].categories_[0].tolist() == ["A", "B"]
    assert transformed.shape == (2, 3)

    invalid = pd.DataFrame({"amount": ["oops"], "plan": ["A"]}, dtype="string")
    try:
        pipeline.transform(invalid)
    except PreprocessingError:
        pass
    else:
        raise AssertionError("Invalid numeric input was accepted.")


def main(task_id: UUID) -> None:
    settings = get_settings()
    path = settings.data_directory / "splits" / f"{task_id}.json"
    if not path.is_file():
        raise ValueError("Create the saved split through the API first.")

    with Session(engine) as session:
        task = session.get(Task, task_id)
        if task is None:
            raise ValueError("Task not found.")
        dataset = session.get(Dataset, task.dataset_id)
        if dataset is None:
            raise ValueError("Dataset not found.")

        # Verify that the saved split still matches the task and dataset.
        prepare_split(task, dataset, settings)
        artifact = SplitArtifact.model_validate_json(path.read_text(encoding="utf-8"))
        frame = load_dataset_frame(dataset, settings, expected_sha256=task.dataset_sha256)
        features = list(task.feature_columns)

    training = frame.iloc[artifact.row_assignments["train"]].loc[:, features]
    validation = frame.iloc[artifact.row_assignments["validation"]].loc[:, features]

    pipeline = build_preprocessing_pipeline(features)
    training_matrix = pipeline.fit_transform(training)
    validation_matrix = pipeline.transform(validation)

    assert training_matrix.shape[0] == len(training)
    assert validation_matrix.shape[0] == len(validation)
    assert training_matrix.shape[1] == validation_matrix.shape[1]
    assert bool(np.isfinite(training_matrix.data).all())
    assert bool(np.isfinite(validation_matrix.data).all())

    schema = pipeline.named_steps["schema"]
    print("Numeric columns:", schema.numeric_columns_)
    print("Categorical columns:", schema.categorical_columns_)
    print("Training matrix:", training_matrix.shape)
    print("Validation matrix:", validation_matrix.shape)

    check_training_only_fit()
    print("Preprocessing checks passed. No classifier trained; test partition reserved.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("task_id", type=UUID)
    arguments = parser.parse_args()
    main(arguments.task_id)