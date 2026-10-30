"""Zoho CRM and Zoho Billing against a fake Zoho (accounts server, CRM v8 and Billing v1).

No network: `connectors.transport` routes everything to `FakeZoho`; `zoho_accounts_base` and
`zoho_api_base` point at it. All records are synthetic, never real customers.
"""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlmodel import Session, select

from customer_intelligence.models.connection import Connection
from customer_intelligence.models.workspace import PendingAction
from customer_intelligence.services import connectors, plays

BASE = "https://fake.zoho.test"
CLIENT_ID = "1000.SYNTHETICCLIENT"
CLIENT_SECRET = "synthetic_client_secret_do_not_leak"
CODE = "1000.one_time_code"
REFRESH = "1000.synthetic_refresh_token"
ACCESS = "1000.synthetic_access_token"
ORG = "60000001"
CHURN = "Churned_On"


class FakeZoho:
    def __init__(self, accounts: int = 2100) -> None:
        start = datetime(2024, 1, 1, tzinfo=UTC)
        self.accounts = [
            {
                "id": str(5_000_000 + i),
                "Account_Name": f"Synthetic {i}",
                "Website": f"https://www.co{i}.example",
                "Industry": ["Retail", "Software", "Health"][i % 3],
                "Created_Time": (start + timedelta(days=i % 300)).isoformat(),
                CHURN: (start + timedelta(days=400 + i % 100)).date().isoformat()
                if i % 4 == 0
                else None,
            }
            for i in range(accounts)
        ]
        self.cases = [
            {
                "id": str(9_000_000 + i),
                "Subject": "Billing question",
                "Description": "Invoice did not arrive",
                "Created_Time": (start + timedelta(days=200 + i)).isoformat(),
                "Account_Name": {"name": f"Synthetic {i}", "id": str(5_000_000 + i)},
            }
            for i in range(0, 300, 3)
        ]
        # Billing: 50 customers. Even ones carry Zoho's own CRM link; odd ones only an email.
        self.customers = [
            {
                "customer_id": str(7_000 + i),
                "email": f"finance@co{i}.example" if i % 5 else f"owner{i}@gmail.com",
                "created_time": (start + timedelta(days=i)).isoformat(),
                "zcrm_account_id": str(5_000_000 + i) if i % 2 == 0 else "",
            }
            for i in range(50)
        ]
        self.subscriptions = [
            {
                "subscription_id": str(8_000 + i),
                "customer_id": str(7_000 + i),
                "status": "cancelled" if i % 3 == 0 else "live",
                "plan_name": "Pro",
                "interval_unit": "years" if i % 2 else "months",
                "created_time": (start + timedelta(days=i)).isoformat(),
                "cancelled_date": (start + timedelta(days=300 + i)).date().isoformat()
                if i % 3 == 0
                else None,
            }
            for i in range(50)
        ]
        self.invoices = [
            {
                "invoice_id": str(9_100 + i),
                "customer_id": str(7_000 + i % 50),
                "status": ["paid", "overdue", "paid", "void"][i % 4],
                "total": 1200.0,
                "balance": 1200.0 if i % 4 == 1 else 0.0,
                "date": (start + timedelta(days=30 * (i % 10))).date().isoformat(),
            }
            for i in range(200)
        ]
        self.orgs = [{"organization_id": ORG, "name": "Synthetic Pvt Ltd"}]
        self.cases_status = 200
        self.tasks: list[dict] = []
        self.tokens_issued = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/oauth/v2/token":
            form = dict(x.split("=", 1) for x in request.content.decode().split("&"))
            if form.get("client_id") != CLIENT_ID or form.get("client_secret") != CLIENT_SECRET:
                return httpx.Response(200, json={"error": "invalid_client"})
            if form["grant_type"] == "authorization_code":
                if form.get("code") != CODE:
                    return httpx.Response(200, json={"error": "invalid_code"})
                return httpx.Response(
                    200,
                    json={
                        "access_token": ACCESS,
                        "refresh_token": REFRESH,
                        "api_domain": "https://www.zohoapis.in",
                        "expires_in": 3600,
                    },
                )
            assert form["grant_type"] == "refresh_token" and form["refresh_token"] == REFRESH
            self.tokens_issued += 1
            return httpx.Response(
                200, json={"access_token": ACCESS, "api_domain": "https://www.zohoapis.in"}
            )
        assert request.headers["Authorization"] == f"Zoho-oauthtoken {ACCESS}"
        if path.startswith("/billing/v1/"):
            return self.billing(request, path)
        if path == "/crm/v8/Tasks":
            assert request.method == "POST"
            body = json.loads(request.content)
            self.tasks.extend(body["data"])
            return httpx.Response(201, json={"data": [{"status": "success"} for _ in body["data"]]})
        assert request.method == "GET", "only approved plays may write"
        if path == "/crm/v8/settings/fields":
            return httpx.Response(
                200,
                json={
                    "fields": [
                        {
                            "api_name": "Created_Time",
                            "field_label": "Created Time",
                            "data_type": "datetime",
                        },  # noqa: E501
                        {"api_name": CHURN, "field_label": "Churned on", "data_type": "date"},
                        {
                            "api_name": "Industry",
                            "field_label": "Industry",
                            "data_type": "picklist",
                        },  # noqa: E501
                    ]
                },
            )
        if path == "/crm/v8/Cases" and self.cases_status != 200:
            return httpx.Response(
                self.cases_status, json={"code": "OAUTH_SCOPE_MISMATCH", "status": "error"}
            )
        records = {"/crm/v8/Accounts": self.accounts, "/crm/v8/Cases": self.cases}.get(path)
        if records is None:
            return httpx.Response(404, json={})
        params = request.url.params
        per_page = min(int(params.get("per_page", 200)), 200)
        if "page_token" in params:
            start = int(params["page_token"].removeprefix("tok"))
        else:
            page = int(params.get("page", 1))
            start = (page - 1) * per_page
            if start + per_page > 2000:
                return httpx.Response(
                    400, json={"code": "DISCRETE_PAGINATION_LIMIT_EXCEEDED", "status": "error"}
                )
        chunk = records[start : start + per_page]
        if not chunk:
            return httpx.Response(204)
        fields = set(params.get("fields", "").split(",")) | {"id"}
        more = start + per_page < len(records)
        return httpx.Response(
            200,
            json={
                "data": [{k: v for k, v in r.items() if k in fields} for r in chunk],
                "info": {
                    "per_page": per_page,
                    "more_records": more,
                    "next_page_token": f"tok{start + per_page}" if more else None,
                },
            },
        )

    def billing(self, request: httpx.Request, path: str) -> httpx.Response:
        assert request.method == "GET"
        if path == "/billing/v1/organizations":
            return httpx.Response(200, json={"organizations": self.orgs})
        assert request.headers.get("X-com-zoho-subscriptions-organizationid") == ORG
        key = path.rsplit("/", 1)[1]
        records = {
            "customers": self.customers,
            "subscriptions": self.subscriptions,
            "invoices": self.invoices,
        }.get(key)
        if records is None:
            return httpx.Response(404, json={})
        page = int(request.url.params.get("page", 1))
        per_page = int(request.url.params.get("per_page", 200))
        start = (page - 1) * per_page
        return httpx.Response(
            200,
            json={
                key: records[start : start + per_page],
                "page_context": {"has_more_page": start + per_page < len(records)},
            },
        )


