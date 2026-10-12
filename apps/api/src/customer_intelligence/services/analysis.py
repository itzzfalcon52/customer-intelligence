import json
from datetime import UTC, datetime
from uuid import UUID

import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.pipeline import Pipeline
from sqlmodel import Session

from customer_intelligence.core.config import Settings
from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.ml.diagnostics import calibration_checks, contact_curve, wilson_interval
from customer_intelligence.ml.evaluation import evaluate_binary, positive_scores
from customer_intelligence.ml.preprocessing import build_preprocessing_pipeline
from customer_intelligence.models.dataset import Dataset
from customer_intelligence.schemas.runs import TrainingRunManifest
from customer_intelligence.schemas.workflow import DiagnosticsRequest, FinalEvaluation
from customer_intelligence.services.artifacts import read_json
from customer_intelligence.services.profiling import load_dataset_frame
from customer_intelligence.services.runs import load_pipeline, read_training_run
from customer_intelligence.services.scoring import read_customers, read_score


def run_frame(session: Session, settings: Settings, run: TrainingRunManifest) -> pd.DataFrame:
    dataset = session.get(Dataset, run.task.dataset_id)
    if dataset is None:
        raise WorkflowError("The source dataset no longer exists.", 409)
    frame = load_dataset_frame(dataset, settings, expected_sha256=run.task.dataset_sha256)
    assignments = run.split.row_assignments
    positions = [i for partition in ("train", "validation", "test") for i in assignments[partition]]
    if sorted(positions) != list(range(len(frame))):
        raise WorkflowError("Saved split row assignments are inconsistent.", 409)
    return frame


def final_evaluation(session: Session, settings: Settings, run_id: UUID) -> UUID:
    path = settings.data_directory / "runs" / str(run_id) / "evaluation.json"
    if path.exists():
        existing = FinalEvaluation.model_validate(read_json(path))
        if existing.run_id != run_id:
            raise WorkflowError("Final evaluation identity mismatch.", 409)
        return run_id
    run = read_training_run(run_id, settings.data_directory)
    freeze = settings.data_directory / "finalized_tasks" / f"{run.task.id}.json"
    if freeze.exists():
        frozen = read_json(freeze)
        if not isinstance(frozen, dict) or frozen.get("run_id") != str(run_id):
            raise WorkflowError(
                "Another run already revealed final test results for this task.", 409
            )
    pipeline = load_pipeline(run, settings.data_directory)
    frame = run_frame(session, settings, run)
    test = frame.iloc[run.split.row_assignments["test"]]
    labels = [run.task.label_mapping[str(value)] for value in test[run.task.target_column]]
    scores = positive_scores(pipeline, test.loc[:, run.task.feature_columns])
    result = FinalEvaluation(
        run_id=run_id,
        evaluated_at=datetime.now(UTC),
        threshold=run.report.classification_threshold,
        frozen_candidate_id=run.report.best_validation_candidate_id
        or run.report.best_validation_model,
        metrics=evaluate_binary(labels, scores, run.report.classification_threshold),
        contact_metrics=contact_curve(labels, scores),
        calibration_checks=calibration_checks(labels, scores),
    )
    # Reserve this task before publishing metrics. If interrupted, retrying this same run is safe.
    # The single supervised worker serializes evaluation and calibration operations.
    freeze.parent.mkdir(parents=True, exist_ok=True)
    freeze_tmp = freeze.with_suffix(".tmp")
    freeze_tmp.write_text(json.dumps({"run_id": str(run_id), "task_id": str(run.task.id)}))
    freeze_tmp.replace(freeze)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(result.model_dump_json(indent=2))
    temporary.replace(path)
    return run_id


