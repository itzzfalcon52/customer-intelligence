from uuid import UUID

from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sqlmodel import Session

from customer_intelligence.core.config import Settings
from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.ml.diagnostics import calibration_checks
from customer_intelligence.ml.evaluation import positive_scores
from customer_intelligence.services.analysis import run_frame
from customer_intelligence.services.runs import load_pipeline, read_training_run, save_training_run


def calibrate_run(session: Session, settings: Settings, run_id: UUID) -> UUID:
    run = read_training_run(run_id, settings.data_directory)
    if (settings.data_directory / "finalized_tasks" / f"{run.task.id}.json").exists():
        raise WorkflowError(
            "This task has revealed final test results; calibration is frozen.", 409
        )
    if run.calibration is not None:
        raise WorkflowError("This run is already calibrated.", 409)
    pipeline = load_pipeline(run, settings.data_directory)
    frame = run_frame(session, settings, run)
    positions = run.split.row_assignments["validation"]
    labels = [
        run.task.label_mapping[str(value)]
        for value in frame.iloc[positions][run.task.target_column]
    ]
    if min(labels.count(0), labels.count(1)) < 10:
        raise WorkflowError("Calibration needs at least ten examples of each validation class.")
    fit_positions, diagnostic_positions = train_test_split(
        positions,
        test_size=0.5,
        stratify=labels,
        random_state=run.task.random_seed,
    )
    fitting = frame.iloc[fit_positions]
    diagnostic = frame.iloc[diagnostic_positions]
    preprocessing = pipeline.named_steps["preprocessing"]
    model = CalibratedClassifierCV(FrozenEstimator(pipeline.named_steps["model"]), method="sigmoid")
    model.fit(
        preprocessing.transform(fitting.loc[:, run.task.feature_columns]),
        [run.task.label_mapping[str(v)] for v in fitting[run.task.target_column]],
    )
    calibrated = Pipeline([("preprocessing", preprocessing), ("model", model)])
    diagnostic_labels = [run.task.label_mapping[str(v)] for v in diagnostic[run.task.target_column]]
    metadata = {
        "source_run_id": str(run_id),
        "method": "sigmoid",
        "fit_partition": "validation_subset",
        "fit_row_assignments": fit_positions,
        "diagnostic_row_assignments": diagnostic_positions,
        "uncalibrated": calibration_checks(
            diagnostic_labels, positive_scores(pipeline, diagnostic)
        ),
        "calibrated": calibration_checks(
            diagnostic_labels, positive_scores(calibrated, diagnostic)
        ),
        "warning": (
            "The comparison report describes base-model selection before "
            "calibration. Development diagnostics share data used for model "
            "selection and are not unbiased final-test estimates."
        ),
    }
    destination = save_training_run(
        data_directory=settings.data_directory,
        pipeline=calibrated,
        report=run.report,
        task=run.task,
        split=run.split,
        verification_rows=diagnostic.head(20),
        calibration=metadata,
    )
    return UUID(destination.name)
