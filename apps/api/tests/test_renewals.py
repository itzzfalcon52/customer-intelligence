"""Renewal radar over a labelled synthetic source, plus each billing connector's renewal fields."""

import csv
import io
from uuid import UUID, uuid4

import httpx
import pandas as pd
import pytest
from sqlmodel import Session

from customer_intelligence.schemas.workflow import ScoreRequest
from customer_intelligence.services import connectors, razorpay, renewals, sources, zoho
from customer_intelligence.services.scoring import score_dataset
from customer_intelligence.services.training import train_task


def session_for(backend) -> Session:
    session = Session(backend["app"].state.engine)
    session.info["settings"] = backend["settings"]
    return session


@pytest.fixture(scope="module")
def scored(backend) -> dict:
    """A synthetic source, a model trained on its snapshots, and its current accounts scored."""
    client = backend["client"]
    source = client.post("/api/v1/sources/synthetic").json()
    built = client.post(
        f"/api/v1/sources/{source['id']}/datasets", json={"horizon_days": 90}
    ).json()
    task = client.post(
        f"/api/v1/datasets/{built['dataset_id']}/tasks",
        json={**built["recommended_task"], "features_available_at_prediction": True},
    ).json()
    current = client.post(
        f"/api/v1/sources/{source['id']}/datasets",
        json={"horizon_days": 90, "purpose": "scoring"},
    ).json()
    with session_for(backend) as session:
        run = train_task(session, backend["settings"], UUID(task["id"])).name
        score_id = score_dataset(
            session,
            backend["settings"],
            ScoreRequest(
                run_id=UUID(run),
                dataset_id=UUID(current["dataset_id"]),
                contact_count=50,
                idempotency_key=str(uuid4()),
            ),
        )
    return {
        "source_id": source["id"],
        "score_id": str(score_id),
        "run_id": run,
        "features": built["recommended_task"]["feature_columns"],
    }


def test_renewal_columns_are_never_model_features(scored):
    assert "renews_at" not in scored["features"]
    assert "cancel_scheduled" not in scored["features"]


def test_radar_windows_ordering_and_values(backend, scored):
    client = backend["client"]
    month = client.get("/api/v1/renewals", params={"days": 30}).json()
    quarter = client.get("/api/v1/renewals", params={"days": 90}).json()
    assert month["available"] and month["score_id"] == scored["score_id"]
    assert month["source_id"] == scored["source_id"]
    assert {i["account_id"] for i in month["items"]} <= {i["account_id"] for i in quarter["items"]}
    assert len(quarter["items"]) > len(month["items"]) > 0
    assert all(i["days_left"] <= 30 for i in month["items"])

    items = quarter["items"]
    scheduled = [i["cancel_scheduled"] for i in items]
    assert scheduled == sorted(scheduled, reverse=True), "already-set-to-cancel comes first"
    unscheduled = [i["rank"] for i in items if not i["cancel_scheduled"]]
    assert unscheduled == sorted(unscheduled), "then by risk rank"

    by_date = client.get("/api/v1/renewals", params={"days": 90, "sort": "date"}).json()
    assert [i["days_left"] for i in by_date["items"]] == sorted(
        i["days_left"] for i in by_date["items"]
    )

    # The value is the account's last paid invoice, never risk × value.
    tables = sources.load_tables(backend["settings"], UUID(scored["source_id"]))
    invoices = tables["invoices"]
    sample = next(i for i in items if i["amount"] is not None)
    paid = invoices[
        (invoices["account_id"] == sample["account_id"]) & (invoices["status"] == "paid")
    ]
    assert sample["amount"] == pytest.approx(float(paid.sort_values("date")["amount"].iloc[-1]))
    totals = quarter["totals"]
    assert totals["renewing"] == sum(1 for i in items if not i["overdue"])
    assert totals["overdue"] == 0, "synthetic renewals fall after the data's last day"
    assert "expected" not in str(quarter).lower()


def test_radar_csv_is_spreadsheet_safe_and_has_no_holdout(backend, scored):
    response = backend["client"].get("/api/v1/renewals/export.csv", params={"days": 90})
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(response.text)))
    assert rows[0][:3] == ["account_id", "renews_at", "days_left"]
    assert "holdout" not in ",".join(rows[0]) and len(rows) > 1