def diagnostics(session: Session, settings: Settings, request: DiagnosticsRequest) -> UUID:
    run = read_training_run(request.run_id, settings.data_directory)
    pipeline = load_pipeline(run, settings.data_directory)
    frame = run_frame(session, settings, run)
    validation = frame.iloc[run.split.row_assignments["validation"]]
    labels = [run.task.label_mapping[str(value)] for value in validation[run.task.target_column]]
    features = validation.loc[:, run.task.feature_columns]
    scores = positive_scores(pipeline, features)
    importance = permutation_importance(
        pipeline,
        features,
        labels,
        scoring="average_precision",
        n_repeats=3,
        random_state=run.task.random_seed,
        n_jobs=1,
        max_samples=min(1000, len(features)),
    )
    payload: dict = {
        "run_id": str(request.run_id),
        "partition": "validation",
        "contact_curve": [item.model_dump() for item in contact_curve(labels, scores)],
        "calibration": calibration_checks(labels, scores),
        "permutation_importance": [
            {"feature": name, "mean_ap_decrease": float(mean), "std": float(std)}
            for name, mean, std in zip(
                run.task.feature_columns,
                importance.importances_mean,
                importance.importances_std,
                strict=True,
            )
        ],
        "importance_warning": (
            "Associations, not causes; correlated features can share or hide importance."
        ),
        "segments": [],
        "heuristic": None,
    }
    if request.segment_column:
        column = request.segment_column
        if column not in frame.columns or column == run.task.target_column:
            raise WorkflowError("Choose an existing non-target segment column.")
        groups = validation[column].fillna("(missing)").astype(str)
        if groups.nunique() > 20:
            raise WorkflowError("Segment analysis supports at most 20 groups.")
        for name in sorted(groups.unique()):
            mask = (groups == name).to_numpy()
            segment_labels = np.asarray(labels)[mask].tolist()
            entry = {
                "segment": name,
                "row_count": int(mask.sum()),
                "positive_count": sum(segment_labels),
            }
            if (
                len(segment_labels) < 30
                or min(sum(segment_labels), len(segment_labels) - sum(segment_labels)) < 5
            ):
                entry["warning"] = "Insufficient observations for a meaningful binary comparison."
            else:
                metrics = evaluate_binary(
                    segment_labels,
                    np.asarray(scores)[mask].tolist(),
                    run.report.classification_threshold,
                )
                entry["metrics"] = metrics.model_dump()
                entry["accuracy_95_interval"] = wilson_interval(
                    metrics.true_positive + metrics.true_negative, metrics.row_count
                )
            payload["segments"].append(entry)
    if request.heuristic_column:
        column = request.heuristic_column
        if column not in run.task.feature_columns:
            raise WorkflowError("Heuristic must use a confirmed pre-outcome feature.")
        training = frame.iloc[run.split.row_assignments["train"]]
        train_values = pd.to_numeric(training[column], errors="coerce")
        values = pd.to_numeric(validation[column], errors="coerce")
        if train_values.isna().all() or (validation[column].notna() & values.isna()).any():
            raise WorkflowError("Heuristic column must contain numeric values.")
        heuristic_values = values.fillna(train_values.median()).to_numpy(dtype=float)
        if not np.isfinite(heuristic_values).all():
            raise WorkflowError("Heuristic values must be finite.")
        heuristic_scores = (
            heuristic_values if request.heuristic_direction == "higher_risk" else -heuristic_values
        )
        payload["heuristic"] = {
            "column": column,
            "direction": request.heuristic_direction,
            "average_precision": float(average_precision_score(labels, heuristic_scores)),
            "warning": "A user-specified ranking rule, not calibrated churn probabilities.",
        }
    # Separate requests may compare segments/rules without changing the frozen model.
    analysis_id = request.idempotency_key
    payload["id"] = str(analysis_id)
    from customer_intelligence.services.artifacts import publish_json

    destination = settings.data_directory / "analyses" / str(analysis_id)
    if not destination.exists():
        publish_json(destination.parent, {"manifest.json": payload}, analysis_id)
    return analysis_id


