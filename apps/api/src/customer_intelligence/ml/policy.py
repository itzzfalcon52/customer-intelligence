"""Decision policies are tuned on training out-of-fold scores, never test labels."""

import numpy as np
import pandas as pd
from sklearn.metrics import precision_recall_curve
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import Pipeline

from customer_intelligence.ml.evaluation import evaluate_binary, positive_scores


def threshold_table(labels: list[int], scores: list[float]) -> list[dict]:
    return [
        {"threshold": round(float(t), 2), **evaluate_binary(labels, scores, float(t)).model_dump()}
        for t in np.arange(0.1, 1, 0.05)
    ]


def select_threshold(
    pipeline: Pipeline,
    training: pd.DataFrame,
    labels: list[int],
    validation: pd.DataFrame,
    validation_labels: list[int],
    policy: str,
    fixed: float,
    minimum_recall: float,
    seed: int,
) -> dict:
    if policy not in {"fixed", "f1", "precision_at_recall"}:
        raise ValueError("Unsupported decision policy.")
    threshold = fixed
    details: dict = {"source": "user_fixed", "minimum_recall": minimum_recall}
    if policy != "fixed":
        if min(labels.count(0), labels.count(1)) < 3:
            raise ValueError("Threshold tuning requires three training examples per class.")
        oof = cross_val_predict(
            pipeline,
            training,
            labels,
            method="predict_proba",
            n_jobs=1,
            cv=StratifiedKFold(3, shuffle=True, random_state=seed),
        )[:, 1]
        precision, recall, thresholds = precision_recall_curve(labels, oof)
        p, rec = precision[:-1], recall[:-1]
        objective = (
            (2 * p * rec / np.maximum(p + rec, 1e-15))
            if policy == "f1"
            else np.where(rec >= minimum_recall, p, -1)
        )
        # Ties favour recall (ascending thresholds), rather than a tiny high-precision tail.
        chosen = int(np.argmax(objective))
        threshold = float(thresholds[chosen])
        details = {
            "source": "training_3_fold_oof",
            "minimum_recall": minimum_recall,
            "oof_metrics": evaluate_binary(labels, oof.tolist(), threshold).model_dump(),
        }
    return {
        "policy": policy,
        "threshold": threshold,
        **details,
        "validation_curve": threshold_table(
            validation_labels, positive_scores(pipeline, validation)
        ),
        "warning": (
            "Development diagnostics after model selection; not an "
            "unbiased final estimate. Test partition remains reserved."
        ),
    }
