"""Deterministic analyses the investigator may request. No model or LLM computes these numbers.

All functions receive development rows only (train + validation); the final test partition stays
reserved. Results describe associations in historical data, never causes.
"""

import math
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency

from customer_intelligence.ml.diagnostics import wilson_interval
from customer_intelligence.schemas.retention import RuleCondition

MIN_GROUP = 30  # below this a group's churn rate is too noisy to compare
MAX_GROUPS = 12


class AnalysisError(ValueError):
    pass


def _rate(positives: int, count: int) -> dict[str, Any]:
    interval = wilson_interval(positives, count)
    return {
        "rows": count,
        "churned": positives,
        "churn_rate": round(positives / count, 4) if count else None,
        "churn_rate_95ci": [round(v, 4) for v in interval] if interval else None,
    }


def _numeric(series: pd.Series) -> pd.Series | None:
    values = pd.to_numeric(series, errors="coerce")
    present = series.notna()
    # Treat a column as numeric only when every present value parses as a number.
    if present.any() and values[present].notna().all():
        return values
    return None


def _format_edge(value: float) -> str:
    return f"{value:.3g}" if abs(value) < 1e6 else f"{value:.4g}"


def groups(series: pd.Series, bins: int = 5) -> pd.Series:
    """Readable group labels: quantile ranges for numbers, top categories otherwise."""
    numeric = _numeric(series)
    if numeric is not None and numeric.nunique() > bins:
        codes, edges = pd.qcut(numeric, q=bins, retbins=True, duplicates="drop")
        labels = [
            f"{_format_edge(edges[i])} to {_format_edge(edges[i + 1])}"
            for i in range(len(edges) - 1)
        ]
        lookup = np.array(labels, dtype=object)
        named = pd.Series(lookup[codes.cat.codes.clip(lower=0).to_numpy()], index=series.index)
        return named.where(numeric.notna(), "(missing)")
    text = series.astype("string").fillna("(missing)").astype(str)
    common = text.value_counts().index[: MAX_GROUPS - 1]
    return text.where(text.isin(common), "(other)")


def condition_mask(frame: pd.DataFrame, conditions: Sequence[RuleCondition]) -> np.ndarray:
    mask = np.ones(len(frame), dtype=bool)
    for condition in conditions:
        if condition.column not in frame.columns:
            raise AnalysisError(f"Unknown column {condition.column!r}.")
        series = frame[condition.column]
        numeric = _numeric(series)
        value: str | float = condition.value
        if numeric is not None:
            try:
                value = float(condition.value)
            except ValueError:
                raise AnalysisError(f"{condition.column} needs a numeric value.") from None
            if not math.isfinite(value):
                raise AnalysisError("Values must be finite.")
            series = numeric
        elif condition.operator not in {"eq", "ne"}:
            raise AnalysisError(f"{condition.column} is text; use eq or ne.")
        else:
            series = series.astype("string")
        compared = getattr(series, f"__{condition.operator}__")(value)
        mask &= compared.fillna(False).to_numpy(dtype=bool)
    return mask


def overview(labels: np.ndarray, frame: pd.DataFrame, features: list[str]) -> dict[str, Any]:
    return {
        "partition": "development rows (train + validation); final test rows excluded",
        **_rate(int(labels.sum()), len(labels)),
        "features": features,
        "missing_share": {
            column: round(float(frame[column].isna().mean()), 4)
            for column in features
            if frame[column].isna().any()
        },
    }


def segment_rates(
    frame: pd.DataFrame, labels: np.ndarray, column: str, bins: int = 5
) -> dict[str, Any]:
    if column not in frame.columns:
        raise AnalysisError(f"Unknown column {column!r}.")
    grouped = groups(frame[column], bins)
    overall = labels.mean()
    rows = []
    for name in sorted(grouped.unique(), key=lambda g: (g == "(missing)", g)):
        mask = (grouped == name).to_numpy()
        entry = _rate(int(labels[mask].sum()), int(mask.sum()))
        entry["segment"] = name
        entry["lift_vs_overall"] = (
            round(entry["churn_rate"] / overall, 3) if overall and entry["rows"] else None
        )
        if entry["rows"] < MIN_GROUP:
            entry["warning"] = f"Fewer than {MIN_GROUP} rows; rate is unreliable."
        rows.append(entry)
    return {
        "column": column,
        "overall_churn_rate": round(float(overall), 4),
        "segments": rows,
        "note": "Association in historical data, not a cause.",
    }


