from collections.abc import Callable
from pathlib import Path
from uuid import UUID

import sklearn
from sqlmodel import Session

from customer_intelligence.core.config import Settings
from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.ml.evaluation import fit_and_compare_models
from customer_intelligence.models.dataset import Dataset
from customer_intelligence.models.task import Task
from customer_intelligence.schemas.comparison import ComparisonReport
from customer_intelligence.schemas.split import SplitArtifact
from customer_intelligence.schemas.task import TaskResponse
from customer_intelligence.services.profiling import load_dataset_frame
from customer_intelligence.services.runs import save_training_run
from customer_intelligence.services.splits import prepare_split


def task_partitions(session: Session, settings: Settings, task_id: UUID) -> tuple:
    task = session.get(Task, task_id)
    if task is None:
        raise WorkflowError("Task not found.", 404)
    dataset = session.get(Dataset, task.dataset_id)
    if dataset is None:
        raise WorkflowError("Training dataset not found.", 404)
    prepare_split(task, dataset, settings)
    split = SplitArtifact.model_validate_json(
        (settings.data_directory / "splits" / f"{task_id}.json").read_bytes()
    )
    frame = load_dataset_frame(dataset, settings, expected_sha256=task.dataset_sha256)
    return task, split, frame


def train_task(
    session: Session,
    settings: Settings,
    task_id: UUID,
    search_trials: int = 0,
    threshold: float = 0.5,
    progress: Callable[[str], None] | None = None,
) -> Path:
    if (settings.data_directory / "finalized_tasks" / f"{task_id}.json").exists():
        raise WorkflowError(
            "Final test results were revealed for this task; training is frozen.", 409
        )
    task, split, frame = task_partitions(session, settings, task_id)
    training = frame.iloc[split.row_assignments["train"]]
    validation = frame.iloc[split.row_assignments["validation"]]
    outcome = fit_and_compare_models(
        training.loc[:, task.feature_columns],
        [task.label_mapping[str(v)] for v in training[task.target_column]],
        validation.loc[:, task.feature_columns],
        [task.label_mapping[str(v)] for v in validation[task.target_column]],
        list(task.feature_columns),
        task.random_seed,
        threshold,
        search_trials,
        progress,
    )
    best = max(outcome.results, key=lambda result: result.validation.average_precision)
    baseline = next(
        (r.validation.average_precision for r in outcome.results if r.model_name == "dummy_prior"),
        None,
    )
    report = ComparisonReport(
        task_id=task.id,
        dataset_id=task.dataset_id,
        dataset_sha256=task.dataset_sha256,
        sklearn_version=sklearn.__version__,
        random_seed=task.random_seed,
        target_column=task.target_column,
        positive_label=task.positive_label,
        feature_columns=list(task.feature_columns),
        label_mapping=dict(task.label_mapping),
        training_row_count=len(training),
        classification_threshold=threshold,
        best_validation_model=best.model_name,
        best_validation_candidate_id=best.candidate_id,
        results=outcome.results,
        failures=outcome.failures,
        selection_warning=(
            "No successful dummy baseline is available."
            if baseline is None
            else "No candidate improves on the dummy baseline."
            if best.validation.average_precision <= baseline
            else None
        ),
    )
    if progress:
        progress("saving_model")
    return save_training_run(
        data_directory=settings.data_directory,
        pipeline=outcome.best_pipeline,
        report=report,
        task=TaskResponse.model_validate(task),
        split=split,
        verification_rows=validation.loc[:, task.feature_columns].head(20),
    )
