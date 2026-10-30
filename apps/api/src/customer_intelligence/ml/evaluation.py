import time
import warnings
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, confusion_matrix, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.pipeline import Pipeline
from xgboost import XGBClassifier

from customer_intelligence.ml.preprocessing import build_preprocessing_pipeline
from customer_intelligence.schemas.comparison import (
    BinaryMetrics,
    ModelFailure,
    ModelName,
    ModelResult,
)


class ModelEvaluationError(ValueError):
    pass


@dataclass
class FittedComparison:
    results: list[ModelResult]
    best_pipeline: Pipeline
    failures: list[ModelFailure] = field(default_factory=list)
    validation_scores: dict[str, list[float]] = field(default_factory=dict)


def evaluate_binary(
    labels: list[int], scores: list[float], threshold: float = 0.5
) -> BinaryMetrics:
    if len(labels) != len(scores) or set(labels) != {0, 1}:
        raise ModelEvaluationError("Evaluation needs aligned rows and both binary classes.")
    if not 0 <= threshold <= 1:
        raise ModelEvaluationError("The threshold must be between zero and one.")
    values = np.asarray(scores, dtype=float)
    if values.ndim != 1 or not bool(np.isfinite(values).all()):
        raise ModelEvaluationError("Scores must be finite, one-dimensional values.")
    if bool(((values < 0) | (values > 1)).any()):
        raise ModelEvaluationError("Scores must be between zero and one.")
    predictions = (values >= threshold).astype(int)
    tn, fp, fn, tp = (int(v) for v in confusion_matrix(labels, predictions, labels=[0, 1]).ravel())
    predicted_positive = tp + fp
    return BinaryMetrics(
        row_count=len(labels),
        positive_count=tp + fn,
        predicted_positive_count=predicted_positive,
        accuracy=(tp + tn) / len(labels),
        precision=tp / predicted_positive if predicted_positive else None,
        recall=tp / (tp + fn),
        f1=2 * tp / (2 * tp + fp + fn),
        roc_auc=float(roc_auc_score(labels, values)),
        average_precision=float(average_precision_score(labels, values)),
        true_negative=tn,
        false_positive=fp,
        false_negative=fn,
        true_positive=tp,
    )


def positive_scores(pipeline: Pipeline, frame: pd.DataFrame) -> list[float]:
    classes = pipeline.named_steps["model"].classes_.tolist()
    return pipeline.predict_proba(frame)[:, classes.index(1)].tolist()


def candidate_specs(random_seed: int, search_trials: int = 0) -> list[tuple[ModelName, str, dict]]:
    if not 0 <= search_trials <= 8:
        raise ModelEvaluationError("Parameter search is limited to eight extra trials.")
    specs: list[tuple[ModelName, str, dict]] = [
        ("dummy_prior", "dummy_prior", {"strategy": "prior"}),
        (
            "logistic_regression",
            "logistic_regression",
            {"C": 1.0, "solver": "lbfgs", "max_iter": 2000, "random_state": random_seed},
        ),
        (
            "random_forest",
            "random_forest",
            {
                "n_estimators": 200,
                "max_depth": 8,
                "min_samples_leaf": 5,
                "n_jobs": 2,
                "random_state": random_seed,
            },
        ),
        (
            "xgboost",
            "xgboost",
            {
                "n_estimators": 250,
                "max_depth": 3,
                "learning_rate": 0.05,
                "subsample": 0.8,
                "colsample_bytree": 0.8,
                "reg_lambda": 1.0,
                "objective": "binary:logistic",
                "eval_metric": "logloss",
                "tree_method": "hist",
                "device": "cpu",
                "n_jobs": 2,
                "random_state": random_seed,
            },
        ),
    ]
    variants: list[tuple[int, dict]] = [
        (3, {"max_depth": 2, "n_estimators": 400, "reg_lambda": 5.0}),
        (1, {"C": 0.1}),
        (2, {"max_depth": 6, "min_samples_leaf": 10}),
        (3, {"max_depth": 4, "min_child_weight": 5, "reg_lambda": 5.0}),
        (1, {"C": 10.0, "class_weight": "balanced"}),
        (2, {"max_depth": 12, "min_samples_leaf": 10, "class_weight": "balanced"}),
        (3, {"max_depth": 2, "learning_rate": 0.03, "n_estimators": 600}),
        (1, {"C": 1.0, "class_weight": "balanced"}),
    ]
    for number, (index, changes) in enumerate(variants[:search_trials], start=1):
        name, _, parameters = specs[index]
        specs.append((name, f"{name}:trial_{number}", {**parameters, **changes}))
    return specs