def _difference_interval(a: dict[str, Any], b: dict[str, Any]) -> list[float] | None:
    # Newcombe's hybrid score interval for a difference of two proportions.
    if not a["rows"] or not b["rows"]:
        return None
    p1, (l1, u1) = a["churned"] / a["rows"], wilson_interval(a["churned"], a["rows"]) or (0, 0)
    p2, (l2, u2) = b["churned"] / b["rows"], wilson_interval(b["churned"], b["rows"]) or (0, 0)
    difference = p1 - p2
    lower = difference - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    upper = difference + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return [round(lower, 4), round(upper, 4)]


def _two_proportion_p(a: dict[str, Any], b: dict[str, Any]) -> float | None:
    n1, n2 = a["rows"], b["rows"]
    if not n1 or not n2:
        return None
    pooled = (a["churned"] + b["churned"]) / (n1 + n2)
    variance = pooled * (1 - pooled) * (1 / n1 + 1 / n2)
    if variance <= 0:
        return None
    z = (a["churned"] / n1 - b["churned"] / n2) / math.sqrt(variance)
    return float(f"{math.erfc(abs(z) / math.sqrt(2)):.3g}")


def compare_cohorts(
    frame: pd.DataFrame,
    labels: np.ndarray,
    cohort_a: Sequence[RuleCondition],
    cohort_b: Sequence[RuleCondition] | None,
    label_a: str = "cohort A",
) -> dict[str, Any]:
    mask_a = condition_mask(frame, cohort_a)
    mask_b = condition_mask(frame, cohort_b) if cohort_b else ~mask_a
    if cohort_b and (mask_a & mask_b).any():
        raise AnalysisError("Cohorts overlap; make the conditions mutually exclusive.")
    a = _rate(int(labels[mask_a].sum()), int(mask_a.sum()))
    b = _rate(int(labels[mask_b].sum()), int(mask_b.sum()))
    result: dict[str, Any] = {
        "cohort_a": {"label": label_a, "conditions": [c.model_dump() for c in cohort_a], **a},
        "cohort_b": {
            "label": "comparison cohort" if cohort_b else "all other accounts",
            "conditions": [c.model_dump() for c in cohort_b or []],
            **b,
        },
    }
    if a["rows"] and b["rows"]:
        result["rate_difference"] = round(a["churned"] / a["rows"] - b["churned"] / b["rows"], 4)
        result["rate_difference_95ci"] = _difference_interval(a, b)
        result["p_value"] = _two_proportion_p(a, b)
    if min(a["rows"], b["rows"]) < MIN_GROUP:
        result["warning"] = f"A cohort has fewer than {MIN_GROUP} rows; treat as anecdotal."
    result["note"] = "Association in historical data, not a cause."
    return result


def rank_associations(
    frame: pd.DataFrame, labels: np.ndarray, features: list[str], bins: int = 5
) -> dict[str, Any]:
    """Rank features by Cramér's V between their groups and churn (an effect size)."""
    ranked = []
    for column in features:
        grouped = groups(frame[column], bins)
        table = pd.crosstab(grouped, labels)
        if table.shape[0] < 2 or table.shape[1] < 2:
            continue
        chi2, p_value, _, _ = chi2_contingency(table.to_numpy())
        v = math.sqrt(chi2 / (table.to_numpy().sum() * (min(table.shape) - 1)))
        rates = (table[1] / table.sum(axis=1)) if 1 in table.columns else table.iloc[:, 0] * 0
        reliable = rates[table.sum(axis=1) >= MIN_GROUP]
        entry: dict[str, Any] = {"column": column, "cramers_v": round(v, 4), "p_value": p_value}
        if len(reliable) >= 2:
            entry["highest_rate_group"] = {
                "segment": str(reliable.idxmax()),
                "churn_rate": round(float(reliable.max()), 4),
            }
            entry["lowest_rate_group"] = {
                "segment": str(reliable.idxmin()),
                "churn_rate": round(float(reliable.min()), 4),
            }
        ranked.append(entry)
    ranked.sort(key=lambda item: item["cramers_v"], reverse=True)
    for item in ranked:
        item["p_value"] = float(f"{item['p_value']:.3g}")
    return {
        "method": "Cramér's V between binned feature groups and churn (0 = none, 1 = perfect)",
        "associations": ranked,
        "note": "Single-feature associations; correlated features overlap. Not causal.",
    }
