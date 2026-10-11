import warnings

import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, confusion_matrix, roc_auc_score
from sklearn.pipeline import Pipeline

from customer_intelligence.ml.preprocessing import build_preprocessing_pipeline
from customer_intelligence.schemas.comparison import BinaryMetrics, ModelName, ModelResult


class ModelEvaluationError(ValueError):
    pass


def evaluate_binary(
    labels: list[int],
    scores: list[float],
    threshold: float = 0.5,
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
    tn, fp, fn, tp = (
        int(value)
        for value in confusion_matrix(labels, predictions, labels=[0, 1]).ravel()
    )
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


def compare_models(
    training: pd.DataFrame,
    training_labels: list[int],
    validation: pd.DataFrame,
    validation_labels: list[int],
    feature_columns: list[str],
    random_seed: int,
    threshold: float = 0.5,
) -> list[ModelResult]:
    if len(training) != len(training_labels) or len(validation) != len(validation_labels):
        raise ModelEvaluationError("Features and labels must have matching row counts.")
    if set(training_labels) != {0, 1} or set(validation_labels) != {0, 1}:
        raise ModelEvaluationError("Training and validation must both contain both classes.")

    candidates: list[
        tuple[ModelName, DummyClassifier | LogisticRegression, dict[str, int | float | str]]
    ] = [
        ("dummy_prior", DummyClassifier(strategy="prior"), {"strategy": "prior"}),
        (
            "logistic_regression",
            LogisticRegression(C=1.0, solver="lbfgs", max_iter=2000, random_state=random_seed),
            {"C": 1.0, "solver": "lbfgs", "max_iter": 2000, "random_state": random_seed},
        ),
    ]
    results: list[ModelResult] = []

    for name, estimator, parameters in candidates:
        # A fresh preprocessing pipeline is fitted separately for each candidate.
        pipeline = Pipeline(
            steps=[
                ("preprocessing", build_preprocessing_pipeline(feature_columns)),
                ("model", estimator),
            ]
        )

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", ConvergenceWarning)
                pipeline.fit(training, training_labels)
        except ConvergenceWarning as exc:
            raise ModelEvaluationError(
                f"{name} did not converge. Resolve this before comparing its metrics."
            ) from exc

        classes = pipeline.named_steps["model"].classes_.tolist()
        positive_index = classes.index(1)
        scores = pipeline.predict_proba(validation)[:, positive_index].tolist()
        metrics = evaluate_binary(validation_labels, scores, threshold)

        notes = []
        if metrics.predicted_positive_count == 0:
            notes.append(
                "No positive predictions at this threshold; precision is undefined."
            )

        results.append(
            ModelResult(
                model_name=name,
                parameters=parameters,
                validation=metrics,
                warnings=notes,
            )
        )

    return results