import csv
import json
from datetime import UTC, datetime
from hashlib import sha256
from io import StringIO
from pathlib import Path
from uuid import UUID, uuid4

import numpy as np
import pandas as pd
from pydantic import ValidationError
from sqlmodel import Session

from customer_intelligence.core.config import Settings
from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.ml.evaluation import positive_scores
from customer_intelligence.models.dataset import Dataset
from customer_intelligence.schemas.workflow import CustomerScore, ScoreManifest, ScoreRequest
from customer_intelligence.services.artifacts import publish_json, read_json
from customer_intelligence.services.profiling import load_dataset_frame
from customer_intelligence.services.runs import load_pipeline, read_training_run

# A scored row is about 150-250 bytes of JSON; the budget scales with the row limit.
BYTES_PER_ROW = 400


def rows_budget(settings: Settings) -> int:
    return max(20_000_000, settings.max_rows * BYTES_PER_ROW)


def manifest_budget(manifest: ScoreManifest) -> int:
    return max(20_000_000, manifest.row_count * BYTES_PER_ROW)


def score_dataset(session: Session, settings: Settings, request: ScoreRequest) -> UUID:
    run = read_training_run(request.run_id, settings.data_directory)
    pipeline = load_pipeline(run, settings.data_directory)
    dataset = session.get(Dataset, request.dataset_id)
    if dataset is None:
        raise WorkflowError("Scoring dataset not found.", 404)
    raw_path = settings.data_directory / "uploads" / dataset.storage_key
    digest = sha256(raw_path.read_bytes()).hexdigest()
    frame = load_dataset_frame(dataset, settings, expected_sha256=digest)
    if not 1 <= request.contact_count <= len(frame):
        raise WorkflowError("Contact count exceeds the scoring population.")
    missing = [c for c in run.task.feature_columns if c not in frame.columns]
    if missing:
        raise WorkflowError(f"Required scoring features are missing: {missing}")
    id_column = run.task.id_column
    if id_column:
        if id_column not in frame.columns:
            raise WorkflowError(f"Required customer ID column is missing: {id_column}")
        identifiers = frame[id_column]
        if identifiers.isna().any() or identifiers.duplicated().any():
            raise WorkflowError("Customer IDs must be present and unique in the scoring file.")
        ids = identifiers.astype(str).tolist()
        if any(len(value) > 256 for value in ids):
            raise WorkflowError("Scoring identifiers must be at most 256 characters.")
    else:
        ids = [f"row_{i + 1}" for i in range(len(frame))]
    features = frame.loc[:, run.task.feature_columns]
    scores = positive_scores(pipeline, features)
    if not np.isfinite(scores).all() or any(v < 0 or v > 1 for v in scores):
        raise WorkflowError("The model produced invalid risk scores.", 409)
    warnings = [
        "Scores are model risk scores, not established churn probabilities.",
        "A shortlist does not prove that an intervention prevents churn.",
    ]
    if not id_column:
        warnings.append("Row references are file-specific and are not durable customer IDs.")
    extras = set(frame.columns) - set(run.task.feature_columns) - {id_column}
    if extras:
        warnings.append(f"{len(extras)} extra columns were ignored as predictive inputs.")
    schema = pipeline.named_steps["preprocessing"].named_steps["schema"]
    cats = schema.categorical_columns_
    if cats:
        encoder = (
            pipeline.named_steps["preprocessing"]
            .named_steps["columns"]
            .named_transformers_["categorical"]
            .named_steps["encoder"]
        )
        for column, known in zip(cats, encoder.categories_, strict=True):
            count = int((frame[column].notna() & ~frame[column].isin(known)).sum())
            if count:
                warnings.append(
                    f"{column}: {count} unseen values use the saved ignore-unknown encoding."
                )
    values: list[float] | None = None
    if request.value_column:
        if request.value_column not in frame.columns:
            raise WorkflowError("The requested customer value column is missing.")
        parsed = pd.to_numeric(frame[request.value_column], errors="coerce")
        values = parsed.to_numpy(dtype=float, na_value=np.nan).tolist()
        if not np.isfinite(values).all() or any(v < 0 for v in values):
            raise WorkflowError("Customer values must be finite, nonnegative numbers.")
        warnings.append("Risk × value is an exposure proxy, not expected or saved revenue.")
    if request.ranking == "risk_x_value" and values is None:
        raise WorkflowError("Value-based ranking requires a value column.")
    order = np.argsort(-np.asarray(scores), kind="stable")
    ranks = {int(position): rank for rank, position in enumerate(order, start=1)}
    exposures = (
        [score * value for score, value in zip(scores, values, strict=True)] if values else None
    )
    if exposures is not None and not np.isfinite(exposures).all():
        raise WorkflowError("Risk × value exceeded the supported numeric range.")
    priority_order = np.argsort(-np.asarray(exposures), kind="stable") if exposures else order
    priorities = {int(position): rank for rank, position in enumerate(priority_order, start=1)}
    rows = [
        CustomerScore(
            customer_id=ids[i],
            row_reference=i + 1,
            risk_score=scores[i],
            rank=ranks[i],
            customer_value=values[i] if values is not None else None,
            exposure_proxy=exposures[i] if exposures is not None else None,
            priority_rank=priorities[i] if exposures is not None else None,
        ).model_dump(mode="json")
        for i in (
            int(position)
            for position in (priority_order if request.ranking == "risk_x_value" else order)
        )
    ]
    holdout_seed, holdout_count = None, 0
    if request.holdout_rate > 0:
        # A seeded random holdout among the contact list: the only fair comparison for lift.
        if request.contact_count < 10:
            raise WorkflowError("A holdout group needs a contact list of at least 10 accounts.")
        holdout_seed = request.idempotency_key.int % 2**32
        holdout_count = max(1, round(request.contact_count * request.holdout_rate))
        chosen = set(
            np.random.default_rng(holdout_seed)
            .choice(request.contact_count, size=holdout_count, replace=False)
            .tolist()
        )
        for position, row in enumerate(rows[: request.contact_count]):
            row["group"] = "holdout" if position in chosen else "contact"
        warnings.append(
            f"{holdout_count} of {request.contact_count} listed accounts are a random holdout: "
            "do not contact them, so outreach can be measured against them later."
        )
    elif rows:
        for row in rows[: request.contact_count]:
            row["group"] = "contact"
    encoded = json.dumps(rows, allow_nan=False, ensure_ascii=False).encode()
    if len(encoded) > rows_budget(settings):
        raise WorkflowError("Scoring output exceeds the artifact size limit.")
    score_id = uuid4()
    manifest = ScoreManifest(
        id=score_id,
        run_id=request.run_id,
        dataset_id=request.dataset_id,
        dataset_sha256=digest,
        created_at=datetime.now(UTC),
        row_count=len(frame),
        contact_count=request.contact_count,
        ranking=request.ranking,
        value_column=request.value_column,
        value_unit=request.value_unit,
        rows_sha256=sha256(encoded).hexdigest(),
        warnings=warnings,
        holdout_rate=request.holdout_rate,
        holdout_seed=holdout_seed,
        holdout_count=holdout_count,
    )
    publish_json(
        settings.data_directory / "scores",
        {
            "rows.json": rows,
            "manifest.json": manifest.model_dump(mode="json"),
        },
        score_id,
    )
    return score_id