@pytest.fixture
def zoho(backend, monkeypatch) -> FakeZoho:
    fake = FakeZoho()
    settings = backend["settings"]
    monkeypatch.setattr(settings, "credentials_key", SecretStr(Fernet.generate_key().decode()))
    monkeypatch.setattr(settings, "zoho_accounts_base", BASE)
    monkeypatch.setattr(settings, "zoho_api_base", BASE)
    monkeypatch.setattr(connectors, "transport", httpx.MockTransport(fake))
    monkeypatch.setattr(connectors, "sleep", lambda seconds: None)
    yield fake
    client = backend["client"]
    for c in client.get("/api/v1/connections").json()["connections"]:
        client.delete(f"/api/v1/connections/{c['id']}")


def _connect(client, provider: str, label: str, **overrides):
    fields = {
        "region": "in",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": CODE,
        **overrides,
    }
    return client.post(
        "/api/v1/connections", json={"provider": provider, "label": label, "fields": fields}
    )


def test_zoho_codes_are_exchanged_once_and_never_stored(backend, zoho):
    client = backend["client"]
    bad = _connect(client, "zoho_crm", "CRM", code="1000.expired")
    assert bad.status_code == 400 and "one-time code" in bad.text
    region = _connect(client, "zoho_crm", "CRM", region="mars")
    assert region.status_code == 400
    created = _connect(client, "zoho_crm", "CRM")
    assert created.status_code == 201, created.text
    for secret in (CLIENT_SECRET, CODE, REFRESH, ACCESS):
        assert secret not in created.text
        assert secret not in json.dumps(client.get("/api/v1/connections").json())
    with Session(backend["app"].state.engine) as session:
        stored = session.exec(select(Connection)).one()
        assert CLIENT_SECRET not in stored.secret_ciphertext
        saved = connectors.credential(backend["settings"], stored)
    assert saved["refresh_token"] == REFRESH and "code" not in saved


