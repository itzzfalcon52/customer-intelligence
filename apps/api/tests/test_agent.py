import json
from uuid import uuid4

import httpx
import pytest
from openai import OpenAI
from sqlmodel import Session, select

from customer_intelligence.agent.workflow import chat
from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.models.conversation import AssistantLease
from customer_intelligence.models.job import Job
from customer_intelligence.schemas.workflow import AssistantRequest


def provider(messages: list[dict]):
    requests = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        message = messages[len(requests) - 1]
        return httpx.Response(
            200,
            json={
                "id": f"response-{len(requests)}",
                "object": "chat.completion",
                "created": 1,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "tool_calls" if message.get("tool_calls") else "stop",
                        "message": message,
                    }
                ],
            },
        )

    return OpenAI(
        api_key="test-key",
        base_url="https://example.invalid/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(handle)),
    ), requests


def tools(*calls) -> dict:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": f"call-{number}",
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(arguments),
                },
            }
            for number, (name, arguments) in enumerate(calls)
        ],
    }


def test_agent_real_evidence_history_and_replay(backend, trained):
    request = AssistantRequest(
        dataset_id=trained["dataset_id"],
        task_id=trained["task_id"],
        question="Explain the dataset and confirmed task.",
        idempotency_key=uuid4(),
    )
    client, captured = provider(
        [
            tools(
                ("inspect_dataset", {"resource_id": trained["dataset_id"]}),
                ("read_task", {"resource_id": trained["task_id"]}),
            ),
            {
                "role": "assistant",
                "content": "The profile contains 480 rows; the saved target is Churn.",
            },
        ]
    )
    with client, Session(backend["app"].state.engine) as session:
        result = chat(request, session, backend["settings"], client)
        replay = chat(request, session, backend["settings"], client)
        assert result == replay and len(captured) == 2
        assert [event.tool for event in result.events] == ["inspect_dataset", "read_task"]
        payloads = [
            json.loads(m["content"]) for m in captured[1]["messages"] if m["role"] == "tool"
        ]
        assert payloads[0]["row_count"] == 480 and "preview" not in payloads[0]
        assert payloads[1]["feature_columns"] == [
            "tenure",
            "Contract",
            "MonthlyCharges",
            "TotalCharges",
        ]
        assert all(event.evidence_path.startswith("/api/v1/") for event in result.events)
        with pytest.raises(WorkflowError, match="another message"):
            chat(
                request.model_copy(update={"question": "Different question"}),
                session,
                backend["settings"],
                client,
            )
    history = backend["client"].get(f"/api/v1/assistant/conversations/{result.conversation_id}")
    assert history.status_code == 200 and len(history.json()["turns"]) == 1


@pytest.mark.parametrize(
    "call_name,arguments",
    [
        ("submit_training", {"resource_id": "task"}),
        ("inspect_dataset", {"resource_id": "other"}),
        ("inspect_dataset", {"resource_id": "dataset", "shell": "bad"}),
    ],
)
def test_agent_rejects_unauthorized_tools_and_arguments(backend, trained, call_name, arguments):
    arguments = {
        key: trained["dataset_id"]
        if value == "dataset"
        else trained["task_id"]
        if value == "task"
        else str(uuid4())
        if value == "other"
        else value
        for key, value in arguments.items()
    }
    client, _ = provider([tools((call_name, arguments))])
    request = AssistantRequest(
        dataset_id=trained["dataset_id"], question="Inspect.", idempotency_key=uuid4()
    )
    with client, Session(backend["app"].state.engine) as session:
        before = len(session.exec(select(Job)).all())
        with pytest.raises(WorkflowError):
            chat(request, session, backend["settings"], client)
        assert len(session.exec(select(Job)).all()) == before
        assert session.get(AssistantLease, str(request.idempotency_key)) is None


