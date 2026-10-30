import json
import platform
import shutil
from datetime import UTC, datetime
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
from uuid import UUID, uuid4

import joblib
import numpy as np
import pandas as pd
from pydantic import ValidationError
from sklearn.pipeline import Pipeline

from customer_intelligence.schemas.comparison import ComparisonReport
from customer_intelligence.schemas.runs import TrainingRunManifest
from customer_intelligence.schemas.split import SplitArtifact
from customer_intelligence.schemas.task import TaskResponse, fingerprint_payload


def save_training_run(
    *,
    data_directory: Path,
    pipeline: Pipeline,
    report: ComparisonReport,
    task: TaskResponse,
    split: SplitArtifact,
    verification_rows: pd.DataFrame,
    calibration: dict | None = None,
) -> Path:
    if (
        report.task_id != task.id
        or report.dataset_id != task.dataset_id
        or report.dataset_sha256 != task.dataset_sha256
        or report.feature_columns != task.feature_columns
        or report.target_column != task.target_column
        or report.positive_label != task.positive_label
        or report.label_mapping != task.label_mapping
        or report.random_seed != task.random_seed
        or split.summary.task_id != task.id
        or split.summary.dataset_sha256 != task.dataset_sha256
        or report.training_row_count != split.summary.train.row_count
        or split.summary.dataset_id != task.dataset_id
        or split.summary.random_seed != task.random_seed
        or split.sklearn_version != report.sklearn_version
        or split.task_fingerprint
        != sha256(json.dumps(fingerprint_payload(task), sort_keys=True).encode("utf-8")).hexdigest()
    ):
        raise ValueError("The report, task, and saved split do not describe the same run.")

    best = max(report.results, key=lambda result: result.validation.average_precision)
    if best.model_name != report.best_validation_model or (
        report.best_validation_candidate_id
        and best.candidate_id != report.best_validation_candidate_id
    ):
        raise ValueError("The selected model does not match the comparison results.")
    if verification_rows.empty:
        raise ValueError("Supply validation rows for the serialization check.")

    package_versions = {
        name: version(name)
        for name in ("scikit-learn", "xgboost", "numpy", "scipy", "pandas", "joblib")
    }
    package_versions["python"] = platform.python_version()
    if report.sklearn_version != package_versions["scikit-learn"]:
        raise ValueError("The report uses a different scikit-learn version.")

    ml_directory = Path(__file__).resolve().parents[1] / "ml"
    source_hashes = {
        name: sha256((ml_directory / name).read_bytes()).hexdigest()
        for name in ("evaluation.py", "preprocessing.py")
    }

    run_id = uuid4()
    directory = data_directory / "runs"
    directory.mkdir(parents=True, exist_ok=True)
    staging = directory / f".{run_id}.tmp"
    destination = directory / str(run_id)
    staging.mkdir()

    try:
        pipeline_path = staging / "pipeline.joblib"
        joblib.dump(pipeline, pipeline_path, compress=3)

        # Load only the artifact this function has just created.
        restored = joblib.load(pipeline_path)
        if not isinstance(restored, Pipeline):
            raise ValueError("The restored artifact is not a fitted pipeline.")
        np.testing.assert_allclose(
            restored.predict_proba(verification_rows),
            pipeline.predict_proba(verification_rows),
            rtol=1e-12,
            atol=1e-12,
        )

        manifest = TrainingRunManifest(
            run_id=run_id,
            created_at=datetime.now(UTC),
            pipeline_sha256=sha256(pipeline_path.read_bytes()).hexdigest(),
            package_versions=package_versions,
            source_sha256=source_hashes,
            task=task,
            split=split,
            report=report,
            calibration=calibration,
        )
        (staging / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        staging.rename(destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    return destination


class RunNotFoundError(ValueError):
    pass


class RunReadError(ValueError):
    pass


def read_training_run(run_id: UUID, data_directory: Path) -> TrainingRunManifest:
    path = data_directory / "runs" / str(run_id) / "manifest.json"

    try:
        with path.open("rb") as handle:
            payload = handle.read(2_000_001)
    except FileNotFoundError as exc:
        raise RunNotFoundError("Training run not found.") from exc
    except OSError as exc:
        raise RunReadError("The saved training run could not be read.") from exc

    if len(payload) > 2_000_000:
        raise RunReadError("The saved training manifest exceeds the size limit.")

    try:
        manifest = TrainingRunManifest.model_validate_json(payload)
    except ValidationError as exc:
        raise RunReadError("The saved training manifest is invalid.") from exc

    if (
        manifest.run_id != run_id
        or manifest.report.task_id != manifest.task.id
        or manifest.report.dataset_id != manifest.task.dataset_id
        or manifest.report.dataset_sha256 != manifest.task.dataset_sha256
        or manifest.split.summary.task_id != manifest.task.id
        or not manifest.report.results
    ):
        raise RunReadError("The saved training manifest has inconsistent identifiers.")

    best = max(
        manifest.report.results,
        key=lambda result: result.validation.average_precision,
    )
    if best.model_name != manifest.report.best_validation_model or (
        manifest.report.best_validation_candidate_id
        and best.candidate_id != manifest.report.best_validation_candidate_id
    ):
        raise RunReadError("The saved model selection does not match its metrics.")

    return manifest


def load_pipeline(manifest: TrainingRunManifest, data_directory: Path) -> Pipeline:
    from customer_intelligence.core.errors import WorkflowError

    for name, recorded in manifest.package_versions.items():
        current = platform.python_version() if name == "python" else version(name)
        if current != recorded:
            raise WorkflowError(
                f"Model environment differs for {name}; retrain in this environment.", 409
            )
    path = data_directory / "runs" / str(manifest.run_id) / manifest.pipeline_filename
    if not path.is_file() or path.stat().st_size > 100_000_000:
        raise WorkflowError("The model artifact is missing or too large.", 409)
    if sha256(path.read_bytes()).hexdigest() != manifest.pipeline_sha256:
        raise WorkflowError("The model artifact checksum does not match.", 409)
    preprocessing = Path(__file__).resolve().parents[1] / "ml" / "preprocessing.py"
    if sha256(preprocessing.read_bytes()).hexdigest() != manifest.source_sha256.get(
        "preprocessing.py"
    ):
        raise WorkflowError("Preprocessing code changed; retrain before scoring.", 409)
    pipeline = joblib.load(path)
    if not isinstance(pipeline, Pipeline):
        raise WorkflowError("The model artifact is not a pipeline.", 409)
    if (
        pipeline.named_steps["preprocessing"].named_steps["schema"].feature_columns
        != manifest.task.feature_columns
    ):
        raise WorkflowError("The fitted schema differs from the saved task.", 409)
    return pipeline
