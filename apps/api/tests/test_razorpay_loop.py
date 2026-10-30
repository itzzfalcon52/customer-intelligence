"""Razorpay end to end against a fake API built from the labelled synthetic generator.

connect → sync → train from the synced source → make active → schedule → daily cycle → digest,
plus the status mapping. No network: `connectors.transport` routes requests to `FakeRazorpay`.
"""

import base64
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pandas as pd
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlmodel import Session

from customer_intelligence.services import connectors, razorpay
from customer_intelligence.services.sources import synthetic_tables
from customer_intelligence.services.training import train_task

KEY_ID = "rzp_test_synthetic123"
KEY_SECRET = "synthetic_secret_do_not_leak"


def _ts(day: object) -> int | None:
    if day is None or pd.isna(day) or day == "":
        return None
    return int(datetime.fromisoformat(str(day)[:10]).replace(tzinfo=UTC).timestamp())


class FakeRazorpay:
    """Razorpay-shaped collections (count/skip paging). Synthetic data, not real customers."""

    def __init__(self, accounts: int = 500) -> None:
        tables = synthetic_tables(seed=13, accounts=accounts)
        self.plans = [
            {"id": "plan_m", "period": "monthly", "item": {"name": "Growth"}},
            {"id": "plan_y", "period": "yearly", "item": {"name": "Growth annual"}},
        ]
        self.customers, self.subscriptions = [], []
        for i, row in enumerate(tables["accounts"].itertuples()):
            customer = f"cust_{i:05d}"
            self.customers.append(
                {
                    "id": customer,
                    "email": f"accounts@{row.account_id.lower()}.example",
                    "created_at": _ts(row.created_at),
                }
            )
            ended = _ts(row.cancelled_at)
            self.subscriptions.append(
                {
                    "id": f"sub_{i:05d}",
                    "customer_id": customer,
                    "plan_id": "plan_y" if row.billing_cycle == "annual" else "plan_m",
                    "quantity": int(row.seats),
                    "status": "cancelled" if ended else "active",
                    "created_at": _ts(row.created_at),
                    "ended_at": ended,
                }
            )
        ids = {
            row.account_id: f"cust_{i:05d}" for i, row in enumerate(tables["accounts"].itertuples())
        }
        self.invoices = [
            {
                "id": f"inv_{i}",
                "customer_id": ids[row.account_id],
                "status": "paid" if row.status == "paid" else "expired",
                "amount": int(row.amount * 100),
                "amount_paid": int(row.amount * 100) if row.status == "paid" else 0,
                "amount_due": int(row.amount * 100),
                "issued_at": _ts(row.date),
                "paid_at": _ts(row.date) if row.status == "paid" else None,
            }
            for i, row in enumerate(tables["invoices"].itertuples())
        ]
        self.requests = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.method == "GET", "the Razorpay connector must only read"
        expected = base64.b64encode(f"{KEY_ID}:{KEY_SECRET}".encode()).decode()
        if request.headers.get("Authorization") != f"Basic {expected}":
            return httpx.Response(401, json={"error": {"code": "BAD_REQUEST_ERROR"}})
        self.requests += 1
        items = {
            "/v1/customers": self.customers,
            "/v1/subscriptions": self.subscriptions,
            "/v1/plans": self.plans,
            "/v1/invoices": self.invoices,
        }.get(request.url.path)
        if items is None:
            return httpx.Response(404, json={})
        count = min(int(request.url.params.get("count", 10)), 100)
        skip = int(request.url.params.get("skip", 0))
        page = items[skip : skip + count]
        return httpx.Response(200, json={"entity": "collection", "count": len(page), "items": page})


@pytest.fixture
def fake(backend, monkeypatch) -> FakeRazorpay:
    server = FakeRazorpay()
    monkeypatch.setattr(
        backend["settings"], "credentials_key", SecretStr(Fernet.generate_key().decode())
    )
    monkeypatch.setattr(connectors, "transport", httpx.MockTransport(server))
    monkeypatch.setattr(connectors, "sleep", lambda seconds: None)
    return server


def _connect(client, key_id: str = KEY_ID, key_secret: str = KEY_SECRET):
    return client.post(
        "/api/v1/connections",
        json={
            "provider": "razorpay",
            "label": "Payments",
            "fields": {"key_id": key_id, "key_secret": key_secret},
        },
    )


def test_wrong_razorpay_keys_are_rejected_without_echoing_them(backend, fake):
    client = backend["client"]
    malformed = _connect(client, key_id="not-a-key")
    assert malformed.status_code == 400 and "rzp_" in malformed.text
    wrong = _connect(client, key_secret="wrong_secret_value")
    assert wrong.status_code == 400 and "rejected the key" in wrong.text
    assert "wrong_secret_value" not in wrong.text and KEY_SECRET not in wrong.text