def fit_and_compare_models(
    training: pd.DataFrame,
    training_labels: list[int],
    validation: pd.DataFrame,
    validation_labels: list[int],
    feature_columns: list[str],
    random_seed: int,
    threshold: float = 0.5,
    search_trials: int = 0,
    progress: Callable[[str], None] | None = None,
    cv_folds: int = 0,
) -> FittedComparison:
    if len(training) != len(training_labels) or len(validation) != len(validation_labels):
        raise ModelEvaluationError("Features and labels must have matching row counts.")
    if set(training_labels) != {0, 1} or set(validation_labels) != {0, 1}:
        raise ModelEvaluationError("Training and validation must both contain both classes.")
    if not 0 <= threshold <= 1:
        raise ModelEvaluationError("The threshold must be between zero and one.")
    if cv_folds not in {0, 3, 5}:
        raise ModelEvaluationError("Choose zero, three or five training CV folds.")
    if cv_folds and min(training_labels.count(0), training_labels.count(1)) < cv_folds:
        raise ModelEvaluationError("Too few examples per class for training cross-validation.")
    results: list[ModelResult] = []
    failures: list[ModelFailure] = []
    best_pipeline: Pipeline | None = None
    best_score = -1.0
    validation_scores: dict[str, list[float]] = {}
    factories = {
        "dummy_prior": DummyClassifier,
        "logistic_regression": LogisticRegression,
        "random_forest": RandomForestClassifier,
        "xgboost": XGBClassifier,
    }
    for name, candidate_id, parameters in candidate_specs(random_seed, search_trials):
        if progress:
            progress(f"training:{candidate_id}")
        started = time.monotonic()
        pipeline = Pipeline(
            [
                ("preprocessing", build_preprocessing_pipeline(feature_columns)),
                ("model", factories[name](**parameters)),
            ]
        )
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", ConvergenceWarning)
                cv_scores = None
                if cv_folds:
                    if progress:
                        progress(f"cross_validation:{candidate_id}")
                    cv_scores = cross_val_score(
                        pipeline,
                        training,
                        training_labels,
                        cv=StratifiedKFold(cv_folds, shuffle=True, random_state=random_seed),
                        scoring="average_precision",
                        n_jobs=1,
                        error_score="raise",
                    )
                pipeline.fit(training, training_labels)
            scores = positive_scores(pipeline, validation)
            metrics = evaluate_binary(validation_labels, scores, threshold)
            validation_scores[candidate_id] = scores
        except (ValueError, RuntimeError, ConvergenceWarning) as exc:
            failures.append(
                ModelFailure(
                    model_name=name,
                    candidate_id=candidate_id,
                    error=(
                        f"Candidate failed ({type(exc).__name__}); "
                        "check preprocessing or convergence."
                    ),
                    elapsed_seconds=time.monotonic() - started,
                )
            )
            continue
        notes = []
        if metrics.predicted_positive_count == 0:
            notes.append("No positive predictions at this threshold; precision is undefined.")
        results.append(
            ModelResult(
                model_name=name,
                candidate_id=candidate_id,
                parameters=parameters,
                elapsed_seconds=time.monotonic() - started,
                validation=metrics,
                training_cv_average_precision=float(np.mean(cv_scores))
                if cv_scores is not None
                else None,
                training_cv_std=float(np.std(cv_scores)) if cv_scores is not None else None,
                warnings=notes,
            )
        )
        if metrics.average_precision > best_score:
            best_pipeline, best_score = pipeline, metrics.average_precision
    if best_pipeline is None:
        raise ModelEvaluationError("All candidates failed. Review the feature schema and data.")
    return FittedComparison(results, best_pipeline, failures, validation_scores)


def compare_models(
    training: pd.DataFrame,
    training_labels: list[int],
    validation: pd.DataFrame,
    validation_labels: list[int],
    feature_columns: list[str],
    random_seed: int,
    threshold: float = 0.5,
) -> list[ModelResult]:
    return fit_and_compare_models(
        training,
        training_labels,
        validation,
        validation_labels,
        feature_columns,
        random_seed,
        threshold,
    ).results
