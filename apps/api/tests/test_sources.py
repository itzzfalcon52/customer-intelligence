from uuid import UUID

import pandas as pd
import pytest
from sqlmodel import Session

from customer_intelligence.ml.snapshots import (
    SnapshotError,
    build_snapshots,
    features_at,
    normalise,
)
from customer_intelligence.services.splits import prepare_split
from customer_intelligence.services.training import train_task


def tiny_tables() -> dict[str, pd.DataFrame]:
    return {
        "accounts": pd.DataFrame(
            {
                "account_id": ["A", "B"],
                "created_at": ["2025-01-01", "2025-01-01"],
                "cancelled_at": ["2025-05-10", ""],
                "billing_cycle": ["monthly", "annual"],
            }
        ),
        "invoices": pd.DataFrame(
            {
                "account_id": ["A", "A", "B"],
                "date": ["2025-03-01", "2025-04-20", "2025-02-01"],
                "amount": [100, 100, 1200],
                "status": ["paid", "failed", "paid"],
            }
        ),
        "usage": pd.DataFrame(
            {
                "account_id": ["A", "A", "B", "B"],
                "date": ["2025-03-15", "2025-04-25", "2025-03-15", "2025-04-25"],
                "active_users": [10, 2, 5, 5],
            }
        ),
        "tickets": pd.DataFrame(
            {
                "account_id": ["A", "A"],
                "created_at": ["2025-04-01", "2025-05-01"],
                "subject": ["How do I cancel?", "Invoice question"],
            }
        ),
    }


def test_features_never_use_events_after_the_cutoff():
    tables = normalise(tiny_tables())
    rows = features_at(tables, pd.Timestamp("2025-04-21"))
    a = rows.loc["A"]
    # The 2025-05-01 billing ticket and the 2025-04-25 usage are after the cutoff.
    assert a["tickets_90d"] == 1 and a["tickets_cancel_intent_90d"] == 1
    assert a["tickets_billing_90d"] == 0
    assert a["failed_payments_90d"] == 1
    # The only usage on or before the cutoff (2025-03-15) is outside the 30-day window.
    assert pd.isna(a["active_users_30d"]) and a["days_since_active"] == 37
    # Annual invoices are normalised to monthly recurring revenue.
    assert rows.loc["B", "mrr"] == 100


def test_labels_only_for_fully_observed_horizons():
    tables = tiny_tables()
    result = build_snapshots(
        tables,
        horizon_days=40,
        cutoffs=[
            pd.Timestamp("2025-03-31"),
            pd.Timestamp("2025-04-30"),
            pd.Timestamp("2025-05-31"),
        ],
    )
    frame = result.frame
    # Data ends 2025-05-10, so only the March cutoff has a full 40-day window, in which A
    # cancels.
    assert result.dropped_unobserved == 2
    assert set(frame["snapshot_date"]) == {"2025-03-31"}
    assert frame.set_index("account_id")["churned_within_40d"].to_dict() == {"A": "Yes", "B": "No"}
    with pytest.raises(SnapshotError):
        normalise({"accounts": pd.DataFrame({"account_id": ["A"]})})


def test_synthetic_source_to_time_ordered_model(backend):
    client = backend["client"]
    source = client.post("/api/v1/sources/synthetic").json()
    assert source["kind"] == "synthetic" and source["counts"]["accounts"] == 900
    built = client.post(
        f"/api/v1/sources/{source['id']}/datasets", json={"horizon_days": 90}
    ).json()
    assert built["snapshot_dates"] >= 6 and 0 < built["positive_rate"] < 0.5
    recommended = built["recommended_task"]
    task = client.post(
        f"/api/v1/datasets/{built['dataset_id']}/tasks",
        json={**recommended, "features_available_at_prediction": True},
    )
    assert task.status_code == 201, task.text
    task = task.json()
    assert task["time_column"] == "snapshot_date" and task["evaluation_strategy"] == "time_ordered"
    dataset = client.get(f"/api/v1/datasets/{built['dataset_id']}").json()
    assert dataset["original_filename"].startswith("DEMO-")
    with Session(backend["app"].state.engine) as session:
        from customer_intelligence.models.dataset import Dataset
        from customer_intelligence.models.task import Task

        db_task = session.get(Task, UUID(task["id"]))
        db_dataset = session.get(Dataset, UUID(built["dataset_id"]))
        summary = prepare_split(db_task, db_dataset, backend["settings"])
        assert summary.strategy == "time_ordered"
        split = (backend["settings"].data_directory / "splits" / f"{task['id']}.json").read_text()
        import json

        rows = json.loads(split)["row_assignments"]
        frame = pd.read_csv(backend["settings"].data_directory / "uploads" / db_dataset.storage_key)
        dates = {k: pd.to_datetime(frame.iloc[v]["snapshot_date"]) for k, v in rows.items()}
        assert dates["train"].max() < dates["validation"].min()
        assert dates["validation"].max() < dates["test"].min()
        path = train_task(session, backend["settings"], UUID(task["id"]))
    run = client.get(f"/api/v1/runs/{path.name}").json()
    assert run["report"]["task_id"] == task["id"]
    current = client.post(
        f"/api/v1/sources/{source['id']}/datasets", json={"purpose": "scoring"}
    ).json()
    assert current["recommended_task"] is None and current["rows"] > 100
    account = frame["account_id"].iloc[0]
    timeline = client.get(f"/api/v1/sources/{source['id']}/accounts/{account}").json()
    assert timeline["account_id"] == account and timeline["usage"]


def test_bundle_upload_validates_tables(backend):
    client = backend["client"]
    bad = client.post(
        "/api/v1/sources/upload",
        data={"name": "Broken"},
        files={"accounts": ("accounts.csv", "account_id,plan\nA,Pro\n", "text/csv")},
    )
    assert bad.status_code == 400 and "created_at" in bad.text
    orphan = client.post(
        "/api/v1/sources/upload",
        data={"name": "Orphans"},
        files={
            "accounts": ("accounts.csv", "account_id,created_at\nA,2025-01-01\n", "text/csv"),
            "tickets": ("tickets.csv", "account_id,created_at\nZ,2025-02-01\n", "text/csv"),
        },
    )
    assert orphan.status_code == 400 and "not in accounts" in orphan.text


def test_current_snapshot_stops_where_activity_data_is_complete():
    from customer_intelligence.ml.snapshots import current_snapshot

    tables = tiny_tables()
    # An invoice dated after the last usage row must not move the scoring cutoff past usage.
    tables["invoices"] = pd.concat(
        [
            tables["invoices"],
            pd.DataFrame(
                {"account_id": ["B"], "date": ["2025-06-30"], "amount": [1200], "status": ["paid"]}
            ),
        ]
    )
    rows = current_snapshot(tables)
    assert set(rows["snapshot_date"]) == {"2025-04-25"}
    assert rows.set_index("account_id").loc["B", "days_since_active"] == 0
