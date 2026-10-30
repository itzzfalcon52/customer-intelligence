import json

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlmodel import Session, select

from customer_intelligence.models.connection import Connection
from customer_intelligence.services import connectors

SECRET = "sk_test_do_not_leak_123"
DAY = 86_400
T0 = 1_700_000_000


def stripe_api(request: httpx.Request) -> httpx.Response:
    assert request.method == "GET", "connectors must only read"
    assert request.headers["Authorization"] == f"Bearer {SECRET}"
    path = request.url.path
    if path == "/v1/customers":
        if request.url.params.get("starting_after") is None and request.url.params["limit"] == "1":
            return httpx.Response(200, json={"data": [{"id": "cus_1"}], "has_more": True})
        page = request.url.params.get("starting_after")
        if page is None:
            return httpx.Response(
                200,
                json={
                    "data": [{"id": "cus_1", "created": T0}, {"id": "cus_2", "created": T0}],
                    "has_more": True,
                },
            )
        return httpx.Response(
            200, json={"data": [{"id": "cus_3", "created": T0}], "has_more": False}
        )
    if path == "/v1/subscriptions":
        item = lambda interval, qty: {  # noqa: E731
            "items": {
                "data": [
                    {
                        "quantity": qty,
                        "price": {"nickname": "Pro", "recurring": {"interval": interval}},
                    }
                ]
            }
        }
        return httpx.Response(
            200,
            json={
                "data": [
                    {"customer": "cus_1", "status": "active", "created": T0, **item("month", 5)},
                    {
                        "customer": "cus_2",
                        "status": "canceled",
                        "created": T0,
                        "ended_at": T0 + 90 * DAY,
                        **item("year", 2),
                    },
                ],
                "has_more": False,
            },
        )
    if path == "/v1/invoices":
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "customer": "cus_1",
                        "created": T0 + DAY,
                        "status": "paid",
                        "amount_paid": 5000,
                    },
                    {
                        "customer": "cus_2",
                        "created": T0 + 30 * DAY,
                        "status": "open",
                        "attempt_count": 2,
                        "amount_due": 24000,
                    },
                    {
                        "customer": "cus_2",
                        "created": T0 + 31 * DAY,
                        "status": "draft",
                        "amount_due": 1,
                    },
                ],
                "has_more": False,
            },
        )
    return httpx.Response(404)


@pytest.fixture
def keyed(backend, monkeypatch):
    settings = backend["settings"]
    monkeypatch.setattr(settings, "credentials_key", SecretStr(Fernet.generate_key().decode()))
    monkeypatch.setattr(connectors, "transport", httpx.MockTransport(stripe_api))
    return backend


def test_connectors_need_a_key(backend):
    response = backend["client"].post(
        "/api/v1/connections", json={"provider": "stripe", "label": "Live", "secret": SECRET}
    )
    assert response.status_code == 409 and "CI_CREDENTIALS_KEY" in response.text
    assert SECRET not in response.text


def test_stripe_sync_builds_a_source_without_leaking_the_secret(keyed):
    client = keyed["client"]
    created = client.post(
        "/api/v1/connections", json={"provider": "stripe", "label": "Billing", "secret": SECRET}
    )
    assert created.status_code == 201, created.text
    assert SECRET not in created.text
    with Session(keyed["app"].state.engine) as session:
        stored = session.exec(select(Connection)).one()
        assert SECRET not in stored.secret_ciphertext
    listed = client.get("/api/v1/connections").json()
    assert listed["enabled"] and SECRET not in json.dumps(listed)
    source = client.post(f"/api/v1/connections/{created.json()['id']}/sync")
    assert source.status_code == 201, source.text
    manifest = source.json()
    assert manifest["kind"] == "stripe" and manifest["counts"]["accounts"] == 3
    assert manifest["cancelled_accounts"] == 1
    tables = keyed["settings"].data_directory / "sources" / manifest["id"]
    accounts = (tables / "accounts.csv").read_text()
    invoices = (tables / "invoices.csv").read_text()
    assert "annual" in accounts and "failed" in invoices and "draft" not in invoices
    assert SECRET not in accounts + invoices
    assert (
        client.get("/api/v1/connections").json()["connections"][0]["last_source_id"]
        == manifest["id"]
    )


def test_bad_credentials_are_rejected(keyed, monkeypatch):
    monkeypatch.setattr(
        connectors, "transport", httpx.MockTransport(lambda r: httpx.Response(401, json={}))
    )
    response = keyed["client"].post(
        "/api/v1/connections", json={"provider": "hubspot", "label": "CRM", "secret": SECRET}
    )
    assert response.status_code == 400 and SECRET not in response.text
