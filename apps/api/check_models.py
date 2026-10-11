import argparse
from uuid import UUID

import sklearn
from sqlmodel import Session

from customer_intelligence.core.config import get_settings
from customer_intelligence.core.database import engine
from customer_intelligence.ml.evaluation import compare_models, evaluate_binary
from customer_intelligence.models.dataset import Dataset
from customer_intelligence.models.task import Task
from customer_intelligence.schemas.comparison import ComparisonReport
from customer_intelligence.schemas.split import SplitArtifact
from customer_intelligence.services.profiling import load_dataset_frame
from customer_intelligence.services.splits import prepare_split


def check_metrics() -> None:
    perfect = evaluate_binary([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9])
    assert perfect.average_precision == 1.0
    assert perfect.roc_auc == 1.0
    assert perfect.true_positive == 2
    assert perfect.false_positive == 0

    constant = evaluate_binary([0, 0, 0, 1], [0.25] * 4)
    assert constant.average_precision == 0.25
    assert constant.roc_auc == 0.5
    assert constant.accuracy == 0.75
    assert constant.precision is None
    assert constant.recall == 0.0


def main(task_id: UUID) -> None:
    check_metrics()
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

        prepare_split(task, dataset, settings)
        artifact = SplitArtifact.model_validate_json(path.read_text(encoding="utf-8"))
        frame = load_dataset_frame(dataset, settings, expected_sha256=task.dataset_sha256)

        training = frame.iloc[artifact.row_assignments["train"]]
        validation = frame.iloc[artifact.row_assignments["validation"]]

        training_labels = [
            task.label_mapping[str(value)] for value in training[task.target_column]
        ]
        validation_labels = [
            task.label_mapping[str(value)] for value in validation[task.target_column]
        ]

        results = compare_models(
            training=training.loc[:, task.feature_columns],
            training_labels=training_labels,
            validation=validation.loc[:, task.feature_columns],
            validation_labels=validation_labels,
            feature_columns=list(task.feature_columns),
            random_seed=task.random_seed,
        )
        best = max(results, key=lambda result: result.validation.average_precision)

        report = ComparisonReport(
            task_id=task.id,
            dataset_id=dataset.id,
            dataset_sha256=task.dataset_sha256,
            sklearn_version=sklearn.__version__,
            random_seed=task.random_seed,
            target_column=task.target_column,
            positive_label=task.positive_label,
            feature_columns=list(task.feature_columns),
            label_mapping=dict(task.label_mapping),
            training_row_count=len(training),
            best_validation_model=best.model_name,
            results=results,
        )

    print(report.model_dump_json(indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("task_id", type=UUID)
    arguments = parser.parse_args()
    main(arguments.task_id)
    