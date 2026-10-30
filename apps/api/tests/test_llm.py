import json
from uuid import uuid4

import httpx
import pytest
from openai import OpenAI
from sqlmodel import Session, col, select

from customer_intelligence.agent import llm
from customer_intelligence.agent.llm import LLMGateway
from customer_intelligence.agent.tracing import traced
from customer_intelligence.agent.workflow import chat
from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.models.trace import AgentSpan, AgentTrace
from customer_intelligence.schemas.retention import SchemaReasoning
from customer_intelligence.schemas.workflow import AssistantRequest


def completion(message: dict, model: str = "test-model", usage: bool = True) -> dict:
    body = {
        "id": "r",
        "object": "chat.completion",
        "created": 1,
        "model": model,
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls" if message.get("tool_calls") else "stop",
                "message": {"role": "assistant", **message},
            }
        ],
    }
    if usage:
        body["usage"] = {"prompt_tokens": 1000, "completion_tokens": 200, "total_tokens": 1200}
    return body


def scripted(responses: list[httpx.Response]) -> tuple[OpenAI, list[dict]]:
    requests: list[dict] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return responses[len(requests) - 1]

    client = OpenAI(
        api_key="test",
        base_url="https://example.invalid/v1",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handle)),
    )
    return client, requests


def deliver(payload: dict) -> dict:
    return {
        "content": None,
        "tool_calls": [
            {
                "id": "c1",
                "type": "function",
                "function": {"name": "deliver_result", "arguments": json.dumps(payload)},
            }
        ],
    }


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(llm, "_sleep", lambda seconds: None)


def test_retries_transient_failures_then_records_usage_and_cost(backend):
    settings = backend["settings"].model_copy(
        update={"nebius_max_retries": 2, "model_prices": {"test-model": (0.5, 2.0)}}
    )
    client, requests = scripted(
        [
            httpx.Response(429, json={"error": {"message": "slow down"}}),
            httpx.Response(503, json={"error": {"message": "busy"}}),
            httpx.Response(200, json=completion({"content": "OK"})),
        ]
    )
    with Session(backend["app"].state.engine) as session:
        with traced(session, "test.retry") as tracer, LLMGateway(settings, client) as gateway:
            response = gateway.complete(
                name="ping", messages=[{"role": "user", "content": "hi"}], max_tokens=8
            )
        assert response.choices[0].message.content == "OK"
        assert len(requests) == 3
        trace = session.get(AgentTrace, tracer.id)
        assert trace is not None and trace.status == "succeeded"
        assert (trace.model_calls, trace.retries) == (1, 2)
        assert (trace.input_tokens, trace.output_tokens) == (1000, 200)
        # 1000 * 0.5 / 1e6 + 200 * 2.0 / 1e6
        assert trace.cost_usd == pytest.approx(0.0009)


def test_does_not_retry_client_errors_and_saves_failed_trace(backend):
    client, requests = scripted([httpx.Response(401, json={"error": {"message": "no"}})])
    with Session(backend["app"].state.engine) as session:
        with pytest.raises(WorkflowError) as error:
            with traced(session, "test.fail") as tracer:
                LLMGateway(backend["settings"], client).complete(
                    name="ping", messages=[{"role": "user", "content": "hi"}], max_tokens=8
                )
        assert error.value.code == "provider_credentials"
        assert len(requests) == 1
        trace = session.get(AgentTrace, tracer.id)
        assert trace is not None
        assert (trace.status, trace.error_code) == ("failed", "provider_credentials")
        span = session.exec(select(AgentSpan).where(AgentSpan.trace_id == tracer.id)).one()
        assert (span.status, span.input_tokens, span.cost_usd) == ("failed", None, None)


def test_structured_repairs_once_without_echoing_rejected_values(backend):
    client, requests = scripted(
        [
            httpx.Response(200, json=completion(deliver({"summary": "SECRET-VALUE"}))),
            httpx.Response(
                200, json=completion(deliver({"summary": "ok", "findings": [], "questions": []}))
            ),
        ]
    )
    result = LLMGateway(backend["settings"], client).structured("review", {}, SchemaReasoning)
    assert result.summary == "ok"
    feedback = requests[1]["messages"][-1]["content"]
    assert "findings" in feedback and "SECRET-VALUE" not in feedback