def test_razorpay_feeds_the_daily_loop(backend, fake, execute_job):
    client = backend["client"]
    created = _connect(client)
    assert created.status_code == 201, created.text
    assert KEY_SECRET not in created.text
    connection_id = created.json()["id"]

    source = client.post(f"/api/v1/connections/{connection_id}/sync")
    assert source.status_code == 201, source.text
    source = source.json()
    assert source["kind"] == "razorpay" and source["counts"]["accounts"] == 500
    assert source["cancelled_accounts"] > 0
    files = backend["settings"].data_directory / "sources" / source["id"] / "accounts.csv"
    assert ".example" not in files.read_text(), "email domains never reach source files"

    built = client.post(f"/api/v1/sources/{source['id']}/datasets", json={"horizon_days": 90})
    assert built.status_code in (200, 201), built.text
    built = built.json()
    task = client.post(
        f"/api/v1/datasets/{built['dataset_id']}/tasks",
        json={**built["recommended_task"], "features_available_at_prediction": True},
    )
    assert task.status_code == 201, task.text
    with Session(backend["app"].state.engine) as session:
        session.info["settings"] = backend["settings"]
        run_id = train_task(session, backend["settings"], UUID(task.json()["id"])).name
    assert client.post("/api/v1/registry/promote", json={"run_id": run_id}).status_code == 200
    schedule = client.put(
        "/api/v1/schedule", json={"enabled": True, "connection_id": connection_id}
    )
    assert schedule.status_code == 200, schedule.text

    before = fake.requests
    finished = execute_job(client.post("/api/v1/schedule/run").json()["id"])
    assert finished["state"] == "succeeded", finished["error"]
    assert fake.requests > before, "the daily cycle pulls fresh data from Razorpay"
    assert "Scored" in client.get("/api/v1/digest").json()[0]["body"]
    client.delete(f"/api/v1/connections/{connection_id}")


def test_razorpay_status_mapping():
    now = datetime(2026, 10, 1, tzinfo=UTC)
    day = lambda d: int(datetime.fromisoformat(d).replace(tzinfo=UTC).timestamp())  # noqa: E731
    tables = razorpay.build(
        customers=[
            {"id": "c1", "email": "a@one.example", "created_at": day("2026-01-01")},
            {"id": "c2", "email": "b@two.example", "created_at": day("2026-01-01")},
        ],
        subscriptions=[
            {
                "customer_id": "c1",
                "plan_id": "y",
                "status": "cancelled",
                "created_at": day("2026-01-01"),
                "ended_at": day("2026-06-01"),
            },  # noqa: E501
            {
                "customer_id": "c1",
                "plan_id": "y",
                "status": "completed",
                "created_at": day("2026-02-01"),
                "end_at": day("2026-07-01"),
            },  # noqa: E501
            {
                "customer_id": "c2",
                "plan_id": "m",
                "status": "halted",
                "created_at": day("2026-01-01"),
                "charge_at": day("2026-08-01"),
            },  # noqa: E501
            {
                "customer_id": "c3",
                "plan_id": "m",
                "status": "active",
                "created_at": day("2026-03-01"),
            },  # noqa: E501
        ],
        plans={"y": {"period": "yearly", "item": {"name": "Pro"}}, "m": {"period": "monthly"}},
        invoices=[
            {
                "customer_id": "c1",
                "status": "paid",
                "amount_paid": 49900,
                "paid_at": day("2026-02-01"),
            },  # noqa: E501
            {
                "customer_id": "c2",
                "status": "expired",
                "amount_due": 1000,
                "issued_at": day("2026-03-01"),
            },  # noqa: E501
            {
                "customer_id": "c2",
                "status": "issued",
                "amount_due": 1000,
                "expire_by": day("2026-09-01"),
                "issued_at": day("2026-08-20"),
            },  # noqa: E501
            {
                "customer_id": "c2",
                "status": "issued",
                "amount_due": 1000,
                "expire_by": day("2026-12-01"),
                "issued_at": day("2026-09-20"),
            },  # noqa: E501
            {"customer_id": "c2", "status": "draft", "amount_due": 1000},
        ],
        now=now,
    )
    accounts = tables["accounts"].set_index("account_id")
    assert accounts.loc["c1", "cancelled_at"] == "2026-07-01", "latest end of all-ended subs"
    assert accounts.loc["c1", "billing_cycle"] == "annual" and accounts.loc["c1", "plan"] == "Pro"
    assert accounts.loc["c2", "cancelled_at"] == "", "a halted subscription is not a cancellation"
    assert "c3" in accounts.index, "a subscription's unknown customer is still an account"
    invoices = tables["invoices"]
    assert invoices[invoices["status"] == "paid"]["amount"].tolist() == [499.0]
    failed = invoices[(invoices["account_id"] == "c2") & (invoices["status"] == "failed")]
    # expired + overdue issued + halted subscription; the not-yet-due issued and draft are skipped
    assert len(failed) == 3
