"""Renewal radar: accounts renewing soon, ranked by churn risk, with the value that renews.

Renewal dates and "set to cancel" come straight from the billing system (or a CSV bundle's
`renews_at` column); they are carried on the accounts table but never used as model features.
Risk scores are uncalibrated ranks, so the radar never multiplies them by value into an
"expected loss": it shows the value renewing (the last paid invoice) next to the risk.
"""

import csv
import io
from typing import Any, Literal
from uuid import UUID

import pandas as pd
from sqlmodel import Session

from customer_intelligence.core.config import Settings
from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.services import sources
from customer_intelligence.services.scoring import read_customers, read_score, spreadsheet_safe

Sort = Literal["risk", "date", "value"]
MAX_DAYS = 365
UNAVAILABLE = (
    "No renewal dates yet. Connect a billing system (Razorpay, Zoho Billing or Stripe), or add "
    "a renews_at column to a CSV bundle, then score its accounts or run a check."
)


def _level(rank: int, total: int) -> str:
    share = rank / max(1, total)
    return "high" if share <= 0.1 else "elevated" if share <= 0.3 else "low"


def _has_renewals(settings: Settings, source_id: UUID) -> bool:
    try:
        accounts = sources.load_tables(settings, source_id)["accounts"]
    except (WorkflowError, KeyError):
        return False
    return "renews_at" in accounts and bool(accounts["renews_at"].notna().any())


def _resolve(
    session: Session, settings: Settings, score_id: UUID | None, source_id: UUID | None = None
) -> tuple[UUID, UUID] | None:
    """The scoring batch and the renewal-carrying source its accounts came from."""
    from customer_intelligence.services.autonomy import read_schedule

    if score_id and source_id:
        return (score_id, source_id) if _has_renewals(settings, source_id) else None

    history = read_schedule(session).model_dump(mode="json")["history"]
    for entry in history:
        if not entry.get("score_id") or not entry.get("source_id"):
            continue
        if score_id and entry["score_id"] != str(score_id):
            continue
        if _has_renewals(settings, UUID(entry["source_id"])):
            return UUID(entry["score_id"]), UUID(entry["source_id"])
    # Not from a scheduled check: match a recent batch to a source by its account IDs.
    candidates = [
        UUID(m["id"])
        for m in sorted(
            sources.list_sources(settings), key=lambda m: m.get("created_at", ""), reverse=True
        )[:20]
        if _has_renewals(settings, UUID(m["id"]))
    ]
    if not candidates:
        return None
    scores_dir = settings.data_directory / "scores"
    ids = [score_id] if score_id else []
    if not ids and scores_dir.is_dir():
        manifests = []
        for path in scores_dir.iterdir():
            try:
                manifests.append(read_score(UUID(path.name), settings.data_directory))
            except (ValueError, WorkflowError, OSError):
                continue
        ids = [m.id for m in sorted(manifests, key=lambda m: m.created_at, reverse=True)[:20]]
    for candidate_score in ids:
        try:
            score = read_score(candidate_score, settings.data_directory)
            customers = read_customers(score, settings.data_directory)
        except WorkflowError:
            continue
        sample = {c.customer_id.rpartition("@")[0] or c.customer_id for c in customers[:200]}
        for source_id in candidates:
            accounts = set(sources.load_tables(settings, source_id)["accounts"]["account_id"])
            if sample and len(sample & {str(a) for a in accounts}) >= 0.5 * len(sample):
                return candidate_score, source_id
    return None


