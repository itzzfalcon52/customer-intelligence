import csv
import io
import json
from uuid import UUID, uuid4

import httpx
import numpy as np
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlmodel import Session

from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.models.connection import Connection
from customer_intelligence.schemas.workflow import ScoreRequest
from customer_intelligence.services import connectors, monitoring
from customer_intelligence.services.scoring import read_customers, read_score, score_dataset


def session_for(backend) -> Session:
    session = Session(backend["app"].state.engine)
    session.info["settings"] = backend["settings"]
    return session


def scored(backend, trained, key: UUID, holdout: float = 0.2, contacts: int = 200) -> UUID:
    with session_for(backend) as session:
        return score_dataset(
            session,
            backend["settings"],
            ScoreRequest(
                run_id=UUID(trained["run_id"]),
                dataset_id=UUID(trained["dataset_id"]),
                contact_count=contacts,
                holdout_rate=holdout,
                idempotency_key=key,
            ),
        )


def test_holdout_is_seeded_excluded_from_exports_and_reproducible(backend, trained):
    key = uuid4()
    first, second = scored(backend, trained, key), scored(backend, trained, key)
    settings = backend["settings"]
    groups = [
        {
            c.customer_id: c.group
            for c in read_customers(read_score(s, settings.data_directory), settings.data_directory)
        }
        for s in (first, second)
    ]
    assert groups[0] == groups[1], "the same request must hold out the same accounts"
    manifest = read_score(first, settings.data_directory)
    assert manifest.holdout_count == 40 and manifest.holdout_seed is not None
    held = {i for i, g in groups[0].items() if g == "holdout"}
    assert len(held) == 40 and sum(g == "contact" for g in groups[0].values()) == 160
    export = backend["client"].get(f"/api/v1/scores/{first}/export?top_k=200").text
    rows = list(csv.DictReader(io.StringIO(export)))
    assert len(rows) == 200 and not held & {r["customer_id"] for r in rows}
    with pytest.raises(WorkflowError, match="at least 10"):
        scored(backend, trained, uuid4(), contacts=5)


def test_lift_needs_a_holdout_and_reports_an_interval(backend, trained):
    settings = backend["settings"]
    score_id = scored(backend, trained, uuid4())
    customers = read_customers(
        read_score(score_id, settings.data_directory), settings.data_directory
    )
    rng = np.random.default_rng(1)
    # Synthetic outcomes: contacted accounts churn at 10%, held-out ones at 45%.
    outcomes = {
        c.customer_id: int(rng.random() < (0.45 if c.group == "holdout" else 0.10))
        for c in customers
        if c.group
    }
    segments = {c.customer_id: "A" for c in customers}
    with session_for(backend) as session:
        report = monitoring.measure_lift(
            session, settings, score_id, outcomes, {"kind": "test"}, segments
        )
        payload = report.payload
        low, high = payload["interval_95"]
        assert payload["verdict"] == "fewer_churned" and 0 < low <= payload["reduction"] <= high
        assert payload["contacted"]["accounts"] == 160 and payload["holdout"]["accounts"] == 40
        assert (
            payload["by_segment"][0]["segment"] == "A" and "Intention-to-treat" in payload["note"]
        )
        none = scored(backend, trained, uuid4(), holdout=0)
        with pytest.raises(WorkflowError, match="no holdout"):
            monitoring.measure_lift(session, settings, none, outcomes, {"kind": "test"})
        few = {k: v for k, v in list(outcomes.items())[:15]}
        with pytest.raises(WorkflowError, match="Not enough"):
            monitoring.measure_lift(session, settings, score_id, few, {"kind": "test"})
    listed = backend["client"].get("/api/v1/monitoring?kind=lift").json()
    assert listed[0]["id"] == str(report.id)