def test_zoho_crm_pages_past_2000_accounts_and_reads_cases(backend, zoho):
    client = backend["client"]
    crm = _connect(client, "zoho_crm", "CRM").json()["id"]
    fields = client.get(f"/api/v1/connections/{crm}/properties").json()
    assert [f["name"] for f in fields] == [CHURN, "Created_Time"], "date fields, by label"
    chosen = client.put(f"/api/v1/connections/{crm}/settings", json={"churn_property": CHURN})
    assert chosen.status_code == 200, chosen.text

    source = client.post(f"/api/v1/connections/{crm}/sync")
    assert source.status_code == 201, source.text
    source = source.json()
    assert source["kind"] == "zoho_crm" and source["counts"]["accounts"] == 2100
    assert source["cancelled_accounts"] == 525 and source["counts"]["tickets"] == 100
    folder = backend["settings"].data_directory / "sources" / source["id"]
    assert ".example" not in (folder / "accounts.csv").read_text()

    zoho.cases_status = 401
    partial = client.post(f"/api/v1/connections/{crm}/sync").json()
    assert partial["counts"]["tickets"] == 0
    assert any("Cases" in note for note in partial["notes"])


def test_zoho_billing_needs_one_organisation(backend, zoho):
    client = backend["client"]
    zoho.orgs = [*zoho.orgs, {"organization_id": "60000002", "name": "Other Ltd"}]
    several = _connect(client, "zoho_billing", "Billing")
    assert several.status_code == 400 and "60000002" in several.text
    picked = _connect(client, "zoho_billing", "Billing", organization_id=ORG)
    assert picked.status_code == 201, picked.text


def test_zoho_billing_links_to_zoho_crm_and_writes_tasks(backend, zoho):
    client = backend["client"]
    crm = _connect(client, "zoho_crm", "CRM").json()["id"]
    client.put(f"/api/v1/connections/{crm}/settings", json={"churn_property": CHURN})
    billing = _connect(client, "zoho_billing", "Billing").json()["id"]
    linked = client.put(
        f"/api/v1/connections/{billing}/settings", json={"enrich_connection_id": crm}
    )
    assert linked.status_code == 200, linked.text

    source = client.post(f"/api/v1/connections/{billing}/sync")
    assert source.status_code == 201, source.text
    source = source.json()
    assert source["kind"] == "zoho_billing+zoho_crm"
    assert source["cancelled_accounts"] == 17  # billing owns cancellations: 0, 3, …, 48
    match = source["match"]
    # 25 even customers carry Zoho's CRM link; of the 25 odd ones, 5 use a personal mailbox.
    assert match["matched_by_crm_id"] == 25 and match["matched"] == 45
    folder = backend["settings"].data_directory / "sources" / source["id"]
    saved = (folder / "accounts.csv").read_text()
    assert "crm_id" not in saved and "5000000" not in saved and ".example" not in saved
    invoices = (folder / "invoices.csv").read_text()
    assert "failed" in invoices and "void" not in invoices

    client.put(f"/api/v1/connections/{crm}/write", json={"enabled": True, "confirm": True})
    action = PendingAction(
        kind="play",
        summary="test",
        payload={
            "score_id": str(uuid4()),
            "title": "Renewal call",
            "instructions": "Call before renewal.",
            "accounts": ["7000", "7001", "7005", "unknown"],
            "connection_id": crm,
        },
        origin="user",
    )
    with Session(backend["app"].state.engine) as session:
        result = plays.execute(session, backend["settings"], action)
    # 7000 by CRM ID, 7001 by domain; 7005 pays from gmail and "unknown" isn't a customer.
    assert result == {"destination": "zoho_crm", "written": 2, "skipped": 2, "failed": 0}
    assert [t["What_Id"]["id"] for t in zoho.tasks] == ["5000000", "5000001"]
    assert all(t["$se_module"] == "Accounts" for t in zoho.tasks)