def radar(
    session: Session,
    settings: Settings,
    days: int = 30,
    sort: Sort = "risk",
    score_id: UUID | None = None,
    source_id: UUID | None = None,
) -> dict[str, Any]:
    days = max(1, min(days, MAX_DAYS))
    resolved = _resolve(session, settings, score_id, source_id)
    if resolved is None:
        return {"available": False, "message": UNAVAILABLE, "window_days": days, "items": []}
    score_id, source_id = resolved
    score = read_score(score_id, settings.data_directory)
    customers = read_customers(score, settings.data_directory)
    manifest = sources.read_source(settings, source_id)
    tables = sources.load_tables(settings, source_id)
    accounts = tables["accounts"].copy()
    accounts["account_id"] = accounts["account_id"].astype(str)
    accounts = accounts.set_index("account_id")
    reference = pd.Timestamp(manifest["last_date"])

    invoices = tables.get("invoices")
    last_paid: dict[str, float] = {}
    if invoices is not None and not invoices.empty:
        paid = invoices[invoices["status"].astype(str).str.lower() == "paid"].copy()
        paid["date"] = pd.to_datetime(paid["date"], errors="coerce")
        paid = paid.sort_values("date").groupby("account_id").tail(1)
        last_paid = {
            str(a): float(v) for a, v in zip(paid["account_id"], paid["amount"], strict=True)
        }

    items: list[dict[str, Any]] = []
    for customer in customers:
        account = customer.customer_id.rpartition("@")[0] or customer.customer_id
        if account not in accounts.index:
            continue
        row = accounts.loc[account]
        renews = pd.to_datetime(str(row.get("renews_at") or ""), errors="coerce")
        if pd.isna(renews):
            continue
        days_left = int((renews.normalize() - reference.normalize()).days)
        if days_left > days:
            continue
        items.append(
            {
                "account_id": account,
                "customer_id": customer.customer_id,
                "rank": customer.rank,
                "risk_score": customer.risk_score,
                "level": _level(customer.rank, score.row_count),
                "renews_at": renews.date().isoformat(),
                "days_left": days_left,
                "overdue": days_left < 0,
                "cancel_scheduled": str(row.get("cancel_scheduled") or "").lower() == "yes",
                "amount": last_paid.get(account),
                "billing_cycle": str(row.get("billing_cycle") or "") or None,
                "holdout": customer.group == "holdout",
            }
        )
    keys = {
        "risk": lambda i: (not i["cancel_scheduled"], i["rank"], i["days_left"]),
        "date": lambda i: (i["days_left"], i["rank"]),
        "value": lambda i: (-(i["amount"] or 0), i["rank"]),
    }
    items.sort(key=keys[sort])
    renewing = [i for i in items if not i["overdue"]]
    return {
        "available": True,
        "score_id": str(score_id),
        "source_id": str(source_id),
        "source_name": manifest.get("name"),
        "as_of": reference.date().isoformat(),
        "window_days": days,
        "sort": sort,
        "totals": {
            "renewing": len(renewing),
            "value_renewing": round(sum(i["amount"] or 0 for i in renewing), 2),
            "high_risk": sum(1 for i in renewing if i["level"] == "high"),
            "value_high_risk": round(
                sum(i["amount"] or 0 for i in renewing if i["level"] == "high"), 2
            ),
            "cancel_scheduled": sum(1 for i in items if i["cancel_scheduled"]),
            "overdue": sum(1 for i in items if i["overdue"]),
        },
        "items": items,
    }


def export_csv(session: Session, settings: Settings, days: int, sort: Sort) -> str:
    """The radar as a spreadsheet-safe CSV. The holdout flag stays in the app."""
    result = radar(session, settings, days, sort)
    if not result["available"]:
        raise WorkflowError(UNAVAILABLE, 409)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "account_id",
            "renews_at",
            "days_left",
            "set_to_cancel",
            "last_payment",
            "billing_cycle",
            "risk_rank",
            "risk_score",
            "risk_level",
        ]
    )
    for item in result["items"]:
        writer.writerow(
            [
                spreadsheet_safe(item["account_id"]),
                item["renews_at"],
                item["days_left"],
                "yes" if item["cancel_scheduled"] else "",
                "" if item["amount"] is None else item["amount"],
                spreadsheet_safe(item["billing_cycle"] or ""),
                item["rank"],
                round(item["risk_score"], 4),
                item["level"],
            ]
        )
    return buffer.getvalue()


def digest_line(
    session: Session, settings: Settings, score_id: UUID, source_id: UUID
) -> str | None:
    """One aggregate sentence for the daily digest (no account IDs), or None."""
    try:
        result = radar(session, settings, 30, "risk", score_id, source_id)
    except WorkflowError:
        return None
    if not result["available"] or result.get("score_id") != str(score_id):
        return None
    totals = result["totals"]
    line = f"Renewals in the next 30 days: {totals['renewing']}, {totals['high_risk']} high-risk"
    if totals["value_high_risk"]:
        line += f" ({totals['value_high_risk']:,.0f} renewing on high-risk accounts)"
    if totals["cancel_scheduled"]:
        line += f"; {totals['cancel_scheduled']} already set to cancel"
    return line + "."