def test_lift_from_an_outcomes_file(backend, trained):
    client = backend["client"]
    score_id = scored(backend, trained, uuid4())
    labels = {
        row["customerID"]: row["Churn"] for row in csv.DictReader(io.StringIO(trained["csv"]))
    }
    body = "customerID,renewed,segment\n" + "".join(
        f"{i},{'No' if y == 'Yes' else 'Yes'},{'A' if int(i[1:]) % 2 else 'B'}\n"
        for i, y in labels.items()
    )
    uploaded = client.post(
        "/api/v1/datasets/upload", files={"file": ("outcomes.csv", body, "text/csv")}
    ).json()
    response = client.post(
        "/api/v1/monitoring/lift",
        json={
            "score_id": str(score_id),
            "dataset_id": uploaded["id"],
            "id_column": "customerID",
            "outcome_column": "renewed",
            "positive_label": "No",
            "segment_column": "segment",
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()["payload"]
    assert payload["verdict"] in {"fewer_churned", "no_clear_difference", "more_churned"}
    assert payload["contacted"]["accounts"] + payload["holdout"]["accounts"] == 200


def test_play_writes_hubspot_tasks_only_after_approval(backend, trained, monkeypatch):
    settings = backend["settings"]
    monkeypatch.setattr(settings, "credentials_key", SecretStr(Fernet.generate_key().decode()))
    posted: list[dict] = []

    def hubspot(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            posted.append(json.loads(request.content))
            return httpx.Response(201, json={"id": "t1"})
        return httpx.Response(200, json={"results": []})

    monkeypatch.setattr(connectors, "transport", httpx.MockTransport(hubspot))
    client = backend["client"]
    client.put("/api/v1/autonomy", json={"daily_action_quota": 20})
    connection = client.post(
        "/api/v1/connections", json={"provider": "hubspot", "label": "CRM", "secret": "pat-na1-xyz"}
    ).json()
    score_id = scored(backend, trained, uuid4())
    # Make two contact-list accounts look like HubSpot company IDs.
    with session_for(backend) as session:
        listed = [
            c.customer_id
            for c in read_customers(
                read_score(score_id, settings.data_directory), settings.data_directory
            )
            if c.group == "contact"
        ]
    play = {
        "score_id": str(score_id),
        "title": "Billing check-in",
        "instructions": "Call the billing contact and confirm the card on file.",
        "accounts": 5,
        "connection_id": connection["id"],
    }
    refused = client.post("/api/v1/actions/plays", json=play)
    assert refused.status_code == 409 and "Allow" in refused.text
    assert (
        client.put(
            f"/api/v1/connections/{connection['id']}/write", json={"enabled": True}
        ).status_code
        == 400
    )
    opened = client.put(
        f"/api/v1/connections/{connection['id']}/write", json={"enabled": True, "confirm": True}
    )
    assert opened.json()["write_enabled"] is True
    action = client.post("/api/v1/actions/plays", json=play).json()
    assert action["kind"] == "play" and action["payload"]["accounts"] == listed[:5]
    assert not posted, "nothing is written before approval"
    approved = client.post(f"/api/v1/actions/{action['id']}/approve").json()
    result = approved["payload"]["result"]
    # Telco-style IDs (C0001) are not HubSpot company IDs: skipped, never guessed.
    assert result == {"destination": "hubspot", "written": 0, "skipped": 5, "failed": 0}
    with session_for(backend) as session:
        stored = session.get(Connection, UUID(connection["id"]))
        assert stored is not None
    export = client.get(f"/api/v1/actions/{action['id']}/export").text
    assert "Billing check-in" in export and listed[0] in export


def test_play_without_connection_is_a_csv_export(backend, trained):
    client = backend["client"]
    client.put("/api/v1/autonomy", json={"daily_action_quota": 20})
    score_id = scored(backend, trained, uuid4())
    action = client.post(
        "/api/v1/actions/plays",
        json={
            "score_id": str(score_id),
            "title": "Adoption review",
            "instructions": "Book a call.",
        },
    ).json()
    pending_export = client.get(f"/api/v1/actions/{action['id']}/export")
    assert pending_export.status_code == 409
    approved = client.post(f"/api/v1/actions/{action['id']}/approve").json()
    assert approved["payload"]["result"] == {"destination": "csv", "accounts": 50}
    rows = list(
        csv.DictReader(io.StringIO(client.get(f"/api/v1/actions/{action['id']}/export").text))
    )
    assert len(rows) == 50 and rows[0]["play"] == "Adoption review"


def test_approved_play_creates_a_task_per_hubspot_company(backend, monkeypatch):
    from customer_intelligence.models.workspace import PendingAction
    from customer_intelligence.services import plays

    settings = backend["settings"]
    monkeypatch.setattr(settings, "credentials_key", SecretStr(Fernet.generate_key().decode()))
    posted: list[dict] = []

    def hubspot(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/crm/v3/objects/tasks"
        posted.append(json.loads(request.content))
        return httpx.Response(201, json={"id": "t"})

    monkeypatch.setattr(connectors, "transport", httpx.MockTransport(hubspot))
    with session_for(backend) as session:
        secret = connectors._fernet(settings).encrypt(b"pat-na1-abc").decode()
        connection = Connection(
            provider="hubspot", label="CRM", secret_ciphertext=secret, write_enabled=True
        )
        session.add(connection)
        session.commit()
        action = PendingAction(
            kind="play",
            summary="x",
            payload={
                "title": "Renewal call",
                "instructions": "Confirm renewal plans.",
                "accounts": ["101@2026-09-30", "202@2026-09-30", "ACME@2026-09-30"],
                "connection_id": str(connection.id),
            },
        )
        result = plays.execute(session, settings, action)
    assert result == {"destination": "hubspot", "written": 2, "skipped": 1, "failed": 0}
    assert [p["associations"][0]["to"]["id"] for p in posted] == ["101", "202"]
    assert posted[0]["properties"]["hs_task_subject"] == "Renewal call"
