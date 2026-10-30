"""HubSpot on its own and matched with Stripe, against fake APIs built from synthetic data.

No network: `connectors.transport` routes Stripe paths to `FakeStripe` and HubSpot paths to
`FakeHubSpot`. All data is the labelled synthetic generator's, never real customers.
"""

import json
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pandas as pd
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlmodel import Session
from test_stripe_loop import SECRET as STRIPE_SECRET
from test_stripe_loop import FakeStripe

from customer_intelligence.models.workspace import PendingAction
from customer_intelligence.services import connectors, plays

TOKEN = "pat-na1-synthetic-only-789"
CHURN = "churned_on"


def _iso(day: object) -> str | None:
    if day is None or pd.isna(day) or day == "":
        return None
    return datetime.fromisoformat(str(day)[:10]).replace(tzinfo=UTC).isoformat()


class FakeHubSpot:
    """Companies (one per synthetic account, plus a duplicate domain) and associated tickets."""

    def __init__(self, tables: dict[str, pd.DataFrame]) -> None:
        accounts = tables["accounts"].reset_index(drop=True)
        self.company_of = {a: str(1000 + i) for i, a in enumerate(accounts["account_id"])}
        self.companies = [
            {
                "id": self.company_of[row.account_id],
                "properties": {
                    "createdate": _iso(row.created_at),
                    "industry": row.industry,
                    "domain": f"https://www.{row.account_id.lower()}.example/",
                    CHURN: _iso(row.cancelled_at),
                },
            }
            for row in accounts.itertuples()
        ]
        # A second company claiming the first account's domain makes that domain ambiguous.
        first = accounts["account_id"][0].lower()
        self.companies.append(
            {
                "id": "9999",
                "createdAt": "2025-01-01T00:00:00Z",
                "properties": {"createdate": None, "domain": f"{first}.example"},
            }
        )
        self.tickets = [
            {
                "id": str(5000 + i),
                "properties": {"createdate": _iso(row.created_at), "subject": row.subject},
                "associations": {
                    "companies": {"results": [{"id": self.company_of[row.account_id]}]}
                },
            }
            for i, row in enumerate(tables["tickets"].itertuples())
        ]
        self.tasks: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        path = request.url.path
        if request.method == "POST" and path == "/crm/v3/objects/tasks":
            self.tasks.append(json.loads(request.content))
            return httpx.Response(201, json={"id": str(len(self.tasks))})
        assert request.method == "GET", "only approved plays may write"
        if path == "/crm/v3/properties/companies":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"name": "createdate", "label": "Create date", "type": "datetime"},
                        {"name": CHURN, "label": "Churned on", "type": "date"},
                        {"name": "industry", "label": "Industry", "type": "enumeration"},
                    ]
                },
            )
        objects = {
            "/crm/v3/objects/companies": self.companies,
            "/crm/v3/objects/tickets": self.tickets,
        }.get(path)
        if objects is None:
            return httpx.Response(404, json={})
        if path.endswith("companies") and "properties" in request.url.params:
            wanted = set(request.url.params["properties"].split(","))
            objects = [
                {**o, "properties": {k: v for k, v in o["properties"].items() if k in wanted}}
                for o in objects
            ]
        limit = int(request.url.params.get("limit", 10))
        start = int(request.url.params.get("after", 0))
        page = objects[start : start + limit]
        more = start + limit < len(objects)
        return httpx.Response(
            200,
            json={
                "results": page,
                **({"paging": {"next": {"after": str(start + limit)}}} if more else {}),
            },
        )


@pytest.fixture
def providers(backend, monkeypatch) -> tuple[FakeStripe, FakeHubSpot]:
    stripe = FakeStripe(accounts=400)
    hubspot = FakeHubSpot(stripe.tables)

    def route(request: httpx.Request) -> httpx.Response:
        return stripe(request) if request.url.path.startswith("/v1/") else hubspot(request)

    monkeypatch.setattr(
        backend["settings"], "credentials_key", SecretStr(Fernet.generate_key().decode())
    )
    monkeypatch.setattr(connectors, "transport", httpx.MockTransport(route))
    monkeypatch.setattr(connectors, "sleep", lambda seconds: None)
    return stripe, hubspot


