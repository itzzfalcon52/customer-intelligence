import json
from uuid import UUID, uuid4

import httpx
import numpy as np
import pandas as pd
import pytest
from openai import OpenAI
from sqlmodel import Session

from customer_intelligence.agent.verification import causal_claims, finalize, verify_report
from customer_intelligence.ml import investigation as analyses
from customer_intelligence.schemas.investigation import (
    Check,
    InvestigationReport,
    InvestigationRequest,
)
from customer_intelligence.schemas.retention import RuleCondition
from customer_intelligence.services.investigation import run_investigation

EVIDENCE = {
    "E1": {"tool": "overview", "result": {"churn_rate": 0.4608, "rows": 1200}},
    "E2": {"tool": "segment_rates", "result": {"segments": [{"churn_rate": 0.569}]}},
    "E3": {"tool": "segment_rates", "error": "not approved"},
}


def report(
    *findings: tuple[str, list[str]], headline: str = "Monthly billing stands out."
) -> InvestigationReport:
    return InvestigationReport(
        headline=headline,
        findings=[
            {"statement": statement, "kind": "association", "evidence": ids}
            for statement, ids in findings
        ],
        next_steps=["Compare monthly accounts by tenure next."],
    )


def test_verifier_accepts_grounded_associative_findings():
    result = verify_report(
        report(("Monthly accounts churned at 56.9% versus 46.1% overall.", ["E1", "E2"])),
        EVIDENCE,
    )
    assert result["passed"], result


def test_verifier_rejects_ungrounded_causal_and_badly_cited_findings():
    draft = report(
        ("Monthly billing causes churn.", ["E2"]),
        ("Churn would fall to 12.5% with annual plans.", ["E2"]),
        ("Seats are irrelevant.", ["E3", "E9"]),
        ("Overall churn is 46.1%.", ["E1"]),
    )
    result = verify_report(draft, EVIDENCE)
    assert not result["passed"]
    assert [f["supported"] for f in result["findings"]] == [False, False, False, True]
    assert "causal" in result["findings"][0]["problems"][0]
    assert "12.5%" in result["findings"][1]["problems"][0]
    assert any("E9" in p for p in result["findings"][2]["problems"])
    final = finalize(draft, result)
    assert final["status"] == "partial"
    assert [f["statement"] for f in final["findings"]] == ["Overall churn is 46.1%."]
    assert len(final["withheld"]) == 3


def test_negated_causal_wording_is_allowed():
    assert causal_claims("This does not show that billing causes churn.") == []
    assert causal_claims("Billing drives churn. It is not proven.") == ["drives"]


def test_analyses_reject_unsafe_or_invalid_requests():
    frame = pd.DataFrame({"plan": ["a", "b"] * 20, "seats": range(40)})
    labels = np.array([0, 1] * 20)
    with pytest.raises(analyses.AnalysisError, match="text"):
        analyses.condition_mask(frame, [RuleCondition(column="plan", operator="gt", value="a")])
    with pytest.raises(analyses.AnalysisError, match="overlap"):
        analyses.compare_cohorts(
            frame,
            labels,
            [RuleCondition(column="seats", operator="gt", value="5")],
            [RuleCondition(column="seats", operator="gt", value="10")],
        )
    with pytest.raises(ValueError, match="column"):
        Check(hypothesis="x", tool="segment_rates")


def scripted(payloads: list[dict]) -> tuple[OpenAI, list[dict]]:
    requests: list[dict] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        payload = payloads[len(requests) - 1]
        if payload.get("choices_override"):  # a degenerate, truncated completion
            return httpx.Response(
                200,
                json={
                    "id": "r",
                    "object": "chat.completion",
                    "created": 1,
                    "model": "test-model",
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "length",
                            "message": {"role": "assistant", "content": "<tool_call>" + " " * 50},
                        }
                    ],
                },
            )
        return httpx.Response(
            200,
            json={
                "id": "r",
                "object": "chat.completion",
                "created": 1,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "c",
                                    "type": "function",
                                    "function": {
                                        "name": "deliver_result",
                                        "arguments": json.dumps(payload),
                                    },
                                }
                            ],
                        },
                    }
                ],
            },
        )

    client = OpenAI(
        api_key="test",
        base_url="https://example.invalid/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(handle)),
    )
    return client, requests


PLAN = {
    "restated_question": "Which segments churn most?",
    "checks": [
        {"hypothesis": "Short tenure churns more", "tool": "segment_rates", "column": "tenure"},
        {
            "hypothesis": "Monthly contracts churn more",
            "tool": "compare_cohorts",
            "cohort_label": "Monthly",
            "cohort_a": [{"column": "Contract", "operator": "eq", "value": "Monthly"}],
        },
        {"hypothesis": "IDs matter", "tool": "segment_rates", "column": "customerID"},
    ],
}
FOLLOW_UP = {"done": True, "rationale": "Enough evidence.", "checks": []}
DRAFT = {
    "headline": "Short tenure causes churn.",
    "findings": [
        {"statement": "Tenure drives churn by 99.9%.", "kind": "association", "evidence": ["E4"]},
    ],
}
REVISED = {
    "headline": "Short tenure and monthly contracts are associated with higher churn.",
    "findings": [
        {
            "statement": "Accounts with short tenure show higher churn rates in development rows.",
            "kind": "association",
            "evidence": ["E4"],
        },
        {
            "statement": "Monthly contracts churn more often than other contracts.",
            "kind": "association",
            "evidence": ["E5"],
        },
    ],
    "caveats": ["Associations only."],
}