def test_agent_requires_evidence_and_rejects_duplicate_batch(backend, trained):
    for messages in [
        [{"role": "assistant", "content": "I trained a model without tools."}],
        [
            tools(
                ("inspect_dataset", {"resource_id": trained["dataset_id"]}),
                ("inspect_dataset", {"resource_id": trained["dataset_id"]}),
            )
        ],
    ]:
        client, _ = provider(messages)
        with client, Session(backend["app"].state.engine) as session:
            with pytest.raises(WorkflowError):
                chat(
                    AssistantRequest(
                        dataset_id=trained["dataset_id"],
                        question="Inspect.",
                        idempotency_key=uuid4(),
                    ),
                    session,
                    backend["settings"],
                    client,
                )


def test_explicit_agent_training_and_idempotent_submission(backend, trained):
    # Use a new confirmed task because the workflow tests may have frozen the original.
    client_api = backend["client"]
    task = client_api.get(f"/api/v1/tasks/{trained['task_id']}").json()
    new_task = client_api.post(
        f"/api/v1/datasets/{trained['dataset_id']}/tasks",
        json={
            key: task[key]
            for key in (
                "target_column",
                "positive_label",
                "id_column",
                "feature_columns",
                "features_available_at_prediction",
            )
        },
    ).json()["id"]
    request = AssistantRequest(
        dataset_id=trained["dataset_id"],
        task_id=new_task,
        question="Train the confirmed plan.",
        allow_training=True,
        idempotency_key=uuid4(),
    )
    client, captured = provider(
        [
            tools(
                ("inspect_dataset", {"resource_id": trained["dataset_id"]}),
                ("read_task", {"resource_id": new_task}),
                ("propose_training", {"resource_id": new_task}),
                ("submit_training", {"resource_id": new_task}),
            ),
            {"role": "assistant", "content": "The training job is queued, not yet completed."},
        ]
    )
    with client, Session(backend["app"].state.engine) as session:
        session.info["settings"] = backend["settings"]
        result = chat(request, session, backend["settings"], client)
        jobs = session.exec(select(Job).where(Job.kind == "train", Job.state == "queued")).all()
        assert len(jobs) == 1 and len(captured) == 2
        assert result.events[-1].resource_id == str(jobs[0].id)
        assert chat(request, session, backend["settings"], client) == result
        job_id = jobs[0].id
    assert client_api.post(f"/api/v1/jobs/{job_id}/cancel").json()["state"] == "cancelled"


def test_scope_validation_happens_before_provider_call(backend, trained):
    client, captured = provider([])
    request = AssistantRequest(
        dataset_id=trained["dataset_id"],
        task_id=uuid4(),
        question="Inspect.",
        idempotency_key=uuid4(),
    )
    with client, Session(backend["app"].state.engine) as session:
        with pytest.raises(WorkflowError):
            chat(request, session, backend["settings"], client)
    assert not captured


def test_api_agent_uses_configured_provider_adapter(backend, trained, monkeypatch):
    client, _ = provider(
        [
            tools(("inspect_dataset", {"resource_id": trained["dataset_id"]})),
            {"role": "assistant", "content": "480 rows are recorded."},
        ]
    )
    monkeypatch.setattr("customer_intelligence.agent.workflow.OpenAI", lambda **kwargs: client)
    result = backend["client"].post(
        "/api/v1/assistant/messages",
        json={
            "dataset_id": trained["dataset_id"],
            "question": "Inspect this dataset.",
            "idempotency_key": str(uuid4()),
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["events"][0]["tool"] == "inspect_dataset"


def test_legacy_inspection_uses_request_database(backend, trained, monkeypatch):
    client, _ = provider(
        [
            tools(
                ("inspect_dataset", {"dataset_id": trained["dataset_id"]}),
                ("read_task", {"task_id": trained["task_id"]}),
            ),
            {"role": "assistant", "content": "The supplied dataset has 480 rows."},
        ]
    )
    monkeypatch.setattr("customer_intelligence.services.assistant.OpenAI", lambda **kwargs: client)
    response = backend["client"].post(
        "/api/v1/assistant/inspect",
        json={
            "dataset_id": trained["dataset_id"],
            "task_id": trained["task_id"],
            "question": "Inspect.",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["completed_tools"] == ["inspect_dataset", "read_task"]
