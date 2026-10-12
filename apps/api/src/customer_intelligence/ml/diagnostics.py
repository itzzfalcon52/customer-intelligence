import math

import numpy as np
from sklearn.metrics import brier_score_loss

from customer_intelligence.schemas.workflow import ContactMetrics


def contact_metrics(labels: list[int], scores: list[float], k: int) -> ContactMetrics:
    if len(labels) != len(scores) or not 1 <= k <= len(labels):
        raise ValueError("Contact count must be between one and the evaluation row count.")
    positives = sum(labels)
    if positives == 0:
        raise ValueError("Contact metrics require positive labels.")
    order = np.argsort(-np.asarray(scores), kind="stable")
    tp = int(np.asarray(labels)[order[:k]].sum())
    precision = tp / k
    return ContactMetrics(
        k=k,
        true_positive=tp,
        precision=precision,
        recall=tp / positives,
        lift=precision / (positives / len(labels)),
    )


def contact_curve(labels: list[int], scores: list[float]) -> list[ContactMetrics]:
    sizes = sorted(
        {max(1, math.ceil(len(labels) * fraction)) for fraction in (0.05, 0.1, 0.2, 0.5, 1)}
    )
    return [contact_metrics(labels, scores, k) for k in sizes]


def calibration_checks(labels: list[int], scores: list[float]) -> dict:
    values = np.asarray(scores)
    buckets = np.minimum((values * 10).astype(int), 9)
    bins = []
    for number in range(10):
        mask = buckets == number
        count = int(mask.sum())
        bins.append(
            {
                "lower": number / 10,
                "upper": (number + 1) / 10,
                "count": count,
                "mean_score": float(values[mask].mean()) if count else None,
                "observed_positive_rate": float(np.asarray(labels)[mask].mean()) if count else None,
            }
        )
    return {
        "brier_score": float(brier_score_loss(labels, scores)),
        "bins": bins,
        "calibration_fitted": False,
        "warning": "These are development diagnostics, not proof of calibrated probabilities.",
    }


def wilson_interval(successes: int, count: int) -> list[float] | None:
    if not count:
        return None
    p = successes / count
    z = 1.95996398454
    denominator = 1 + z * z / count
    center = (p + z * z / (2 * count)) / denominator
    spread = z * math.sqrt(p * (1 - p) / count + z * z / (4 * count * count)) / denominator
    return [max(0.0, center - spread), min(1.0, center + spread)]
