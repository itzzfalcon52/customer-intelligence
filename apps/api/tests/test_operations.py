import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import numpy as np
import pandas as pd
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlmodel import Session, select

from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.models.job import Job
from customer_intelligence.models.operations import DigestItem
from customer_intelligence.models.trace import AgentTrace
from customer_intelligence.models.workspace import WorkspaceFact
from customer_intelligence.schemas.workflow import ScoreRequest
from customer_intelligence.services import autonomy, monitoring
from customer_intelligence.services.scoring import score_dataset
from customer_intelligence.services.training import train_task


def session_for(backend) -> Session:
    session = Session(backend["app"].state.engine)
    session.info["settings"] = backend["settings"]
    return session


@pytest.fixture(scope="module")
def saas(backend) -> dict:
    """A synthetic source with a time-ordered model trained on its snapshots."""
    client = backend["client"]
    source = client.post("/api/v1/sources/synthetic").json()
    built = client.post(f"/api/v1/sources/{source['id']}/datasets", json={"horizon_days": 90})
    built = built.json()
    task = client.post(
        f"/api/v1/datasets/{built['dataset_id']}/tasks",
        json={**built["recommended_task"], "features_available_at_prediction": True},
    ).json()
    with session_for(backend) as session:
        run = train_task(session, backend["settings"], UUID(task["id"])).name
    return {"source_id": source["id"], "dataset_id": built["dataset_id"], "run_id": run}


def test_psi_is_near_zero_for_the_same_population_and_large_for_a_shift():
    rng = np.random.default_rng(0)
    reference = pd.Series(rng.normal(0, 1, 2000))
    assert monitoring.numeric_psi(reference, pd.Series(rng.normal(0, 1, 2000))) < 0.05
    shifted = monitoring.numeric_psi(reference, pd.Series(rng.normal(1.5, 1, 2000)))
    assert shifted is not None and monitoring.band(shifted) == "alert"
    plans = pd.Series(["Pro"] * 80 + ["Basic"] * 20)
    flipped = pd.Series(["Pro"] * 20 + ["Basic"] * 80)
    assert monitoring.band(monitoring.categorical_psi(plans, flipped) or 0) == "alert"
    assert monitoring.numeric_psi(reference[:5], reference[:5]) is None


def test_registry_promotes_and_rolls_back(backend, trained, saas):
    client = backend["client"]
    assert client.get("/api/v1/registry").json()["run_id"] is None
    assert client.post("/api/v1/registry/rollback").status_code == 409
    first = client.post("/api/v1/registry/promote", json={"run_id": trained["run_id"]}).json()
    assert first["run_id"] == trained["run_id"]
    client.post("/api/v1/registry/promote", json={"run_id": saas["run_id"]})
    back = client.post("/api/v1/registry/rollback").json()
    assert back["run_id"] == trained["run_id"]
    assert [h["action"] for h in back["history"][:3]] == ["rolled_back", "promoted", "promoted"]
    missing = client.post("/api/v1/registry/promote", json={"run_id": str(uuid4())})
    assert missing.status_code == 404


def test_scheduled_cycle_scores_checks_drift_and_writes_a_digest(backend, saas, execute_job):
    client = backend["client"]
    client.post("/api/v1/registry/promote", json={"run_id": saas["run_id"]})
    client.put("/api/v1/autonomy", json={"level": "recommend"})
    schedule = client.put(
        "/api/v1/schedule",
        json={"enabled": True, "source_id": saas["source_id"], "contact_count": 25},
    )
    assert schedule.status_code == 200, schedule.text
    assert schedule.json()["next_run_at"] is not None
    job = client.post("/api/v1/schedule/run").json()
    assert job["kind"] == "cycle"
    finished = execute_job(job["id"])
    assert finished["state"] == "succeeded", finished["error"]
    digest = client.get("/api/v1/digest").json()
    item = digest[0]
    assert item["kind"] == "cycle" and "Scored" in item["body"]
    assert "Review first:" in item["body"]
    hrefs = [link["href"] for link in item["links"]]
    assert f"/app/scores/{finished['result_id']}" in hrefs
    report_id = next(h for h in hrefs if h.startswith("/app/monitoring/")).rsplit("/", 1)[1]
    report = client.get(f"/api/v1/monitoring/{report_id}").json()
    reference = report["payload"]["reference"]["partition"]
    assert report["kind"] == "drift" and reference.startswith("train (latest snapshot")
    assert report["payload"]["features"] and "rule of thumb" in report["payload"]["note"]
    assert client.get("/api/v1/schedule").json()["history"][0]["score_id"] == finished["result_id"]
    assert client.post(f"/api/v1/digest/{item['id']}/read").json()["read_at"]


def test_realized_performance_uses_only_elapsed_horizons(backend, saas):
    with session_for(backend) as session:
        # Score the historical snapshots: their 90-day outcomes are already in the source.
        score_id = score_dataset(
            session,
            backend["settings"],
            ScoreRequest(
                run_id=UUID(saas["run_id"]),
                dataset_id=UUID(saas["dataset_id"]),
                contact_count=100,
                idempotency_key=uuid4(),
            ),
        )
        report = monitoring.performance_from_source(
            session, backend["settings"], score_id, UUID(saas["source_id"]), 90
        )
        payload = report.payload
        assert payload["matched_accounts"] == payload["scored_accounts"]
        assert 0 < payload["base_rate"] < 1 and payload["average_precision"] > payload["base_rate"]
        assert payload["contact_list"]["size"] == 100 and "holdout" in payload["note"]
        # The current snapshot's horizon has not elapsed, so nothing can be measured yet.
        current = backend["client"].post(
            f"/api/v1/sources/{saas['source_id']}/datasets", json={"purpose": "scoring"}
        )
        fresh = score_dataset(
            session,
            backend["settings"],
            ScoreRequest(
                run_id=UUID(saas["run_id"]),
                dataset_id=UUID(current.json()["dataset_id"]),
                contact_count=10,
                idempotency_key=uuid4(),
            ),
        )
        with pytest.raises(WorkflowError, match="known outcome"):
            monitoring.performance_from_source(
                session, backend["settings"], fresh, UUID(saas["source_id"]), 90
            )


