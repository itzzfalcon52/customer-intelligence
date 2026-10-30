"""Active-model registry and model monitoring.

- The active model is the run that scheduled scoring uses. Promotion checks that the pipeline
  still loads in this environment; history makes rollback a single step.
- Feature drift compares a scoring batch with the run's own training rows using the population
  stability index (PSI). Score shift compares two batches scored by the same run.
- Realized performance is measured only once outcomes are known: from a labelled outcomes file,
  or from a newer sync of the same source after the prediction horizon has fully elapsed.

PSI bands (< 0.1 stable, 0.1-0.25 watch, > 0.25 alert) are a common rule of thumb, not a test.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score
from sqlmodel import Session, col, select

from customer_intelligence.core.config import Settings
from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.models.dataset import Dataset
from customer_intelligence.models.operations import MonitorReport
from customer_intelligence.models.workspace import WorkspaceFact
from customer_intelligence.services.profiling import load_dataset_frame
from customer_intelligence.services.runs import load_pipeline, read_training_run
from customer_intelligence.services.scoring import read_customers, read_score

ACTIVE_MODEL = "active_model"
WATCH, ALERT = 0.1, 0.25
EPSILON = 1e-4
MAX_CATEGORIES = 20


# ------------------------------------------------------------------ registry


def active_model(session: Session) -> dict:
    fact = session.get(WorkspaceFact, ACTIVE_MODEL)
    value = fact.value if fact else {}
    return {"run_id": value.get("run_id"), "history": value.get("history", [])}


def _set_active(session: Session, run_id: str | None, action: str, history: list[dict]) -> dict:
    entry = {"run_id": run_id, "action": action, "at": datetime.now(UTC).isoformat()}
    value = {"run_id": run_id, "history": [entry, *history][:20]}
    fact = session.get(WorkspaceFact, ACTIVE_MODEL)
    if fact is None:
        fact = WorkspaceFact(key=ACTIVE_MODEL, value=value, source="user")
    else:
        fact.value, fact.source, fact.updated_at = value, "user", datetime.now(UTC)
    session.add(fact)
    session.commit()
    return active_model(session)


def promote(session: Session, settings: Settings, run_id: UUID) -> dict:
    run = read_training_run(run_id, settings.data_directory)
    load_pipeline(run, settings.data_directory)  # refuses runs that can no longer score
    current = active_model(session)
    if current["run_id"] == str(run_id):
        return current
    return _set_active(session, str(run_id), "promoted", current["history"])


def rollback(session: Session, settings: Settings) -> dict:
    current = active_model(session)
    previous = [
        h["run_id"]
        for h in current["history"]
        if h["run_id"] and h["run_id"] != current["run_id"] and h["action"] == "promoted"
    ]
    if not previous:
        raise WorkflowError("There is no earlier active model to roll back to.", 409)
    run = read_training_run(UUID(previous[0]), settings.data_directory)
    load_pipeline(run, settings.data_directory)
    return _set_active(session, previous[0], "rolled_back", current["history"])


# ------------------------------------------------------------------ drift


def band(psi: float) -> str:
    return "alert" if psi > ALERT else "watch" if psi > WATCH else "stable"


def _psi(expected: np.ndarray, actual: np.ndarray) -> float:
    e = np.clip(expected, EPSILON, None)
    a = np.clip(actual, EPSILON, None)
    return float(np.sum((a - e) * np.log(a / e)))


def numeric_psi(reference: pd.Series, current: pd.Series, bins: int = 10) -> float | None:
    ref = pd.to_numeric(reference, errors="coerce").dropna().to_numpy(dtype=float)
    cur = pd.to_numeric(current, errors="coerce").dropna().to_numpy(dtype=float)
    if len(ref) < 20 or len(cur) < 20:
        return None
    edges = np.unique(np.quantile(ref, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        return categorical_psi(reference.astype(str), current.astype(str))
    edges[0], edges[-1] = -np.inf, np.inf
    expected = np.histogram(ref, edges)[0] / len(ref)
    actual = np.histogram(cur, edges)[0] / len(cur)
    return _psi(expected, actual)


def categorical_psi(reference: pd.Series, current: pd.Series) -> float | None:
    ref = reference.fillna("(missing)").astype(str)
    cur = current.fillna("(missing)").astype(str)
    if len(ref) < 20 or len(cur) < 20:
        return None
    keep = set(ref.value_counts().index[:MAX_CATEGORIES])
    ref = ref.where(ref.isin(keep), "(other)")
    cur = cur.where(cur.isin(keep), "(other)")
    levels = sorted(set(ref) | set(cur))
    expected = ref.value_counts(normalize=True).reindex(levels, fill_value=0).to_numpy()
    actual = cur.value_counts(normalize=True).reindex(levels, fill_value=0).to_numpy()
    return _psi(expected, actual)


def _frame(session: Session, settings: Settings, dataset_id: UUID) -> pd.DataFrame:
    dataset = session.get(Dataset, dataset_id)
    if dataset is None:
        raise WorkflowError("Dataset not found.", 404)
    return load_dataset_frame(dataset, settings)


def feature_drift(session: Session, settings: Settings, score_id: UUID) -> MonitorReport:
    """PSI of every model input: the run's training rows versus the scored population."""
    score = read_score(score_id, settings.data_directory)
    run = read_training_run(score.run_id, settings.data_directory)
    reference_all = _frame(session, settings, run.task.dataset_id)
    reference = reference_all.iloc[run.split.row_assignments["train"]]
    partition = "train"
    if run.task.time_column and run.task.time_column in reference:
        # Older snapshots differ by design (e.g. tenure grows), so time-ordered models are
        # compared with the newest snapshot date they were trained on.
        latest = reference[run.task.time_column].max()
        reference = reference[reference[run.task.time_column] == latest]
        partition = f"train (latest snapshot, {latest})"
    current = _frame(session, settings, score.dataset_id)
    numeric = {
        c
        for c in run.task.feature_columns
        if pd.to_numeric(reference[c], errors="coerce").notna().mean() > 0.95
    }
    features: list[dict[str, Any]] = []
    for column in run.task.feature_columns:
        if column not in current:
            continue
        value = (
            numeric_psi(reference[column], current[column])
            if column in numeric
            else categorical_psi(reference[column], current[column])
        )
        if value is None:
            continue
        features.append(
            {
                "feature": column,
                "psi": round(value, 4),
                "band": band(value),
                "reference_missing": round(float(reference[column].isna().mean()), 4),
                "current_missing": round(float(current[column].isna().mean()), 4),
            }
        )
    features.sort(key=lambda f: f["psi"], reverse=True)
    shift = score_shift(session, settings, score_id)
    worst = max([float(f["psi"]) for f in features] + [float(shift["psi"]) if shift else 0.0])
    status = band(worst)
    moved = [f["feature"] for f in features if f["band"] != "stable"]
    if moved:
        summary = (
            f"{len(moved)} of {len(features)} customer traits shifted noticeably since training "
            f"(most: {features[0]['feature']})."
        )
    else:
        summary = f"None of the {len(features)} customer traits shifted noticeably since training."
    if shift and shift["band"] != "stable":
        summary += " Risk scores also moved compared with the previous batch."
    report = MonitorReport(
        kind="drift",
        run_id=score.run_id,
        score_id=score_id,
        status=status,
        summary=summary[:500],
        payload={
            "reference": {
                "dataset_id": str(run.task.dataset_id),
                "partition": partition,
                "rows": len(reference),
            },
            "current": {"dataset_id": str(score.dataset_id), "rows": len(current)},
            "features": features,
            "score_shift": shift,
            "bands": {"watch": WATCH, "alert": ALERT},
            "note": "PSI bands are a rule of thumb. Drift says inputs changed, not that the "
            "model is wrong; realized performance needs known outcomes.",
        },
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def score_shift(session: Session, settings: Settings, score_id: UUID) -> dict | None:
    """Compare a batch's risk scores with the previous batch scored by the same run."""
    score = read_score(score_id, settings.data_directory)
    batches = []
    directory = settings.data_directory / "scores"
    for path in directory.iterdir() if directory.exists() else []:
        try:
            other = read_score(UUID(path.name), settings.data_directory)
        except (ValueError, WorkflowError):
            continue
        if other.run_id == score.run_id and other.created_at < score.created_at:
            batches.append(other)
    if not batches:
        return None
    previous = max(batches, key=lambda b: b.created_at)
    before = np.array([c.risk_score for c in read_customers(previous, settings.data_directory)])
    after = np.array([c.risk_score for c in read_customers(score, settings.data_directory)])
    edges = np.unique(np.quantile(before, np.linspace(0, 1, 11)))
    if len(edges) < 3:
        return None
    edges[0], edges[-1] = -np.inf, np.inf
    psi = _psi(
        np.histogram(before, edges)[0] / len(before), np.histogram(after, edges)[0] / len(after)
    )
    return {
        "previous_score_id": str(previous.id),
        "psi": round(psi, 4),
        "band": band(psi),
        "previous_median": round(float(np.median(before)), 4),
        "current_median": round(float(np.median(after)), 4),
    }


# ------------------------------------------------------------------ realized performance


def measure_performance(
    session: Session,
    settings: Settings,
    score_id: UUID,
    outcomes: dict[str, int],
    basis: dict[str, Any],
) -> MonitorReport:
    score = read_score(score_id, settings.data_directory)
    customers = read_customers(score, settings.data_directory)
    matched = [(c, outcomes[c.customer_id]) for c in customers if c.customer_id in outcomes]
    if len(matched) < 20:
        raise WorkflowError("Fewer than 20 scored accounts have a known outcome yet.", 409)
    labels = np.array([y for _, y in matched])
    if labels.min() == labels.max():
        raise WorkflowError("Every matched account has the same outcome; AP is undefined.", 409)
    risk = np.array([c.risk_score for c, _ in matched])
    ap = float(average_precision_score(labels, risk))
    contacted = sorted(matched, key=lambda m: m[0].rank)[: score.contact_count]
    hits = sum(y for _, y in contacted)
    base = float(labels.mean())
    run = read_training_run(score.run_id, settings.data_directory)
    validation_ap = max(r.validation.average_precision for r in run.report.results)
    payload = {
        "matched_accounts": len(matched),
        "scored_accounts": len(customers),
        "churned": int(labels.sum()),
        "base_rate": round(base, 4),
        "average_precision": round(ap, 4),
        "lift_over_chance": round(ap / base, 2) if base else None,
        "validation_average_precision": round(validation_ap, 4),
        "contact_list": {
            "size": len(contacted),
            "churned": int(hits),
            "precision": round(hits / len(contacted), 4) if contacted else None,
            "recall": round(hits / labels.sum(), 4) if labels.sum() else None,
        },
        "basis": basis,
        "note": "Measured on accounts whose outcome is now known. Contacted accounts may have "
        "been saved by outreach, which lowers measured precision; use a holdout to separate "
        "model quality from intervention effect.",
    }
    drop = validation_ap - ap
    status = "alert" if drop > 0.15 else "watch" if drop > 0.07 else "stable"
    report = MonitorReport(
        kind="performance",
        run_id=score.run_id,
        score_id=score_id,
        status=status,
        summary=(
            f"Realized average precision {payload['average_precision']} on "
            f"{len(matched)} accounts with known outcomes (validation "
            f"{payload['validation_average_precision']}, chance {payload['base_rate']})."
        ),
        payload=payload,
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def outcomes_from_file(
    session: Session,
    settings: Settings,
    dataset_id: UUID,
    id_column: str,
    outcome_column: str,
    positive_label: str,
    segment_column: str | None = None,
) -> tuple[dict[str, int], dict[str, str]]:
    frame = _frame(session, settings, dataset_id)
    for column in (id_column, outcome_column, *([segment_column] if segment_column else [])):
        if column not in frame:
            raise WorkflowError(f"The outcomes file has no column {column}.")
    ids = frame[id_column].astype(str)
    labels = frame[outcome_column].astype(str).str.strip() == positive_label
    segments = (
        dict(zip(ids, frame[segment_column].fillna("(missing)").astype(str), strict=True))
        if segment_column
        else {}
    )
    return dict(zip(ids, labels.astype(int), strict=True)), segments


def outcomes_from_source(
    settings: Settings, score_id: UUID, source_id: UUID, horizon_days: int
) -> tuple[dict[str, int], dict[str, str]]:
    """Outcomes for a snapshot batch, read from a newer sync once its horizon has elapsed."""
    from customer_intelligence.ml.snapshots import data_end, normalise
    from customer_intelligence.services.sources import load_tables

    tables = normalise(load_tables(settings, source_id))
    end = data_end(tables)
    accounts = tables["accounts"].set_index("account_id")
    cancelled = accounts["cancelled_at"]
    plans = accounts["plan"].astype(str) if "plan" in accounts else None
    score = read_score(score_id, settings.data_directory)
    outcomes: dict[str, int] = {}
    segments: dict[str, str] = {}
    for customer in read_customers(score, settings.data_directory):
        account, _, day = customer.customer_id.rpartition("@")
        if not account or account not in cancelled.index:
            continue
        cutoff = pd.Timestamp(day)
        if cutoff + pd.Timedelta(days=horizon_days) > end:
            continue
        when = cancelled[account]
        outcomes[customer.customer_id] = int(
            pd.notna(when) and cutoff < when <= cutoff + pd.Timedelta(days=horizon_days)
        )
        if plans is not None:
            segments[customer.customer_id] = plans[account]
    return outcomes, segments


def performance_from_file(
    session: Session,
    settings: Settings,
    score_id: UUID,
    dataset_id: UUID,
    id_column: str,
    outcome_column: str,
    positive_label: str,
) -> MonitorReport:
    outcomes, _ = outcomes_from_file(
        session, settings, dataset_id, id_column, outcome_column, positive_label
    )
    return measure_performance(
        session,
        settings,
        score_id,
        outcomes,
        {"kind": "outcomes_file", "dataset_id": str(dataset_id), "outcome": outcome_column},
    )


def performance_from_source(
    session: Session, settings: Settings, score_id: UUID, source_id: UUID, horizon_days: int
) -> MonitorReport:
    outcomes, _ = outcomes_from_source(settings, score_id, source_id, horizon_days)
    return measure_performance(
        session,
        settings,
        score_id,
        outcomes,
        {"kind": "source_sync", "source_id": str(source_id), "horizon_days": horizon_days},
    )


# ------------------------------------------------------------------ measured lift

MIN_GROUP = 10
BOOTSTRAP = 2000


def _difference_interval(contact: np.ndarray, holdout: np.ndarray) -> tuple[float, float, float]:
    """Holdout churn rate minus contact churn rate, with a 95% percentile bootstrap interval."""
    rng = np.random.default_rng(0)
    point = float(holdout.mean() - contact.mean())
    draws = rng.choice(holdout, (BOOTSTRAP, len(holdout))).mean(axis=1) - rng.choice(
        contact, (BOOTSTRAP, len(contact))
    ).mean(axis=1)
    low, high = np.percentile(draws, [2.5, 97.5])
    return point, float(low), float(high)


def _lift_summary(contact: np.ndarray, holdout: np.ndarray) -> dict[str, Any]:
    point, low, high = _difference_interval(contact, holdout)
    verdict = "fewer_churned" if low > 0 else "more_churned" if high < 0 else "no_clear_difference"
    return {
        "contacted": {"accounts": len(contact), "churned": int(contact.sum())},
        "holdout": {"accounts": len(holdout), "churned": int(holdout.sum())},
        "contacted_churn_rate": round(float(contact.mean()), 4),
        "holdout_churn_rate": round(float(holdout.mean()), 4),
        "reduction": round(point, 4),
        "interval_95": [round(low, 4), round(high, 4)],
        "verdict": verdict,
    }


def measure_lift(
    session: Session,
    settings: Settings,
    score_id: UUID,
    outcomes: dict[str, int],
    basis: dict[str, Any],
    segments: dict[str, str] | None = None,
) -> MonitorReport:
    """Compare churn among contact-list accounts with the random holdout from the same list.

    This is an intention-to-treat comparison: it measures being on the contact list, whether
    or not every account was actually reached. It is the only basis for a retention-lift claim.
    """
    score = read_score(score_id, settings.data_directory)
    if not score.holdout_count:
        raise WorkflowError("This batch has no holdout group, so lift can't be measured.", 409)
    groups: dict[str, list[tuple[str, int]]] = {"contact": [], "holdout": []}
    for customer in read_customers(score, settings.data_directory):
        if customer.group and customer.customer_id in outcomes:
            groups[customer.group].append((customer.customer_id, outcomes[customer.customer_id]))
    if min(len(groups["contact"]), len(groups["holdout"])) < MIN_GROUP:
        raise WorkflowError(
            f"Not enough accounts with known outcomes yet: lift needs at least {MIN_GROUP} "
            f"contacted and {MIN_GROUP} held-out accounts.",
            409,
        )
    contact = np.array([y for _, y in groups["contact"]])
    holdout = np.array([y for _, y in groups["holdout"]])
    summary = _lift_summary(contact, holdout)
    by_segment = []
    for segment in sorted(set((segments or {}).values())):
        c = np.array([y for i, y in groups["contact"] if segments and segments.get(i) == segment])
        h = np.array([y for i, y in groups["holdout"] if segments and segments.get(i) == segment])
        if min(len(c), len(h)) >= MIN_GROUP:
            by_segment.append({"segment": segment, **_lift_summary(c, h)})
    words = {
        "fewer_churned": "fewer contacted accounts churned than held-out ones",
        "more_churned": "more contacted accounts churned than held-out ones",
        "no_clear_difference": "no clear difference between contacted and held-out accounts yet",
    }[summary["verdict"]]
    report = MonitorReport(
        kind="lift",
        run_id=score.run_id,
        score_id=score_id,
        status="stable" if summary["verdict"] != "more_churned" else "watch",
        summary=(
            f"Outreach result: {words}. {summary['contacted_churn_rate']:.1%} of contacted "
            f"accounts churned vs {summary['holdout_churn_rate']:.1%} of held-out ones."
        )[:500],
        payload={
            **summary,
            "by_segment": by_segment,
            "basis": basis,
            "note": "Intention-to-treat: compares everyone on the contact list with a random "
            "holdout from the same list. Small groups give wide intervals; an interval that "
            "crosses zero is not evidence that outreach worked.",
        },
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def list_reports(session: Session, kind: str | None = None, limit: int = 50) -> list[MonitorReport]:
    query = select(MonitorReport)
    if kind:
        query = query.where(MonitorReport.kind == kind)
    return list(session.exec(query.order_by(col(MonitorReport.created_at).desc()).limit(limit)))
