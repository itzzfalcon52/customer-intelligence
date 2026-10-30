"""Razorpay (billing) for the connector pipeline: customers, subscriptions and invoices.

Auth is HTTP basic with the account's key ID and key secret. Lists page with `count` (max 100)
and `skip`. Amounts are in the smallest currency unit (paise) and are divided by 100.

Mapping (assumptions are kept explicit so a live check can confirm them):
- An account is cancelled when every subscription it has ended (`cancelled`, `completed` or
  `expired`); the date is the latest `ended_at` (or `end_at`, then `created_at`).
- Paid invoices are `paid`. An `expired` invoice, or an `issued`/`partially_paid` one whose
  `expire_by` has passed, counts as a failed payment. A `halted` subscription (Razorpay stops
  retrying after repeated charge failures) adds one failed payment dated at its `charge_at`.
- Billing cycle is annual when the plan's period is `yearly`, otherwise monthly.
"""

from collections import defaultdict
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import httpx
import pandas as pd

from customer_intelligence.core.config import Settings
from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.services import connectors

PAGE = 100
ENDED = {"cancelled", "completed", "expired"}


def _client(settings: Settings, key_id: str, key_secret: str) -> httpx.Client:
    return httpx.Client(
        base_url=settings.razorpay_api_base,
        auth=(key_id, key_secret),
        headers={"Accept": "application/json"},
        timeout=30,
        transport=connectors.transport,
        follow_redirects=False,
    )


def _pages(client: httpx.Client, path: str) -> Iterator[dict]:
    for page in range(connectors.MAX_PAGES):
        body = connectors._get(client, path, {"count": PAGE, "skip": page * PAGE})
        items = [i for i in body.get("items") or [] if isinstance(i, dict)]
        yield from items
        if len(items) < PAGE:
            return


def connect(settings: Settings, fields: dict[str, str]) -> dict[str, str]:
    key_id, key_secret = fields.get("key_id", ""), fields.get("key_secret", "")
    if not key_id.startswith("rzp_") or not key_secret:
        raise WorkflowError("Enter the Razorpay key ID (starts with rzp_) and its key secret.")
    with _client(settings, key_id, key_secret) as client:
        connectors._get(client, "/v1/customers", {"count": 1})
    return {"key_id": key_id, "key_secret": key_secret}


def tables(settings: Settings, credential: dict[str, str]) -> dict[str, pd.DataFrame]:
    with _client(settings, credential["key_id"], credential["key_secret"]) as client:
        customers = list(_pages(client, "/v1/customers"))
        subscriptions = list(_pages(client, "/v1/subscriptions"))
        plans = {p.get("id"): p for p in _pages(client, "/v1/plans")}
        invoices = list(_pages(client, "/v1/invoices"))
    return build(customers, subscriptions, plans, invoices)


def build(
    customers: list[dict],
    subscriptions: list[dict],
    plans: dict[Any, dict],
    invoices: list[dict],
    now: datetime | None = None,
) -> dict[str, pd.DataFrame]:
    now = now or datetime.now(UTC)
    day = connectors._day
    by_customer: dict[str, list[dict]] = defaultdict(list)
    for sub in subscriptions:
        if sub.get("customer_id"):
            by_customer[str(sub["customer_id"])].append(sub)
    created = {str(c["id"]): c for c in customers if c.get("id")}
    # Subscriptions can name a customer the customers list didn't return; keep them too.
    for customer_id, subs in by_customer.items():
        created.setdefault(
            customer_id,
            {"id": customer_id, "created_at": min(s.get("created_at") or 0 for s in subs)},
        )
    accounts, failed_rows = [], []
    for customer_id, customer in created.items():
        subs = sorted(by_customer.get(customer_id, []), key=lambda s: s.get("created_at") or 0)
        latest = subs[-1] if subs else {}
        plan = plans.get(latest.get("plan_id")) or {}
        ended = [s for s in subs if s.get("status") in ENDED]
        cancelled = ""
        if subs and len(ended) == len(subs):
            cancelled = day(
                max(
                    (s.get("ended_at") or s.get("end_at") or s.get("created_at") or 0)
                    for s in ended
                )
            )
        accounts.append(
            {
                "account_id": customer_id,
                "domain": connectors._domain(customer.get("email")),
                "created_at": day(customer.get("created_at")),
                "cancelled_at": cancelled,
                "plan": (plan.get("item") or {}).get("name") or latest.get("plan_id") or "",
                "seats": latest.get("quantity"),
                "billing_cycle": "annual" if plan.get("period") == "yearly" else "monthly",
            }
        )
        for sub in subs:
            if sub.get("status") == "halted":
                failed_rows.append(
                    {
                        "account_id": customer_id,
                        "date": day(sub.get("charge_at") or sub.get("created_at")),
                        "amount": 0.0,
                        "status": "failed",
                    }
                )
    rows = []
    stamp = now.timestamp()
    for invoice in invoices:
        owner = str(invoice.get("customer_id") or "")
        status = invoice.get("status")
        if owner not in created:
            continue
        overdue = (
            status in ("issued", "partially_paid") and 0 < (invoice.get("expire_by") or 0) < stamp
        )
        if status == "paid":
            amount, kind = invoice.get("amount_paid") or invoice.get("amount"), "paid"
        elif status == "expired" or overdue:
            amount, kind = invoice.get("amount_due") or invoice.get("amount"), "failed"
        else:
            continue
        rows.append(
            {
                "account_id": owner,
                "date": day(
                    invoice.get("paid_at")
                    or invoice.get("issued_at")
                    or invoice.get("date")
                    or invoice.get("created_at")
                ),
                "amount": float(amount or 0) / 100,
                "status": kind,
            }
        )
    return {
        "accounts": pd.DataFrame(
            accounts,
            columns=[
                "account_id",
                "domain",
                "created_at",
                "cancelled_at",
                "plan",
                "seats",
                "billing_cycle",
            ],
        ),
        "invoices": pd.DataFrame(
            rows + failed_rows, columns=["account_id", "date", "amount", "status"]
        ),
    }