def test_unknown_price_keeps_cost_unknown(backend):
    client, _ = scripted([httpx.Response(200, json=completion({"content": "OK"}, usage=False))])
    with Session(backend["app"].state.engine) as session:
        with traced(session, "test.unpriced") as tracer:
            LLMGateway(backend["settings"], client).complete(
                name="ping", messages=[{"role": "user", "content": "hi"}], max_tokens=8
            )
        trace = session.get(AgentTrace, tracer.id)
        assert trace is not None
        assert (trace.input_tokens, trace.cost_usd) == (None, None)


def tool_call(name: str, arguments: dict) -> dict:
    return {
        "content": None,
        "tool_calls": [
            {
                "id": "t1",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)},
            }
        ],
    }


def test_agent_turn_is_traced_with_tool_spans_and_events(backend, trained):
    client, _ = scripted(
        [
            httpx.Response(
                200,
                json=completion(
                    tool_call("inspect_dataset", {"resource_id": trained["dataset_id"]})
                ),
            ),
            httpx.Response(200, json=completion({"content": "480 rows are recorded."})),
        ]
    )
    events: list[dict] = []
    request = AssistantRequest(
        dataset_id=trained["dataset_id"], question="Inspect.", idempotency_key=uuid4()
    )
    with Session(backend["app"].state.engine) as session:
        result = chat(request, session, backend["settings"], client, listener=events.append)
        assert result.trace_id is not None and result.model_call_count == 2
        trace = session.get(AgentTrace, result.trace_id)
        assert trace is not None
        assert (trace.kind, trace.status, trace.model_calls, trace.tool_calls) == (
            "assistant",
            "succeeded",
            2,
            1,
        )
        assert trace.turn_id == result.turn_id
        assert trace.prompt_version and trace.prompt_version.startswith("assistant@v5+")
        spans = session.exec(
            select(AgentSpan)
            .where(AgentSpan.trace_id == result.trace_id)
            .order_by(col(AgentSpan.sequence))
        ).all()
        assert [(s.kind, s.name) for s in spans] == [
            ("model", "assistant"),
            ("tool", "inspect_dataset"),
            ("model", "assistant"),
        ]
        assert spans[1].evidence_path == f"/api/v1/datasets/{trained['dataset_id']}/profile"
    assert [e["type"] for e in events] == [
        "model_start",
        "model_end",
        "tool_start",
        "tool_end",
        "model_start",
        "model_end",
    ]


def test_fast_model_routes_tools_and_primary_writes_answer(backend, trained):
    settings = backend["settings"].model_copy(update={"nebius_fast_model": "fast-model"})
    client, requests = scripted(
        [
            httpx.Response(
                200,
                json=completion(
                    tool_call("inspect_dataset", {"resource_id": trained["dataset_id"]}),
                    model="fast-model",
                ),
            ),
            httpx.Response(200, json=completion({"content": "draft"}, model="fast-model")),
            httpx.Response(200, json=completion({"content": "480 rows are recorded."})),
        ]
    )
    request = AssistantRequest(
        dataset_id=trained["dataset_id"], question="Inspect.", idempotency_key=uuid4()
    )
    with Session(backend["app"].state.engine) as session:
        result = chat(request, session, settings, client)
    assert [r["model"] for r in requests] == ["fast-model", "fast-model", "test-model"]
    assert requests[2]["tool_choice"] == "none"
    assert (result.answer, result.model, result.model_call_count) == (
        "480 rows are recorded.",
        "test-model",
        3,
    )


def test_failed_agent_turn_still_saves_trace(backend, trained):
    client, _ = scripted([httpx.Response(200, json=completion({"content": "No evidence."}))])
    request = AssistantRequest(
        dataset_id=trained["dataset_id"], question="Inspect.", idempotency_key=uuid4()
    )
    with Session(backend["app"].state.engine) as session:
        with pytest.raises(WorkflowError):
            chat(request, session, backend["settings"], client)
        trace = session.exec(
            select(AgentTrace)
            .where(AgentTrace.kind == "assistant", AgentTrace.status == "failed")
            .order_by(col(AgentTrace.created_at).desc())
        ).first()
        assert trace is not None and trace.model_calls == 1


def read_events(response: httpx.Response) -> list[tuple[str, dict]]:
    events = []
    for block in response.read().decode().split("\n\n"):
        lines = [line for line in block.splitlines() if not line.startswith(":")]
        if lines:
            name = lines[0].removeprefix("event: ")
            events.append((name, json.loads(lines[1].removeprefix("data: "))))
    return events


