"""Point-in-time feature snapshots from account-level tables.

Each row describes one account as it looked on a snapshot date: every feature uses only events
dated on or before that date, and the label says whether the account cancelled within the
following horizon. Snapshots whose horizon has not fully elapsed are dropped, because their
outcome is not yet known.
"""

import re
from dataclasses import dataclass

import numpy as np
import pandas as pd

# Transparent keyword taxonomy for support tickets: no fitting, so no leakage across time.
TICKET_TOPICS: dict[str, tuple[str, ...]] = {
    "billing": ("invoice", "charge", "refund", "billing", "payment", "card", "price", "pricing"),
    "bug": ("bug", "error", "broken", "crash", "fail", "not working", "issue"),
    "onboarding": (
        "setup",
        "set up",
        "onboard",
        "how do i",
        "how to",
        "training",
        "getting started",
    ),
    "cancel_intent": (
        "cancel",
        "cancellation",
        "downgrade",
        "terminate",
        "switch to",
        "competitor",
    ),
    "performance": ("slow", "latency", "timeout", "performance", "loading"),
}
REQUIRED = {
    "accounts": {"account_id", "created_at"},
    "invoices": {"account_id", "date", "amount", "status"},
    "usage": {"account_id", "date", "active_users"},
    "tickets": {"account_id", "created_at"},
}


class SnapshotError(ValueError):
    pass


@dataclass(frozen=True)
class SnapshotResult:
    frame: pd.DataFrame
    dropped_unobserved: int
    data_end: pd.Timestamp
    cutoffs: list[pd.Timestamp]


def ticket_topics(text: str) -> list[str]:
    lowered = text.lower()
    return [
        topic
        for topic, words in TICKET_TOPICS.items()
        if any(re.search(rf"\b{re.escape(w)}", lowered) for w in words)
    ]


def _dates(frame: pd.DataFrame, column: str, table: str, optional: bool = False) -> pd.Series:
    values = pd.to_datetime(frame[column], errors="coerce", utc=True).dt.tz_localize(None)
    raw_present = frame[column].notna() & (frame[column].astype(str).str.strip() != "")
    if bool((values.isna() & raw_present).any()):
        raise SnapshotError(f"{table}.{column} has values that are not dates.")
    if not optional and bool(values.isna().any()):
        raise SnapshotError(f"{table}.{column} has missing dates.")
    return values