def test_retraining_proposal_waits_for_approval(backend, saas):
    client = backend["client"]
    client.put("/api/v1/autonomy", json={"level": "act_with_approval", "daily_action_quota": 5})
    with session_for(backend) as session:
        action = autonomy.propose_retraining(
            session, backend["settings"], UUID(saas["run_id"]), UUID(saas["source_id"]), 90
        )
        assert not session.exec(select(Job).where(Job.kind == "train", Job.state == "queued")).all()
    approved = client.post(f"/api/v1/actions/{action.id}/approve")
    assert approved.status_code == 200, approved.text
    job = client.get(f"/api/v1/jobs/{approved.json()['result_id']}").json()
    assert job["kind"] == "train" and job["state"] == "queued"
    assert client.post(f"/api/v1/jobs/{job['id']}/cancel").json()["state"] == "cancelled"


def test_kill_switch_budget_and_quota_are_enforced(backend, trained):
    client = backend["client"]
    client.put("/api/v1/autonomy", json={"paused": True})
    assert client.post("/api/v1/schedule/run").status_code == 423
    with session_for(backend) as session:
        with pytest.raises(WorkflowError) as paused:
            autonomy.check_ai_allowed(session)
        assert paused.value.status_code == 423
    client.put("/api/v1/autonomy", json={"daily_token_budget": 1000, "daily_action_quota": 0})
    with session_for(backend) as session:
        session.add(AgentTrace(kind="assistant", input_tokens=900, output_tokens=200))
        session.commit()
        with pytest.raises(WorkflowError) as budget:
            autonomy.check_ai_allowed(session)
        assert budget.value.status_code == 429
    usage = client.get("/api/v1/autonomy").json()["usage"]
    assert usage["tokens_today"] >= 1100 and usage["daily_token_budget"] == 1000
    from customer_intelligence.services.workspace import propose_training

    with session_for(backend) as session, pytest.raises(WorkflowError, match="quota"):
        propose_training(session, UUID(trained["task_id"]), None)
    client.put("/api/v1/autonomy", json={})


def test_tick_queues_one_cycle_when_due(backend, saas):
    with session_for(backend) as session:
        fact = session.get(WorkspaceFact, autonomy.SCHEDULE)
        assert fact is not None
        fact.value = {
            **fact.value,
            "enabled": True,
            "next_run_at": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
        }
        session.add(fact)
        session.commit()
        assert autonomy.tick(session) is True
        assert autonomy.tick(session) is False
        queued = session.exec(select(Job).where(Job.kind == "cycle", Job.state == "queued")).all()
        assert len(queued) == 1
        queued[0].state = "cancelled"
        session.add(queued[0])
        session.commit()


def test_slack_digest_never_includes_account_ids(backend, monkeypatch):
    settings = backend["settings"]
    monkeypatch.setattr(settings, "credentials_key", SecretStr(Fernet.generate_key().decode()))
    sent: list[dict] = []

    def slack(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200)

    monkeypatch.setattr(autonomy, "transport", httpx.MockTransport(slack))
    client = backend["client"]
    bad = client.put("/api/v1/autonomy", json={"slack_webhook_url": "https://evil.test/x"})
    assert bad.status_code == 400
    hook = "https://hooks.slack.com/services/T000/B000/secret"
    saved = client.put("/api/v1/autonomy", json={"slack_webhook_url": hook})
    assert saved.json()["slack_connected"] is True and hook not in saved.text
    with session_for(backend) as session:
        item = DigestItem(
            kind="cycle",
            title="Scheduled check: monitoring alert",
            body="Scored 10 accounts.\nReview first: ACME@2026-01-31, BETA@2026-01-31.",
            links=[{"label": "Risk scores", "href": "/app/scores/x"}],
        )
        session.add(item)
        session.commit()
        session.refresh(item)
        autonomy.notify(session, settings, item)
        assert item.notified == "slack"
    assert "ACME" not in sent[0]["text"] and "Scored 10 accounts." in sent[0]["text"]
    assert (
        client.put("/api/v1/autonomy", json={"slack_webhook_url": ""}).json()["slack_connected"]
        is False
    )


def test_cycle_keeps_results_when_the_brief_cannot_be_written(backend, saas, execute_job):
    client = backend["client"]
    client.post("/api/v1/registry/promote", json={"run_id": saas["run_id"]})
    client.put("/api/v1/autonomy", json={"level": "observe", "ai_briefs": True})
    client.put("/api/v1/schedule", json={"enabled": False, "source_id": saas["source_id"]})
    job = client.post("/api/v1/schedule/run").json()
    finished = execute_job(job["id"])
    # The test provider is unreachable: scoring and drift still succeed and say so.
    assert finished["state"] == "succeeded", finished["error"]
    item = client.get("/api/v1/digest").json()[0]
    assert "Nemotron brief unavailable" in item["body"]
    latest = client.get("/api/v1/briefs/latest").json()
    assert latest["enabled"] is True and latest["brief"]["status"] == "failed"
    client.put("/api/v1/autonomy", json={})