def read_score(score_id: UUID, data_directory: Path) -> ScoreManifest:
    try:
        manifest = ScoreManifest.model_validate(
            read_json(data_directory / "scores" / str(score_id) / "manifest.json")
        )
    except ValidationError as exc:
        raise WorkflowError("Scoring manifest is invalid.", 409) from exc
    if manifest.id != score_id:
        raise WorkflowError("Scoring manifest identity mismatch.", 409)
    return manifest


def read_customers(manifest: ScoreManifest, data_directory: Path) -> list[CustomerScore]:
    path = data_directory / "scores" / str(manifest.id) / "rows.json"
    try:
        with path.open("rb") as handle:
            raw = handle.read(manifest_budget(manifest) + 1)
    except OSError as exc:
        raise WorkflowError("Scoring output is missing or unreadable.", 409) from exc
    if len(raw) > manifest_budget(manifest) or sha256(raw).hexdigest() != manifest.rows_sha256:
        raise WorkflowError("Scoring output checksum mismatch.", 409)
    try:
        payload = json.loads(raw)
        if not isinstance(payload, list):
            raise ValueError("Expected customer rows.")
        rows = [CustomerScore.model_validate(row) for row in payload]
    except (ValueError, TypeError) as exc:
        raise WorkflowError("Scoring output is invalid.", 409) from exc
    if len(rows) != manifest.row_count:
        raise WorkflowError("Scoring output row count mismatch.", 409)
    return rows


def spreadsheet_safe(value: str) -> str:
    if value.startswith(("\t", "\r", "\n")) or value.lstrip().startswith(
        ("=", "+", "-", "@", "\t", "\r", "\n")
    ):
        return "'" + value
    return value


def export_scores(
    manifest: ScoreManifest, rows: list[CustomerScore], top_k: int | None = None
) -> str:
    if top_k is not None and not 1 <= top_k <= len(rows):
        raise WorkflowError("Export contact count exceeds the scoring population.")
    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "customer_id",
            "row_reference",
            "risk_score",
            "risk_rank",
            "customer_value",
            "exposure_proxy",
            "priority_rank",
            "run_id",
            "scoring_dataset_id",
            "group",
        ]
    )
    # A contact export never includes the holdout: those accounts must not be contacted.
    selected = [r for r in rows if r.group != "holdout"][:top_k] if top_k else rows
    for row in selected:
        writer.writerow(
            [
                spreadsheet_safe(row.customer_id),
                row.row_reference,
                row.risk_score,
                row.rank,
                row.customer_value,
                row.exposure_proxy,
                row.priority_rank,
                manifest.run_id,
                manifest.dataset_id,
                row.group or "",
            ]
        )
    return output.getvalue()