def normalise(tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Validate required columns and parse dates. Missing optional tables become empty."""
    if "accounts" not in tables:
        raise SnapshotError("An accounts table is required.")
    out: dict[str, pd.DataFrame] = {}
    for name, required in REQUIRED.items():
        frame = tables.get(name)
        if frame is None:
            frame = pd.DataFrame(columns=sorted(required))
        missing = required - set(frame.columns)
        if missing:
            raise SnapshotError(f"{name} is missing columns: {', '.join(sorted(missing))}.")
        frame = frame.copy()
        frame["account_id"] = frame["account_id"].astype(str)
        out[name] = frame
    accounts = out["accounts"]
    if bool(accounts["account_id"].duplicated().any()):
        raise SnapshotError("accounts.account_id must be unique.")
    accounts["created_at"] = _dates(accounts, "created_at", "accounts")
    if "cancelled_at" not in accounts:
        accounts["cancelled_at"] = pd.NaT
    accounts["cancelled_at"] = _dates(accounts, "cancelled_at", "accounts", optional=True)
    out["invoices"]["date"] = _dates(out["invoices"], "date", "invoices")
    out["invoices"]["amount"] = pd.to_numeric(out["invoices"]["amount"], errors="coerce")
    out["invoices"]["status"] = out["invoices"]["status"].astype(str).str.lower()
    out["usage"]["date"] = _dates(out["usage"], "date", "usage")
    for column in ("active_users", "logins"):
        if column in out["usage"]:
            out["usage"][column] = pd.to_numeric(out["usage"][column], errors="coerce")
    out["tickets"]["created_at"] = _dates(out["tickets"], "created_at", "tickets")
    text = out["tickets"].get("subject", pd.Series("", index=out["tickets"].index)).fillna("")
    if "body" in out["tickets"]:
        text = text.astype(str) + " " + out["tickets"]["body"].fillna("").astype(str)
    out["tickets"]["topics"] = [ticket_topics(str(t)) for t in text]
    known = set(accounts["account_id"])
    for name in ("invoices", "usage", "tickets"):
        unknown = set(out[name]["account_id"]) - known
        if unknown:
            raise SnapshotError(f"{name} references {len(unknown)} account IDs not in accounts.")
    return out


def data_end(tables: dict[str, pd.DataFrame]) -> pd.Timestamp:
    stamps = [
        tables["accounts"]["created_at"].max(),
        tables["accounts"]["cancelled_at"].max(),
        tables["invoices"]["date"].max(),
        tables["usage"]["date"].max(),
        tables["tickets"]["created_at"].max(),
    ]
    present = [s for s in stamps if pd.notna(s)]
    return max(present)


def monthly_cutoffs(
    tables: dict[str, pd.DataFrame], horizon_days: int, count: int = 12
) -> list[pd.Timestamp]:
    """Month-end dates whose full horizon has elapsed, newest last."""
    end = data_end(tables)
    start = tables["accounts"]["created_at"].min() + pd.Timedelta(days=60)
    last = end - pd.Timedelta(days=horizon_days)
    if last <= start:
        raise SnapshotError("The data does not span enough time for this horizon.")
    months = pd.date_range(start=start, end=last, freq="ME")
    if len(months) < 3:
        raise SnapshotError("At least three monthly snapshot dates are needed.")
    return list(months[-count:])


def _window(frame: pd.DataFrame, column: str, end: pd.Timestamp, days: int) -> pd.DataFrame:
    return frame[(frame[column] <= end) & (frame[column] > end - pd.Timedelta(days=days))]


def features_at(tables: dict[str, pd.DataFrame], cutoff: pd.Timestamp) -> pd.DataFrame:
    """One row per account active on `cutoff`, using only events on or before it."""
    accounts = tables["accounts"]
    active = accounts[
        (accounts["created_at"] < cutoff)
        & (accounts["cancelled_at"].isna() | (accounts["cancelled_at"] > cutoff))
    ].set_index("account_id")
    out = pd.DataFrame(index=active.index)
    out["tenure_days"] = (cutoff - active["created_at"]).dt.days
    for column in ("plan", "billing_cycle", "seats", "industry", "region"):
        if column in active:
            out[column] = active[column]

    invoices = tables["invoices"]
    paid = invoices[(invoices["date"] <= cutoff) & (invoices["status"] == "paid")]
    last_paid = paid.sort_values("date").groupby("account_id").tail(1).set_index("account_id")
    cycle = active.get("billing_cycle", pd.Series("monthly", index=active.index)).astype(str)
    divisor = np.where(cycle.str.lower().str.startswith("annual"), 12.0, 1.0)
    mrr = last_paid["amount"].reindex(out.index)
    out["mrr"] = (mrr / pd.Series(divisor, index=active.index)).round(2)
    recent = _window(invoices, "date", cutoff, 90)
    out["failed_payments_90d"] = (
        recent[recent["status"] == "failed"]
        .groupby("account_id")
        .size()
        .reindex(out.index)
        .fillna(0)
    )

    usage = tables["usage"]
    last30 = _window(usage, "date", cutoff, 30).groupby("account_id")["active_users"].mean()
    prev30 = (
        _window(usage, "date", cutoff - pd.Timedelta(days=30), 30)
        .groupby("account_id")["active_users"]
        .mean()
    )
    out["active_users_30d"] = last30.reindex(out.index).round(2)
    change = (last30 - prev30) / prev30.where(prev30 > 0)
    out["usage_change_pct"] = (change.reindex(out.index) * 100).round(1)
    seen = usage[(usage["date"] <= cutoff) & (usage["active_users"] > 0)]
    last_seen = seen.groupby("account_id")["date"].max().reindex(out.index)
    out["days_since_active"] = (cutoff - last_seen).dt.days
    if "logins" in usage:
        out["logins_30d"] = (
            _window(usage, "date", cutoff, 30)
            .groupby("account_id")["logins"]
            .sum()
            .reindex(out.index)
        )

    tickets = _window(tables["tickets"], "created_at", cutoff, 90)
    out["tickets_90d"] = tickets.groupby("account_id").size().reindex(out.index).fillna(0)
    exploded = tickets.explode("topics").dropna(subset=["topics"])
    for topic in TICKET_TOPICS:
        out[f"tickets_{topic}_90d"] = (
            exploded[exploded["topics"] == topic]
            .groupby("account_id")
            .size()
            .reindex(out.index)
            .fillna(0)
        )
    return out


def build_snapshots(
    tables: dict[str, pd.DataFrame],
    horizon_days: int,
    cutoffs: list[pd.Timestamp] | None = None,
) -> SnapshotResult:
    tables = normalise(tables)
    end = data_end(tables)
    cutoffs = cutoffs or monthly_cutoffs(tables, horizon_days)
    label = f"churned_within_{horizon_days}d"
    frames = []
    dropped = 0
    for cutoff in sorted(cutoffs):
        if cutoff + pd.Timedelta(days=horizon_days) > end:
            dropped += 1
            continue
        rows = features_at(tables, cutoff)
        cancelled = tables["accounts"].set_index("account_id")["cancelled_at"].reindex(rows.index)
        churned = (cancelled > cutoff) & (cancelled <= cutoff + pd.Timedelta(days=horizon_days))
        rows.insert(0, "snapshot_date", cutoff.date().isoformat())
        rows[label] = np.where(churned, "Yes", "No")
        rows = rows.reset_index().rename(columns={"index": "account_id"})
        rows.insert(0, "snapshot_id", rows["account_id"] + "@" + rows["snapshot_date"])
        frames.append(rows)
    if not frames:
        raise SnapshotError("No snapshot date has a fully observed horizon.")
    frame = pd.concat(frames, ignore_index=True)
    if frame[label].nunique() < 2:
        raise SnapshotError("Every snapshot has the same outcome; there is nothing to learn.")
    return SnapshotResult(
        frame=frame, dropped_unobserved=dropped, data_end=end, cutoffs=sorted(cutoffs)
    )


def observed_through(tables: dict[str, pd.DataFrame]) -> pd.Timestamp:
    """The last date every non-empty activity table (usage, invoices) covers.

    Scoring at a later date would read windows with missing activity (e.g. an invoice dated after
    the last usage export makes every account look inactive), so current features stop here.
    """
    ends = [
        tables[name][column].max()
        for name, column in (("usage", "date"), ("invoices", "date"))
        if not tables[name].empty
    ]
    present = [e for e in ends if pd.notna(e)]
    return min(present) if present else data_end(tables)


def current_snapshot(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Features for accounts active when activity data was last complete, for scoring."""
    tables = normalise(tables)
    end = observed_through(tables)
    rows = features_at(tables, end)
    rows.insert(0, "snapshot_date", end.date().isoformat())
    rows = rows.reset_index().rename(columns={"index": "account_id"})
    rows.insert(0, "snapshot_id", rows["account_id"] + "@" + rows["snapshot_date"])
    return rows
