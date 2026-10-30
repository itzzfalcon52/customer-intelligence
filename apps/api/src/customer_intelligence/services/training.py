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
    cv_folds: int = 0,
    threshold_policy: str = "fixed",
    minimum_recall: float = 0.5,
) -> Path:
    if (settings.data_directory / "finalized_tasks" / f"{task_id}.json").exists():
        raise WorkflowError(
            "Final test results were revealed for this task; training is frozen.", 409
        )
    task, split, frame = task_partitions(session, settings, task_id)
    from customer_intelligence.ml.schema_checks import obvious_leakage

    leaked = [c for c in task.feature_columns if obvious_leakage(c)]
    if leaked:
        raise WorkflowError(
            f"Post-outcome fields cannot be trained: {leaked}. Review the schema "
            f"and create a corrected task."
        )
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
        cv_folds,
    )
    from customer_intelligence.ml.policy import select_threshold

    policy = select_threshold(
        outcome.best_pipeline,
        training.loc[:, task.feature_columns],
        [task.label_mapping[str(v)] for v in training[task.target_column]],
        validation.loc[:, task.feature_columns],
        [task.label_mapping[str(v)] for v in validation[task.target_column]],
        threshold_policy,
        threshold,
        minimum_recall,
        task.random_seed,
    )
    threshold = policy["threshold"]
    if threshold_policy != "fixed":
        from customer_intelligence.ml.evaluation import evaluate_binary

        for result in outcome.results:
            result.validation = evaluate_binary(
                [task.label_mapping[str(v)] for v in validation[task.target_column]],
                outcome.validation_scores[result.candidate_id],
                threshold,
            )
            result.warnings = [
                w for w in result.warnings if not w.startswith("No positive predictions")
            ]
            if result.validation.predicted_positive_count == 0:
                result.warnings.append(
                    "No positive predictions at this threshold; precision is undefined."
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
        training_cv_folds=cv_folds,
        threshold_policy=threshold_policy,
        threshold_selection=policy,
        selection_warning=(
            "No successful dummy baseline is available."
            if baseline is None
            else "No candidate improves on the dummy baseline."
            if best.validation.average_precision <= baseline
            else None
        ),
    )
    from customer_intelligence.services.retention_brief import computed_briefing

    report.executive_briefing = computed_briefing(report)
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