def test_stream_emits_steps_then_answer_and_trace_is_readable(backend, trained, monkeypatch):
    client, _ = scripted(
        [
            httpx.Response(
                200,
                json=completion(
                    tool_call("inspect_dataset", {"resource_id": trained["dataset_id"]})
                ),
            ),
            httpx.Response(200, json=completion({"content": "480 rows are recorded."})),
        ]
    )
    monkeypatch.setattr(
        "customer_intelligence.agent.provider.provider_client", lambda settings: client
    )
    with backend["client"].stream(
        "POST",
        "/api/v1/assistant/messages/stream",
        json={
            "dataset_id": trained["dataset_id"],
            "question": "Inspect this dataset.",
            "idempotency_key": str(uuid4()),
        },
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = read_events(response)
    names = [name for name, _ in events]
    assert names == [
        "model_start",
        "model_end",
        "tool_start",
        "tool_end",
        "model_start",
        "model_end",
        "answer",
    ]
    answer = events[-1][1]["response"]
    assert answer["answer"] == "480 rows are recorded."
    detail = backend["client"].get(f"/api/v1/assistant/traces/{answer['trace_id']}").json()
    assert detail["trace"]["status"] == "succeeded"
    assert [span["name"] for span in detail["spans"]] == [
        "assistant",
        "inspect_dataset",
        "assistant",
    ]
    listed = backend["client"].get("/api/v1/assistant/traces?kind=assistant").json()
    assert answer["trace_id"] in [item["id"] for item in listed]


def test_stream_reports_workflow_errors_as_events(backend):
    with backend["client"].stream(
        "POST",
        "/api/v1/assistant/messages/stream",
        json={"dataset_id": str(uuid4()), "question": "Hi", "idempotency_key": str(uuid4())},
    ) as response:
        events = read_events(response)
    assert events == [
        (
            "error",
            {
                "type": "error",
                "code": "invalid_workflow",
                "message": "Dataset not found.",
                "status": 404,
            },
        )
    ]
    assert backend["client"].get(f"/api/v1/assistant/traces/{uuid4()}").status_code == 404


def test_idempotent_replay_does_not_add_empty_traces(backend, trained):
    client, _ = scripted(
        [
            httpx.Response(
                200,
                json=completion(
                    tool_call("inspect_dataset", {"resource_id": trained["dataset_id"]})
                ),
            ),
            httpx.Response(200, json=completion({"content": "480 rows are recorded."})),
        ]
    )
    request = AssistantRequest(
        dataset_id=trained["dataset_id"], question="Inspect.", idempotency_key=uuid4()
    )
    with Session(backend["app"].state.engine) as session:
        first = chat(request, session, backend["settings"], client)
        before = len(session.exec(select(AgentTrace)).all())
        replay = chat(request, session, backend["settings"], client)
        assert replay.trace_id == first.trace_id
        assert len(session.exec(select(AgentTrace)).all()) == before


def grounding_turn(backend, trained, answers: list[str]):
    client, requests = scripted(
        [
            httpx.Response(
                200,
                json=completion(
                    tool_call("inspect_dataset", {"resource_id": trained["dataset_id"]})
                ),
            ),
            *[httpx.Response(200, json=completion({"content": text})) for text in answers],
        ]
    )
    request = AssistantRequest(
        dataset_id=trained["dataset_id"], question="How many rows?", idempotency_key=uuid4()
    )
    with Session(backend["app"].state.engine) as session:
        return chat(request, session, backend["settings"], client), requests


def test_fabricated_number_triggers_one_grounding_revision(backend, trained):
    result, requests = grounding_turn(
        backend, trained, ["480 rows; contacting them saves 42,000 USD.", "480 rows are recorded."]
    )
    assert result.answer == "480 rows are recorded."
    assert result.verification == {
        "grounded": True,
        "numbers_checked": 1,
        "ungrounded": [],
        "causal_claims": [],
        "revised": True,
    }
    assert "42,000" in requests[2]["messages"][-1]["content"]
    assert requests[2]["tool_choice"] == "none"


def test_unfixed_number_is_flagged_not_silently_edited(backend, trained):
    result, _ = grounding_turn(
        backend, trained, ["480 rows and 12.5% uplift.", "480 rows and a 12.5% uplift."]
    )
    assert result.answer == "480 rows and 12.5% uplift."
    assert result.verification["grounded"] is False
    assert result.verification["ungrounded"] == ["12.5%"]


def test_causal_wording_triggers_revision(backend, trained):
    result, requests = grounding_turn(
        backend,
        trained,
        ["Short tenure causes churn in 480 rows.", "Short tenure is associated with churn."],
    )
    assert result.answer == "Short tenure is associated with churn."
    assert result.verification["grounded"] and result.verification["revised"]
    assert "causal wording" in requests[2]["messages"][-1]["content"]
