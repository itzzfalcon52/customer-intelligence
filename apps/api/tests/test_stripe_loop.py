"""The Stripe connector end to end, against a fake Stripe API serving labelled synthetic data.

connect → sync → train from the synced source → make active → schedule → daily cycle → digest.
No network: `connectors.transport` routes every request to `FakeStripe`.
"""

from datetime import UTC, datetime
from uuid import UUID

import httpx
import pandas as pd
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlmodel import Session

from customer_intelligence.services import connectors
from customer_intelligence.services.sources import synthetic_tables
from customer_intelligence.services.training import train_task

SECRET = "rk_test_synthetic_only_456"


def _ts(day: object) -> int | None:
    if day is None or pd.isna(day) or day == "":
        return None
    return int(datetime.fromisoformat(str(day)[:10]).replace(tzinfo=UTC).timestamp())


class FakeStripe:
    """Stripe-shaped pages built from the synthetic generator (synthetic data, not customers)."""

    def __init__(self, accounts: int = 500) -> None:
        tables = synthetic_tables(seed=11, accounts=accounts)
        # Every tenth customer pays with a personal mailbox, which must never be matched.
        self.customers = [
            {
                "id": row.account_id,
                "created": _ts(row.created_at),
                "email": f"owner{i}@gmail.com"
                if i % 10 == 9
                else f"billing@{row.account_id.lower()}.example",
            }
            for i, row in enumerate(tables["accounts"].itertuples())
        ]
        self.tables = tables
        self.subscriptions = []
        for row in tables["accounts"].itertuples():
            ended = _ts(row.cancelled_at)
            self.subscriptions.append(
                {
                    "id": f"sub_{row.account_id}",
                    "customer": row.account_id,
                    "created": _ts(row.created_at),
                    "status": "canceled" if ended else "active",
                    "ended_at": ended,
                    "items": {
                        "data": [
                            {
                                "quantity": int(row.seats),
                                "price": {
                                    "nickname": row.plan,
                                    "recurring": {
                                        "interval": "year"
                                        if row.billing_cycle == "annual"
                                        else "month"
                                    },
                                },
                            }
                        ]
                    },
                }
            )
        self.invoices = [
            {
                "id": f"in_{i}",
                "customer": row.account_id,
                "created": _ts(row.date),
                "status": "paid" if row.status == "paid" else "open",
                "attempt_count": 0 if row.status == "paid" else 2,
                "amount_paid": int(row.amount * 100) if row.status == "paid" else 0,
                "amount_due": int(row.amount * 100),
            }
            for i, row in enumerate(tables["invoices"].itertuples())
        ]
        self.requests = 0
        self.fail_once: set[str] = set()
        self.forbidden: set[str] = set()

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.method == "GET", "the Stripe connector must only read"
        assert request.headers["Authorization"] == f"Bearer {SECRET}"
        self.requests += 1
        path = request.url.path
        if path in self.forbidden:
            return httpx.Response(403, json={"error": {"type": "invalid_request_error"}})
        if path in self.fail_once:
            self.fail_once.discard(path)
            return httpx.Response(503, headers={"Retry-After": "0"}, json={})
        objects = {
            "/v1/customers": self.customers,
            "/v1/subscriptions": self.subscriptions,
            "/v1/invoices": self.invoices,
        }.get(path)
        if objects is None:
            return httpx.Response(404, json={})
        limit = int(request.url.params.get("limit", 10))
        after = request.url.params.get("starting_after")
        start = next(i + 1 for i, o in enumerate(objects) if o["id"] == after) if after else 0
        page = objects[start : start + limit]
        return httpx.Response(200, json={"data": page, "has_more": start + limit < len(objects)})


@pytest.fixture
def stripe(backend, monkeypatch) -> FakeStripe:
    fake = FakeStripe()
    monkeypatch.setattr(
        backend["settings"], "credentials_key", SecretStr(Fernet.generate_key().decode())
    )
    monkeypatch.setattr(connectors, "transport", httpx.MockTransport(fake))
    monkeypatch.setattr(connectors, "sleep", lambda seconds: None)
    return fake


