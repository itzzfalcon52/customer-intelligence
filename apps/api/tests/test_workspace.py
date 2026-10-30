from uuid import UUID, uuid4

from sqlmodel import Session, select

from customer_intelligence.agent.workflow import CATALOG_SCOPE, MEMORY_SCOPE, chat
from customer_intelligence.models.job import Job
from customer_intelligence.schemas.workflow import AssistantRequest
from tests.test_agent import provider, tools


def test_memory_round_trip_and_validation(backend):
    client = backend["client"]
    empty = client.get("/api/v1/memory").json()
    assert empty["assumptions"] == {} and empty["decisions"] == []
    saved = client.put(
        "/api/v1/memory",
        json={
            "assumptions": {"contact_cost": 12, "assumed_save_rate": 0.15, "currency": "USD"},
            "decisions": [{"text": "Only contact annual-plan accounts this quarter."}],
        },
    ).json()
    assert saved["assumptions"] == {
        "contact_cost": 12,
        "assumed_save_rate": 0.15,
        "currency": "USD",
    }
    assert saved["assumptions_source"] == "user" and len(saved["decisions"]) == 1
    bad = client.put("/api/v1/memory", json={"assumptions": {"assumed_save_rate": 2}})
    assert bad.status_code == 422
    unknown = client.put("/api/v1/memory", json={"assumptions": {"guess": 1}})
    assert unknown.status_code == 422


def test_budget_planner_remembers_assumptions(backend, trained):
    client = backend["client"]
    response = client.post(
        "/api/v1/retention/roi",
        json={
            "run_id": trained["run_id"],
            "budget": 5000,
            "contact_cost": 10,
            "offer_cost": 40,
            "assumed_save_rate": 0.2,
            "retained_value": 900,
            "currency": "EUR",
            "population_size": 400,
        },
    )
    assert response.status_code == 200, response.text
    memory = client.get("/api/v1/memory").json()
    assert memory["assumptions_source"] == "budget_planner"
    assert memory["assumptions"]["retained_value"] == 900
    assert memory["assumptions"]["currency"] == "EUR"


def test_assistant_requests_approval_instead_of_training(backend, trained):
    client_api = backend["client"]
    request = AssistantRequest(
        dataset_id=trained["dataset_id"],
        task_id=trained["task_id"],
        question="Retrain this model please.",
        workspace_tools=True,
        idempotency_key=uuid4(),
    )
    client, captured = provider(
        [
            tools(
                ("inspect_dataset", {"resource_id": trained["dataset_id"]}),
                ("read_task", {"resource_id": trained["task_id"]}),
                ("read_workspace_memory", {"resource_id": str(MEMORY_SCOPE)}),
                ("request_training_approval", {"resource_id": trained["task_id"]}),
            ),
            {"role": "assistant", "content": "I asked for your approval in the Inbox."},
        ]
    )
    with client, Session(backend["app"].state.engine) as session:
        session.info["settings"] = backend["settings"]
        result = chat(request, session, backend["settings"], client)
        queued = session.exec(select(Job).where(Job.kind == "train", Job.state == "queued")).all()
    offered = {t["function"]["name"] for t in captured[0]["tools"]}
    assert {
        "read_workspace_memory",
        "list_workspace_resources",
        "request_training_approval",
    } <= offered
    assert "submit_training" not in offered
    assert not queued, "approval must not queue work"
    action_id = result.events[-1].resource_id
    pending = client_api.get("/api/v1/actions?status=pending").json()
    assert [a["id"] for a in pending] == [action_id]
    approved = client_api.post(f"/api/v1/actions/{action_id}/approve").json()
    assert approved["status"] == "approved" and approved["result_id"]
    job = client_api.get(f"/api/v1/jobs/{approved['result_id']}").json()
    assert job["kind"] == "train" and job["state"] == "queued"
    again = client_api.post(f"/api/v1/actions/{action_id}/approve")
    assert again.status_code == 409
    assert client_api.post(f"/api/v1/jobs/{job['id']}/cancel").json()["state"] == "cancelled"


def test_workspace_tools_are_off_by_default_and_scoped(backend, trained):
    request = AssistantRequest(
        dataset_id=trained["dataset_id"],
        question="What do I have?",
        workspace_tools=True,
        idempotency_key=uuid4(),
    )
    client, captured = provider(
        [
            tools(
                ("inspect_dataset", {"resource_id": trained["dataset_id"]}),
                ("list_workspace_resources", {"resource_id": str(CATALOG_SCOPE)}),
            ),
            {"role": "assistant", "content": "You have one dataset and one training run."},
        ]
    )
    with client, Session(backend["app"].state.engine) as session:
        session.info["settings"] = backend["settings"]
        result = chat(request, session, backend["settings"], client)
    catalog = next(
        m for m in captured[1]["messages"] if m["role"] == "tool" and "runs" in m["content"]
    )
    assert trained["run_id"] in catalog["content"]
    assert [e.tool for e in result.events] == ["inspect_dataset", "list_workspace_resources"]
    plain = AssistantRequest(
        dataset_id=trained["dataset_id"], question="Hi", idempotency_key=uuid4()
    )
    client, captured = provider([{"role": "assistant", "content": "x"}])
    with client, Session(backend["app"].state.engine) as session:
        session.info["settings"] = backend["settings"]
        try:
            chat(plain, session, backend["settings"], client)
        except Exception:
            pass
    names = {t["function"]["name"] for t in captured[0]["tools"]}
    assert names == {"inspect_dataset"}
    assert UUID(str(MEMORY_SCOPE)).int == 1