def _connect(client, provider: str, secret: str, label: str) -> str:
    created = client.post(
        "/api/v1/connections", json={"provider": provider, "label": label, "secret": secret}
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _source_dir(backend, source_id: str):
    return backend["settings"].data_directory / "sources" / source_id


def test_hubspot_needs_a_chosen_churn_property(backend, providers):
    client = backend["client"]
    hubspot_id = _connect(client, "hubspot", TOKEN, "CRM")

    unlabelled = client.post(f"/api/v1/connections/{hubspot_id}/sync").json()
    assert unlabelled["cancelled_accounts"] == 0, "churn is never guessed"

    names = [p["name"] for p in client.get(f"/api/v1/connections/{hubspot_id}/properties").json()]
    assert names == [CHURN, "createdate"], "only date properties, sorted by label"
    bad = client.put(f"/api/v1/connections/{hubspot_id}/settings", json={"churn_property": "x"})
    assert bad.status_code == 400
    chosen = client.put(
        f"/api/v1/connections/{hubspot_id}/settings", json={"churn_property": CHURN}
    )
    assert chosen.status_code == 200 and chosen.json()["churn_property"] == CHURN

    source = client.post(f"/api/v1/connections/{hubspot_id}/sync").json()
    assert source["kind"] == "hubspot" and source["cancelled_accounts"] > 0
    accounts = (_source_dir(backend, source["id"]) / "accounts.csv").read_text()
    assert "domain" not in accounts.splitlines()[0] and ".example" not in accounts
    client.delete(f"/api/v1/connections/{hubspot_id}")


def test_stripe_matched_with_hubspot_adds_tickets_and_writes_back(backend, providers):
    stripe, hubspot = providers
    client = backend["client"]
    stripe_id = _connect(client, "stripe", STRIPE_SECRET, "Billing")
    hubspot_id = _connect(client, "hubspot", TOKEN, "CRM")
    wrong = client.put(
        f"/api/v1/connections/{hubspot_id}/settings", json={"enrich_connection_id": stripe_id}
    )
    assert wrong.status_code == 400, "only Stripe is enriched"
    linked = client.put(
        f"/api/v1/connections/{stripe_id}/settings", json={"enrich_connection_id": hubspot_id}
    )
    assert linked.json()["enrich_connection_id"] == hubspot_id

    source = client.post(f"/api/v1/connections/{stripe_id}/sync").json()
    assert source["kind"] == "stripe+hubspot" and source["counts"]["tickets"] > 0
    match = source["match"]
    # 400 accounts: 40 pay from personal mailboxes and one domain is claimed twice.
    assert match["stripe_accounts"] == 400 and match["ambiguous_domains"] == 1
    assert match["matched"] == 400 - 40 - 1
    listed = client.get("/api/v1/connections").json()["connections"]
    assert next(c for c in listed if c["id"] == stripe_id)["last_match"]["matched"] == 359

    directory = _source_dir(backend, source["id"])
    files = "".join((directory / f"{t}.csv").read_text() for t in ("accounts", "tickets"))
    assert ".example" not in files and "gmail" not in files, "domains never reach source files"
    links = json.loads((directory / "links.json").read_text())
    first = next(iter(links))
    assert links[first] == hubspot.company_of[first]

    built = client.post(f"/api/v1/sources/{source['id']}/datasets", json={"horizon_days": 90})
    features = built.json()["recommended_task"]["feature_columns"]
    assert "tickets_90d" in features and "industry" in features

    # An approved play on Stripe-anchored accounts becomes tasks on the matched companies.
    client.put(f"/api/v1/connections/{hubspot_id}/write", json={"enabled": True, "confirm": True})
    targets = list(links)[:3] + [
        next(a for a in stripe.tables["accounts"]["account_id"] if a not in links)
    ]
    action = PendingAction(
        kind="play",
        summary="test",
        payload={
            "score_id": str(uuid4()),
            "title": "Check in",
            "instructions": "Say hello.",
            "accounts": targets,
            "connection_id": hubspot_id,
        },
        origin="user",
    )
    with Session(backend["app"].state.engine) as session:
        result = plays.execute(session, backend["settings"], action)
    assert result == {"destination": "hubspot", "written": 3, "skipped": 1, "failed": 0}
    associated = [t["associations"][0]["to"]["id"] for t in hubspot.tasks]
    assert associated == [hubspot.company_of[a] for a in targets[:3]]

    # Removing HubSpot unlinks the Stripe connection; the next sync is billing-only again.
    assert client.delete(f"/api/v1/connections/{hubspot_id}").status_code == 204
    after = client.get("/api/v1/connections").json()["connections"]
    assert next(c for c in after if c["id"] == stripe_id)["enrich_connection_id"] is None
    assert client.post(f"/api/v1/connections/{stripe_id}/sync").json()["kind"] == "stripe"
    client.delete(f"/api/v1/connections/{stripe_id}")


def test_merge_keeps_stripe_as_the_record_of_cancellation():
    stripe = {
        "accounts": pd.DataFrame(
            {
                "account_id": ["cus_1", "cus_2"],
                "domain": ["a.example", ""],
                "created_at": ["2026-01-01", "2026-01-01"],
                "cancelled_at": ["2026-05-01", ""],
            }
        )
    }
    hubspot = {
        "accounts": pd.DataFrame(
            {
                "account_id": ["11"],
                "domain": ["a.example"],
                "created_at": ["2025-01-01"],
                "cancelled_at": [""],
                "industry": ["Retail"],
            }
        ),
        "tickets": pd.DataFrame({"account_id": ["11"], "created_at": ["2026-02-01"]}),
    }
    tables, links, stats = connectors.merge(stripe, hubspot)
    assert links == {"cus_1": "11"} and stats["matched"] == 1 and stats["rate"] == 0.5
    assert list(tables["accounts"]["cancelled_at"]) == ["2026-05-01", ""]
    assert list(tables["accounts"]["industry"]) == ["Retail", ""]
    assert list(tables["tickets"]["account_id"]) == ["cus_1"]
    assert connectors._domain("Owner@Sub.A.Example") == "sub.a.example"
    assert connectors._domain("https://www.a.example/path") == "a.example"
    assert connectors._domain("not a domain") == ""