def customer_explanation(
    session: Session, settings: Settings, score_id: UUID, row_reference: int, explanation_id: UUID
) -> UUID:
    score = read_score(score_id, settings.data_directory)
    customers = read_customers(score, settings.data_directory)
    customer = next((row for row in customers if row.row_reference == row_reference), None)
    if customer is None:
        raise WorkflowError("Scoring row not found.", 404)
    run = read_training_run(score.run_id, settings.data_directory)
    pipeline = load_pipeline(run, settings.data_directory)
    training_frame = run_frame(session, settings, run).iloc[run.split.row_assignments["train"]]
    dataset = session.get(Dataset, score.dataset_id)
    if dataset is None:
        raise WorkflowError("Scoring dataset not found.", 404)
    frame = load_dataset_frame(dataset, settings, expected_sha256=score.dataset_sha256)
    row = frame.iloc[[row_reference - 1]].loc[:, run.task.feature_columns]
    schema = pipeline.named_steps["preprocessing"].named_steps["schema"]
    effects: list[dict] = []
    for feature in run.task.feature_columns:
        values = training_frame[feature].dropna()
        reference = (
            str(pd.to_numeric(values).median())
            if feature in schema.numeric_columns_
            else str(values.mode().iloc[0])
        )
        alternative = row.copy()
        alternative[feature] = reference
        alternative_score = positive_scores(pipeline, alternative)[0]
        effects.append(
            {
                "feature": feature,
                "reference_value": reference,
                "risk_score_change_if_replaced": alternative_score - customer.risk_score,
            }
        )
    payload = {
        "id": str(explanation_id),
        "score_id": str(score_id),
        "run_id": str(score.run_id),
        "row_reference": row_reference,
        "risk_score": customer.risk_score,
        "method": "one_feature_reference_perturbation",
        "effects": sorted(effects, key=lambda item: -abs(item["risk_score_change_if_replaced"])),
        "warning": (
            "Model sensitivity, not causal effects or additive SHAP attribution. "
            "Correlated-feature substitutions may be unrealistic."
        ),
    }
    from customer_intelligence.services.artifacts import publish_json

    publish_json(settings.data_directory / "analyses", {"manifest.json": payload}, explanation_id)
    return explanation_id


def leakage_demonstration(
    session: Session, settings: Settings, task_id: UUID, demonstration_id: UUID
) -> UUID:
    from customer_intelligence.services.artifacts import publish_json
    from customer_intelligence.services.training import task_partitions

    task, split, frame = task_partitions(session, settings, task_id)
    training = frame.iloc[split.row_assignments["train"]]
    validation = frame.iloc[split.row_assignments["validation"]]
    labels_train = [task.label_mapping[str(v)] for v in training[task.target_column]]
    labels_validation = [task.label_mapping[str(v)] for v in validation[task.target_column]]
    results = {}
    for leaked in (False, True):
        train_features = training.loc[:, task.feature_columns].copy()
        valid_features = validation.loc[:, task.feature_columns].copy()
        if leaked:
            # Deliberately invalid feature for a clearly labeled teaching experiment.
            train_features["__synthetic_post_outcome"] = [str(v) for v in labels_train]
            valid_features["__synthetic_post_outcome"] = [str(v) for v in labels_validation]
        pipeline = Pipeline(
            [
                ("preprocessing", build_preprocessing_pipeline(train_features.columns.tolist())),
                ("model", LogisticRegression(max_iter=2000, random_state=task.random_seed)),
            ]
        )
        pipeline.fit(train_features, labels_train)
        results["with_leakage" if leaked else "without_leakage"] = evaluate_binary(
            labels_validation, positive_scores(pipeline, valid_features)
        ).model_dump()
    payload = {
        "id": str(demonstration_id),
        "task_id": str(task_id),
        "partition": "validation",
        "results": results,
        "test_evaluated": False,
        "warning": (
            "The synthetic feature copies outcomes. This deliberately invalid "
            "model is never saved for customer scoring."
        ),
    }
    publish_json(settings.data_directory / "analyses", {"manifest.json": payload}, demonstration_id)
    return demonstration_id
