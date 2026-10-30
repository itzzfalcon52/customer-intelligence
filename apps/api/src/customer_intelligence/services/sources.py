"""Account-level data sources (multi-table) and the datasets built from them.

A source is a folder of normalised tables (accounts, invoices, usage, tickets) plus a manifest.
Sources come from a CSV bundle, the labelled synthetic generator, or a read-only connector. The
snapshot builder turns a source into an ordinary dataset, so training and scoring are reused.
"""

import io
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import numpy as np
import pandas as pd
from sqlmodel import Session

from customer_intelligence.core.config import Settings
from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.ml.snapshots import (
    REQUIRED,
    SnapshotError,
    build_snapshots,
    current_snapshot,
    data_end,
    normalise,
)
from customer_intelligence.services.artifacts import read_json
from customer_intelligence.services.datasets import save_dataset

TABLES = ("accounts", "invoices", "usage", "tickets")


def _directory(settings: Settings, source_id: UUID) -> Path:
    return settings.data_directory / "sources" / str(source_id)


def _save(
    settings: Settings,
    name: str,
    kind: str,
    tables: dict[str, pd.DataFrame],
    extra: dict | None = None,
) -> dict:
    try:
        parsed = normalise(tables)
    except SnapshotError as exc:
        raise WorkflowError(str(exc)) from exc
    source_id = uuid4()
    directory = _directory(settings, source_id)
    directory.mkdir(parents=True)
    for table in TABLES:
        frame = tables.get(table)
        if frame is not None:
            frame.to_csv(directory / f"{table}.csv", index=False)
    accounts = parsed["accounts"]
    manifest = {
        "id": str(source_id),
        "name": name,
        "kind": kind,
        "created_at": datetime.now(UTC).isoformat(),
        "counts": {t: int(len(parsed[t])) for t in TABLES},
        "first_date": accounts["created_at"].min().date().isoformat(),
        "last_date": data_end(parsed).date().isoformat(),
        "cancelled_accounts": int(accounts["cancelled_at"].notna().sum()),
        **(extra or {}),
    }
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def read_source(settings: Settings, source_id: UUID) -> dict:
    path = _directory(settings, source_id) / "manifest.json"
    if not path.exists():
        raise WorkflowError("Source not found.", 404)
    manifest = read_json(path)
    if not isinstance(manifest, dict) or manifest.get("id") != str(source_id):
        raise WorkflowError("Invalid source manifest.", 409)
    return manifest


def list_sources(settings: Settings) -> list[dict]:
    root = settings.data_directory / "sources"
    if not root.exists():
        return []
    out = []
    for path in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            out.append(read_source(settings, UUID(path.name)))
        except (ValueError, WorkflowError):
            continue
    return out


def load_tables(settings: Settings, source_id: UUID) -> dict[str, pd.DataFrame]:
    read_source(settings, source_id)
    directory = _directory(settings, source_id)
    return {
        t: pd.read_csv(directory / f"{t}.csv", dtype={"account_id": str})
        for t in TABLES
        if (directory / f"{t}.csv").exists()
    }


def save_bundle(settings: Settings, name: str, files: dict[str, bytes]) -> dict:
    if "accounts" not in files:
        raise WorkflowError("Upload at least accounts.csv.")
    tables = {}
    for table, content in files.items():
        if table not in TABLES:
            raise WorkflowError(f"Unknown table {table}.")
        if len(content) > settings.max_upload_mb * 1024 * 1024:
            raise WorkflowError(f"{table}.csv must be {settings.max_upload_mb} MB or smaller.", 413)
        try:
            frame = pd.read_csv(io.BytesIO(content), dtype={"account_id": str})
        except (ValueError, pd.errors.ParserError) as exc:
            raise WorkflowError(f"{table}.csv could not be read as CSV.") from exc
        if len(frame) > settings.max_rows:
            raise WorkflowError(f"{table}.csv has more than {settings.max_rows:,} rows.", 413)
        tables[table] = frame
    return _save(settings, name, "csv_bundle", tables)