def test_stripe_feeds_the_daily_loop(backend, stripe, execute_job):
    client = backend["client"]
    created = client.post(
        "/api/v1/connections", json={"provider": "stripe", "label": "Billing", "secret": SECRET}
    )
    assert created.status_code == 201, created.text
    connection_id = created.json()["id"]

    stripe.fail_once.add("/v1/invoices")  # a transient 503 is retried, not surfaced
    synced = client.post(f"/api/v1/connections/{connection_id}/sync")
    assert synced.status_code == 201, synced.text
    source = synced.json()
    assert source["kind"] == "stripe" and source["counts"]["accounts"] == 500
    listed = client.get("/api/v1/connections").json()["connections"][0]
    assert listed["last_counts"]["accounts"] == 500 and listed["last_counts"]["cancelled"] > 0

    # Train from the synced source exactly as the Sources page does.
    built = client.post(f"/api/v1/sources/{source['id']}/datasets", json={"horizon_days": 90})
    assert built.status_code in (200, 201), built.text
    built = built.json()
    assert built["positive_rate"] and 0 < built["positive_rate"] < 1
    task = client.post(
        f"/api/v1/datasets/{built['dataset_id']}/tasks",
        json={**built["recommended_task"], "features_available_at_prediction": True},
    )
    assert task.status_code == 201, task.text
    task = task.json()
    with Session(backend["app"].state.engine) as session:
        session.info["settings"] = backend["settings"]
        run_id = train_task(session, backend["settings"], UUID(task["id"])).name
    assert client.post("/api/v1/registry/promote", json={"run_id": run_id}).status_code == 200

    schedule = client.put(
        "/api/v1/schedule",
        json={"enabled": True, "connection_id": connection_id, "contact_count": 20},
    )
    assert schedule.status_code == 200, schedule.text

    before = stripe.requests
    job = client.post("/api/v1/schedule/run").json()
    finished = execute_job(job["id"])
    assert finished["state"] == "succeeded", finished["error"]
    assert stripe.requests > before, "the daily cycle pulls fresh data from Stripe"
    item = client.get("/api/v1/digest").json()[0]
    assert item["kind"] == "cycle" and "Scored" in item["body"]

    # Removing the connection pauses the schedule instead of failing every day.
    assert client.delete(f"/api/v1/connections/{connection_id}").status_code == 204
    paused = client.get("/api/v1/schedule").json()
    assert paused["enabled"] is False and paused["connection_id"] is None


def test_schedule_refuses_a_model_trained_on_other_data(backend, trained, stripe):
    client = backend["client"]
    connection_id = client.post(
        "/api/v1/connections", json={"provider": "stripe", "label": "Other", "secret": SECRET}
    ).json()["id"]
    assert client.post(f"/api/v1/connections/{connection_id}/sync").status_code == 201
    client.post("/api/v1/registry/promote", json={"run_id": trained["run_id"]})
    refused = client.put("/api/v1/schedule", json={"enabled": True, "connection_id": connection_id})
    assert refused.status_code == 400 and "trained on different data" in refused.text
    client.delete(f"/api/v1/connections/{connection_id}")


def test_missing_key_permission_names_the_object(backend, stripe):
    stripe.forbidden.add("/v1/subscriptions")
    client = backend["client"]
    connection_id = client.post(
        "/api/v1/connections", json={"provider": "stripe", "label": "Narrow", "secret": SECRET}
    ).json()["id"]
    failed = client.post(f"/api/v1/connections/{connection_id}/sync")
    assert failed.status_code == 400 and "can't read subscriptions" in failed.text
    assert SECRET not in failed.text
    listed = client.get("/api/v1/connections").json()["connections"]
    assert any("subscriptions" in (c["last_error"] or "") for c in listed)
    client.delete(f"/api/v1/connections/{connection_id}")