def test_radar_says_how_to_get_renewal_dates(backend, monkeypatch):
    monkeypatch.setattr(renewals.sources, "list_sources", lambda settings: [])
    with session_for(backend) as session:
        result = renewals.radar(session, backend["settings"], 30, "risk", uuid4())
    assert result["available"] is False and "Connect a billing system" in result["message"]


def test_daily_digest_mentions_renewals_without_ids(backend, scored, execute_job):
    client = backend["client"]
    client.post("/api/v1/registry/promote", json={"run_id": scored["run_id"]})
    saved = client.put(
        "/api/v1/schedule",
        json={"enabled": True, "source_id": scored["source_id"], "contact_count": 25},
    )
    assert saved.status_code == 200, saved.text
    finished = execute_job(client.post("/api/v1/schedule/run").json()["id"])
    assert finished["state"] == "succeeded", finished["error"]
    item = client.get("/api/v1/digest").json()[0]
    line = next(x for x in item["body"].splitlines() if x.startswith("Renewals in the next 30"))
    assert "ACME-" not in line
    assert any(link["href"] == "/app/renewals" for link in item["links"])


def test_stripe_reads_period_end_in_both_shapes_and_scheduled_cancels():
    def api(request: httpx.Request) -> httpx.Response:
        data = {
            "/v1/customers": [
                {"id": "c1", "created": 1_700_000_000},
                {"id": "c2", "created": 1_700_000_000},
            ],  # noqa: E501
            "/v1/subscriptions": [
                {
                    "customer": "c1",
                    "status": "active",
                    "created": 1,
                    "current_period_end": 1_790_000_000,
                    "cancel_at_period_end": True,
                },  # noqa: E501
                {
                    "customer": "c2",
                    "status": "active",
                    "created": 1,
                    "items": {"data": [{"current_period_end": 1_791_000_000}]},
                },  # noqa: E501
            ],
            "/v1/invoices": [],
        }[request.url.path]
        return httpx.Response(200, json={"data": data, "has_more": False})

    with httpx.Client(base_url="https://x", transport=httpx.MockTransport(api)) as client:
        accounts = connectors.stripe_tables(client)["accounts"].set_index("account_id")
    assert accounts.loc["c1", "renews_at"] == "2026-09-21"
    assert accounts.loc["c1", "cancel_scheduled"] == "yes"
    assert accounts.loc["c2", "renews_at"] == "2026-10-03"
    assert accounts.loc["c2", "cancel_scheduled"] == ""


def test_razorpay_and_zoho_billing_renewals():
    rp = razorpay.build(
        customers=[{"id": "c1", "created_at": 1_700_000_000}, {"id": "c2", "created_at": 1}],
        subscriptions=[
            {
                "customer_id": "c1",
                "status": "active",
                "created_at": 1,
                "current_end": 1_790_000_000,
            },  # noqa: E501
            {
                "customer_id": "c2",
                "status": "cancelled",
                "created_at": 1,
                "ended_at": 1_750_000_000,
            },  # noqa: E501
        ],
        plans={},
        invoices=[],
    )["accounts"].set_index("account_id")
    assert rp.loc["c1", "renews_at"] == "2026-09-21" and rp.loc["c2", "renews_at"] == ""

    zb = zoho.build_billing(
        customers=[{"customer_id": "1"}, {"customer_id": "2"}],
        subscriptions=[
            {"customer_id": "1", "status": "non_renewing", "current_term_ends_at": "2026-11-15"},
            {"customer_id": "2", "status": "live", "next_billing_at": "2026-12-01"},
        ],
        invoices=[],
    )["accounts"].set_index("account_id")
    assert zb.loc["1", "renews_at"] == "2026-11-15" and zb.loc["1", "cancel_scheduled"] == "yes"
    assert zb.loc["2", "renews_at"] == "2026-12-01" and zb.loc["2", "cancel_scheduled"] == ""


def test_synthetic_renewals_only_for_active_accounts():
    accounts = sources.synthetic_tables(accounts=120)["accounts"]
    active = accounts["cancelled_at"] == ""
    assert (accounts.loc[active, "renews_at"] != "").all()
    assert (accounts.loc[~active, "renews_at"] == "").all()
    assert pd.to_datetime(accounts.loc[active, "renews_at"]).min() > pd.Timestamp("2026-09-30")