def build_dataset(
    session: Session,
    settings: Settings,
    source_id: UUID,
    horizon_days: int,
    purpose: str,
) -> dict:
    manifest = read_source(settings, source_id)
    tables = load_tables(settings, source_id)
    try:
        if purpose == "training":
            result = build_snapshots(tables, horizon_days)
            frame, dropped = result.frame, result.dropped_unobserved
        else:
            frame, dropped = current_snapshot(tables), 0
    except SnapshotError as exc:
        raise WorkflowError(str(exc)) from exc
    label = f"churned_within_{horizon_days}d"
    stem = manifest["name"].replace(" ", "-")[:60]
    filename = (
        f"{stem}-snapshots-{horizon_days}d.csv" if purpose == "training" else f"{stem}-current.csv"
    )
    if manifest["kind"] == "synthetic" and not filename.startswith("DEMO-"):
        filename = "DEMO-" + filename
    dataset = save_dataset(
        source=io.BytesIO(frame.to_csv(index=False).encode()),
        filename=filename,
        settings=settings,
        session=session,
    )
    excluded = {"snapshot_id", "account_id", "snapshot_date", label}
    # A table the source doesn't have (e.g. tickets from Stripe) yields an all-zero feature;
    # constant columns carry no signal and task validation rejects them, so leave them out.
    features = [c for c in frame.columns if c not in excluded and frame[c].nunique() > 1]
    return {
        "dataset_id": str(dataset.id),
        "rows": int(len(frame)),
        "snapshot_dates": int(frame["snapshot_date"].nunique()),
        "dropped_unobserved_dates": dropped,
        "positive_rate": float((frame[label] == "Yes").mean()) if label in frame else None,
        "recommended_task": {
            "target_column": label,
            "positive_label": "Yes",
            "id_column": "snapshot_id",
            "time_column": "snapshot_date",
            "feature_columns": features,
        }
        if purpose == "training"
        else None,
    }


def account_timeline(settings: Settings, source_id: UUID, account_id: str) -> dict:
    tables = normalise(load_tables(settings, source_id))
    accounts = tables["accounts"].set_index("account_id")
    if account_id not in accounts.index:
        raise WorkflowError("Account not found in this source.", 404)
    row = accounts.loc[account_id]
    usage = tables["usage"][tables["usage"]["account_id"] == account_id].sort_values("date")
    invoices = tables["invoices"][tables["invoices"]["account_id"] == account_id].sort_values(
        "date"
    )
    tickets = tables["tickets"][tables["tickets"]["account_id"] == account_id].sort_values(
        "created_at"
    )

    def iso(value: Any) -> str | None:
        return None if pd.isna(value) else pd.Timestamp(value).date().isoformat()

    return {
        "account_id": account_id,
        "created_at": iso(row["created_at"]),
        "cancelled_at": iso(row["cancelled_at"]),
        "attributes": {
            k: (None if pd.isna(v) else v)
            for k, v in row.drop(["created_at", "cancelled_at"]).to_dict().items()
        },
        "usage": [
            {"date": iso(r.date), "active_users": float(r.active_users)}  # type: ignore[arg-type]
            for r in usage.itertuples()
            if pd.notna(r.active_users)
        ],
        "invoices": [
            {"date": iso(r.date), "amount": float(r.amount), "status": r.status}  # type: ignore[arg-type]
            for r in invoices.itertuples()
        ],
        "tickets": [
            {
                "date": iso(r.created_at),
                "subject": str(getattr(r, "subject", "") or ""),
                "topics": list(r.topics),  # type: ignore[arg-type]
            }
            for r in tickets.itertuples()
        ],
    }


# ------------------------------------------------------------------ synthetic demo source

SUBJECTS = {
    "billing": ["Question about my invoice", "Card was charged twice", "Pricing for more seats"],
    "bug": ["Export is broken", "Error when saving a report", "Dashboard not working"],
    "onboarding": [
        "How do I set up SSO?",
        "Getting started with integrations",
        "How to invite my team",
    ],
    "cancel_intent": [
        "How do I cancel our plan?",
        "We may switch to a competitor",
        "Downgrade request",
    ],
    "performance": ["App is very slow today", "Reports timeout", "Pages loading slowly"],
}