def test_investigation_plans_runs_verifies_revises_and_saves(backend, trained):
    client, requests = scripted([PLAN, FOLLOW_UP, DRAFT, REVISED])
    request = InvestigationRequest(
        run_id=trained["run_id"],
        question="Which segments churn most?",
        provider_consent=True,
        idempotency_key=uuid4(),
    )
    events: list[dict] = []
    with Session(backend["app"].state.engine) as session:
        result = run_investigation(
            request, session, backend["settings"], client, listener=events.append
        )
        again = run_investigation(request, session, backend["settings"], client)
    assert again == result and len(requests) == 4  # replay makes no provider call
    evidence = result["evidence"]
    assert [item["tool"] for item in evidence.values()] == [
        "overview",
        "rank_associations",
        "model_summary",
        "segment_rates",
        "compare_cohorts",
        "segment_rates",
    ]
    assert "not approved" in evidence["E6"]["error"]  # identifier column refused by code
    assert evidence["E5"]["result"]["cohort_a"]["label"] == "Monthly"
    assert result["report"]["status"] == "verified"
    assert len(result["report"]["findings"]) == 2
    # The writer's revision request carried the verifier's concrete objections.
    revision_input = json.loads(requests[3]["messages"][1]["content"])
    assert any("99.9%" in line for line in revision_input["verifier_problems"])
    assert any("causal" in line for line in revision_input["verifier_problems"])
    stages = [(e["name"], e["status"]) for e in events if e["type"] == "stage"]
    assert ("plan", "end") in stages and ("verify", "end") in stages
    assert stages[-1] == ("finalize", "end")
    saved = backend["client"].get(f"/api/v1/analyses/{result['id']}")
    assert saved.status_code == 200 and saved.json()["kind"] == "investigation"
    trace = backend["client"].get(f"/api/v1/assistant/traces/{result['trace_id']}").json()
    assert trace["trace"]["model_calls"] == 4
    assert [s["name"] for s in trace["spans"] if s["kind"] == "model"] == [
        "investigator:plan",
        "investigator:follow_up",
        "investigator:write",
        "investigator:revise",
    ]


def test_investigation_requires_consent_and_development_rows_only(backend, trained):
    response = backend["client"].post(
        "/api/v1/investigations",
        json={"run_id": trained["run_id"], "question": "Why?", "idempotency_key": str(uuid4())},
    )
    assert response.status_code == 422
    client, _ = scripted([PLAN, FOLLOW_UP, REVISED])
    with Session(backend["app"].state.engine) as session:
        result = run_investigation(
            InvestigationRequest(
                run_id=trained["run_id"],
                question="Which segments churn most?",
                provider_consent=True,
                idempotency_key=uuid4(),
            ),
            session,
            backend["settings"],
            client,
        )
    from customer_intelligence.services.runs import read_training_run

    split = read_training_run(UUID(trained["run_id"]), backend["settings"].data_directory).split
    development = len(split.row_assignments["train"]) + len(split.row_assignments["validation"])
    assert result["evidence"]["E1"]["result"]["rows"] == development
    assert result["report"]["status"] == "verified"


def test_verifier_precision_on_labels_and_non_outcome_wording():
    draft = report(
        ("Monthly churn is 56.9% (95% CI shown in evidence).", ["E2"]),
        ("Estimates are uncertain due to small samples; overall churn is 46.1%.", ["E1"]),
    )
    assert verify_report(draft, EVIDENCE)["passed"]
    assert causal_claims("Failed payments lead to churn.") == ["lead to"]


def test_failed_optional_follow_up_does_not_fail_the_investigation(backend, trained):
    truncated = {"choices_override": True}
    client, requests = scripted([PLAN, truncated, truncated, REVISED])
    request = InvestigationRequest(
        run_id=trained["run_id"],
        question="Which segments churn most?",
        provider_consent=True,
        idempotency_key=uuid4(),
    )
    events: list[dict] = []
    with Session(backend["app"].state.engine) as session:
        result = run_investigation(
            request, session, backend["settings"], client, listener=events.append
        )
    assert result["report"]["status"] == "verified"
    assert ("follow_up", "skipped") in [
        (e["name"], e["status"]) for e in events if e["type"] == "stage"
    ]
    # The repair request explains that the first response was truncated.
    assert "cut off" in requests[2]["messages"][-1]["content"]


def test_investigation_stream_reports_stages_and_saved_artifact(backend, trained, monkeypatch):
    client, _ = scripted([PLAN, FOLLOW_UP, REVISED])
    monkeypatch.setattr(
        "customer_intelligence.agent.provider.provider_client", lambda settings: client
    )
    with backend["client"].stream(
        "POST",
        "/api/v1/investigations/stream",
        json={
            "run_id": trained["run_id"],
            "question": "Which segments churn most?",
            "provider_consent": True,
            "idempotency_key": str(uuid4()),
        },
    ) as response:
        assert response.status_code == 200
        blocks = [b for b in response.read().decode().split("\n\n") if b.startswith("event:")]
    names = [block.splitlines()[0].removeprefix("event: ") for block in blocks]
    assert names[-1] == "answer"
    assert "stage" in names and "tool_start" in names and "model_start" in names
    saved = json.loads(blocks[-1].splitlines()[1].removeprefix("data: "))["response"]
    assert saved["kind"] == "investigation" and saved["report"]["status"] == "verified"