def synthetic_tables(
    seed: int = 7, accounts: int = 900, end: str = "2026-09-30"
) -> dict[str, pd.DataFrame]:
    """Explicitly synthetic B2B SaaS data with planted churn drivers (documented below).

    Drivers raising monthly churn hazard: falling active users, failed payments, cancel-intent
    and bug tickets, monthly billing and few seats. Values are generated, never real customers.
    """
    rng = np.random.default_rng(seed)
    end_date = pd.Timestamp(end)
    start = end_date - pd.Timedelta(days=730)
    plans = ["Starter", "Growth", "Scale"]
    rows, invoice_rows, usage_rows, ticket_rows = [], [], [], []
    for index in range(accounts):
        account = f"ACME-{index + 1:04d}"
        created = start + pd.Timedelta(days=int(rng.integers(0, 600)))
        plan = plans[int(rng.choice(3, p=[0.5, 0.35, 0.15]))]
        seats = int(rng.integers(3, 12) * (1 + plans.index(plan) * 2))
        cycle = "annual" if rng.random() < 0.35 else "monthly"
        price = {"Starter": 15, "Growth": 25, "Scale": 40}[plan] * seats
        base_users = max(1, int(seats * rng.uniform(0.5, 0.95)))
        decay = rng.uniform(0.0, 0.05) if rng.random() < 0.35 else rng.uniform(-0.01, 0.01)
        payment_risk = rng.uniform(0.0, 0.25) if rng.random() < 0.2 else 0.02
        cancelled = None
        users = float(base_users)
        week = created
        month_marker = created
        while week <= end_date and cancelled is None:
            users = max(0.0, users * (1 - decay) + rng.normal(0, 0.3))
            logins = int(max(0, users * rng.uniform(3, 6)))
            usage_rows.append((account, week.date().isoformat(), round(users, 1), logins))
            if (week - month_marker).days >= 30:
                month_marker = week
                failed = rng.random() < payment_risk
                if cycle == "monthly" or (week - created).days % 365 < 30:
                    amount = price * (12 if cycle == "annual" else 1)
                    invoice_rows.append(
                        (account, week.date().isoformat(), amount, "failed" if failed else "paid")
                    )
                    if failed:
                        invoice_rows.append(
                            (
                                account,
                                (week + pd.Timedelta(days=5)).date().isoformat(),
                                amount,
                                "paid",
                            )
                        )
                topic_weights = np.array([0.25, 0.25 + 3 * decay, 0.2, 0.05 + 4 * decay, 0.15])
                if rng.random() < 0.25 + 4 * decay + payment_risk:
                    topic = list(SUBJECTS)[
                        int(rng.choice(5, p=topic_weights / topic_weights.sum()))
                    ]
                    ticket_rows.append(
                        (account, week.date().isoformat(), str(rng.choice(SUBJECTS[topic])))
                    )
                usage_drop = max(0.0, 1 - users / base_users)
                hazard = (
                    0.008
                    + 0.09 * usage_drop
                    + 0.6 * payment_risk * failed
                    + (0.01 if cycle == "monthly" else 0.0)
                    + (0.01 if seats < 6 else 0.0)
                )
                if rng.random() < hazard:
                    cancelled = week + pd.Timedelta(days=int(rng.integers(1, 20)))
            week += pd.Timedelta(days=7)
        rows.append(
            (
                account,
                created.date().isoformat(),
                cancelled.date().isoformat()
                if cancelled is not None and cancelled <= end_date
                else "",
                plan,
                seats,
                cycle,
                str(rng.choice(["Software", "Retail", "Finance", "Healthcare", "Education"])),
            )
        )
    return {
        "accounts": pd.DataFrame(
            rows,
            columns=[
                "account_id",
                "created_at",
                "cancelled_at",
                "plan",
                "seats",
                "billing_cycle",
                "industry",
            ],
        ),
        "invoices": pd.DataFrame(invoice_rows, columns=["account_id", "date", "amount", "status"]),
        "usage": pd.DataFrame(usage_rows, columns=["account_id", "date", "active_users", "logins"]),
        "tickets": pd.DataFrame(ticket_rows, columns=["account_id", "created_at", "subject"]),
    }


def create_synthetic(settings: Settings) -> dict:
    return _save(
        settings,
        "Synthetic SaaS workspace",
        "synthetic",
        synthetic_tables(),
        {"note": "Generated demo data with planted drivers. Not a real business or connection."},
    )


def required_columns() -> dict[str, list[str]]:
    return {k: sorted(v) for k, v in REQUIRED.items()}
