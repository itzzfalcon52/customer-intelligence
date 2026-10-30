import json
from uuid import UUID, uuid4

import httpx
import numpy as np
import pytest
from openai import APIConnectionError, APITimeoutError, OpenAI
from sqlmodel import Session

from customer_intelligence.agent.provider import provider_error, structured
from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.ml.evaluation import candidate_specs
from customer_intelligence.ml.policy import select_threshold
from customer_intelligence.models.task import Task
from customer_intelligence.schemas.retention import (
    ApplySchemaRequest,
    CampaignDrafts,
    CampaignRequest,
    ColumnFinding,
    ROIRequest,
    RuleCondition,
    RuleProposal,
    RuleRequest,
    SchemaReasoning,
    SchemaReviewRequest,
)
from customer_intelligence.schemas.workflow import ScoreRequest
from customer_intelligence.services import retention
from customer_intelligence.services.runs import load_pipeline, read_training_run
from customer_intelligence.services.scoring import score_dataset
from customer_intelligence.services.training import task_partitions, train_task


def test_structured_provider_contract_and_redacted_errors(backend):
    captured = []

    def handle(request):
        captured.append(json.loads(request.content))
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
                            "tool_calls": [
                                {
                                    "id": "c",
                                    "type": "function",
                                    "function": {
                                        "name": "deliver_result",
                                        "arguments": json.dumps(
                                            {
                                                "summary": "Review timing.",
                                                "findings": [],
                                                "questions": [],
                                            }
                                        ),
                                    },
                                }
                            ],
                        },
                    }
                ],
            },
        )

    with OpenAI(
        api_key="test-key",
        base_url="https://example.invalid/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(handle)),
    ) as client:
        result = structured(
            backend["settings"], "Review schema", {"columns": []}, SchemaReasoning, client
        )
    assert result.summary == "Review timing."
    assert captured[0]["tool_choice"]["function"]["name"] == "deliver_result"
    request = httpx.Request("POST", "https://example.invalid/v1")
    assert provider_error(APIConnectionError(request=request)).code == "provider_connection"
    assert provider_error(APITimeoutError(request=request)).code == "provider_timeout"


def test_schema_review_requires_consent_and_preserves_task(backend, trained, monkeypatch):
    request = SchemaReviewRequest(
        task_id=trained["task_id"], idempotency_key=uuid4(), provider_consent=True
    )
    calls = []

    def reasoning(settings, instruction, evidence, schema, client=None):
        calls.append(evidence)
        assert "preview" not in json.dumps(evidence) and "C0001" not in json.dumps(evidence)
        return SchemaReasoning(
            summary="Review feature timing.",
            questions=["Were features observed before churn?"],
            findings=[
                ColumnFinding(
                    column=c,
                    decision="exclude" if c == "TotalCharges" else "keep",
                    reason="Review availability.",
                )
                for c in evidence["selected_features"]
            ],
        )

    monkeypatch.setattr(retention, "structured", reasoning)
    client = backend["client"]
    assert (
        client.post(
            "/api/v1/retention/schema-review",
            json={"task_id": trained["task_id"], "idempotency_key": str(uuid4())},
        ).status_code
        == 422
    )
    with Session(backend["app"].state.engine) as session:
        result = retention.analyze_schema_semantics(request, session, backend["settings"])
        assert result == retention.analyze_schema_semantics(request, session, backend["settings"])
        assert len(calls) == 1
        assert "TotalCharges" in session.get(Task, UUID(trained["task_id"])).feature_columns
        applied = retention.apply_schema(
            ApplySchemaRequest(review_id=result["id"], features_available_at_prediction=True),
            session,
            backend["settings"],
        )
        assert (
            applied.id != UUID(trained["task_id"]) and "TotalCharges" not in applied.feature_columns
        )
        assert (
            retention.apply_schema(
                ApplySchemaRequest(review_id=result["id"], features_available_at_prediction=True),
                session,
                backend["settings"],
            ).id
            == applied.id
        )
        with pytest.raises(WorkflowError, match="different inputs"):
            retention.analyze_schema_semantics(
                request.model_copy(update={"provider_consent": False}), session, backend["settings"]
            )


def test_schema_hallucinated_columns_rejected(backend, trained, monkeypatch):
    monkeypatch.setattr(
        retention,
        "structured",
        lambda *args: SchemaReasoning(
            summary="x",
            findings=[ColumnFinding(column="invented", decision="keep", reason="x")],
            questions=[],
        ),
    )
    with (
        Session(backend["app"].state.engine) as session,
        pytest.raises(WorkflowError, match="exactly once"),
    ):
        retention.analyze_schema_semantics(
            SchemaReviewRequest(
                task_id=trained["task_id"], idempotency_key=uuid4(), provider_consent=True
            ),
            session,
            backend["settings"],
        )


@pytest.mark.parametrize(
    "column", ["churn_date", "cancellationReason", "cancelled_at", "termination_date"]
)
def test_obvious_post_outcome_names(column):
    assert retention.obvious_leakage(column)
    assert not retention.obvious_leakage("tenure")


def test_roi_budget_zero_negative_and_scoring_scope(backend, trained):
    with Session(backend["app"].state.engine) as session:
        base = dict(
            run_id=trained["run_id"],
            budget=1000,
            contact_cost=10,
            offer_cost=20,
            assumed_save_rate=0.2,
            retained_value=1000,
            population_size=500,
            currency="INR",
        )
        result = retention.calculate_intervention_roi(
            ROIRequest(**base), session, backend["settings"]
        )
        assert 0 <= result["recommended_contacts"] <= 33
        assert result["reserved_cost"] <= 1000
        assert result["budget_remaining"] >= 0
        assert (
            retention.calculate_intervention_roi(
                ROIRequest(**{**base, "budget": 0}), session, backend["settings"]
            )["recommended_contacts"]
            == 0
        )
        assert (
            retention.calculate_intervention_roi(
                ROIRequest(**{**base, "assumed_save_rate": 0}), session, backend["settings"]
            )["recommended_contacts"]
            == 0
        )
        score_id = score_dataset(
            session,
            backend["settings"],
            ScoreRequest(
                run_id=trained["run_id"],
                dataset_id=trained["dataset_id"],
                contact_count=5,
                idempotency_key=uuid4(),
            ),
        )
        scoped = retention.calculate_intervention_roi(
            ROIRequest(**{**base, "score_id": score_id}), session, backend["settings"]
        )
        assert scoped["population_size"] == 480
        assert len(scoped["shortlist"]) <= scoped["recommended_contacts"]
        assert (
            backend["client"].post("/api/v1/retention/roi", json={**base, "budget": -1}).status_code
            == 422
        )


def test_campaign_uses_permitted_facts_not_customer_ids(backend, trained, monkeypatch):
    captured = []

    def writer(settings, instruction, evidence, schema, client=None):
        captured.append(evidence)
        assert "C0001" not in json.dumps(evidence)
        assert all(set(c["features"]) == {"tenure", "Contract"} for c in evidence["customers"])
        return CampaignDrafts(
            drafts=[
                {
                    "row_reference": c["row_reference"],
                    "subject": "A quick check-in",
                    "body": "Hello, can we help you get more from the service?",
                    "evidence_features": ["Contract"],
                }
                for c in evidence["customers"]
            ]
        )

    monkeypatch.setattr(retention, "structured", writer)
    with Session(backend["app"].state.engine) as session:
        score_id = score_dataset(
            session,
            backend["settings"],
            ScoreRequest(
                run_id=trained["run_id"],
                dataset_id=trained["dataset_id"],
                contact_count=5,
                idempotency_key=uuid4(),
            ),
        )
        request = CampaignRequest(
            score_id=score_id,
            idempotency_key=uuid4(),
            provider_consent=True,
            permitted_features=["tenure", "Contract"],
        )
        result = retention.generate_retention_campaign(request, session, backend["settings"])
        assert result["status"] == "draft_only" and len(result["drafts"]) == 5
        assert all("customer_id" in d for d in result["drafts"])
        assert (
            retention.generate_retention_campaign(request, session, backend["settings"]) == result
        )
        assert len(captured) == 1
        with pytest.raises(WorkflowError, match="distinct model features"):
            retention.generate_retention_campaign(
                request.model_copy(
                    update={"idempotency_key": uuid4(), "permitted_features": ["customerID"]}
                ),
                session,
                backend["settings"],
            )


def test_campaign_hallucinated_customer_is_rejected(backend, trained, monkeypatch):
    monkeypatch.setattr(
        retention,
        "structured",
        lambda *args: CampaignDrafts(
            drafts=[{"row_reference": 50000, "subject": "x", "body": "x", "evidence_features": []}]
        ),
    )
    with Session(backend["app"].state.engine) as session:
        score_id = score_dataset(
            session,
            backend["settings"],
            ScoreRequest(
                run_id=trained["run_id"],
                dataset_id=trained["dataset_id"],
                contact_count=5,
                idempotency_key=uuid4(),
            ),
        )
        with pytest.raises(WorkflowError, match="permitted customers"):
            retention.generate_retention_campaign(
                CampaignRequest(score_id=score_id, idempotency_key=uuid4(), provider_consent=True),
                session,
                backend["settings"],
            )


def test_rule_dsl_is_measured_and_cannot_execute_code(backend, trained, monkeypatch):
    def propose(settings, instruction, evidence, schema, client=None):
        assert "preview" not in evidence and evidence["columns"][0]["name"] == "tenure"
        return RuleProposal(
            name="Short tenure",
            rationale="Simple hypothesis.",
            conditions=[RuleCondition(column="tenure", operator="lt", value="20")],
        )

    monkeypatch.setattr(retention, "structured", propose)
    with Session(backend["app"].state.engine) as session:
        result = retention.challenge_business_rule(
            RuleRequest(run_id=trained["run_id"], idempotency_key=uuid4(), provider_consent=True),
            session,
            backend["settings"],
        )
        assert result["partition"] == "validation" and result["metrics"]["row_count"] == 72
        assert result["metrics"]["predicted_positive_count"] > 0
        monkeypatch.setattr(
            retention,
            "structured",
            lambda *args: RuleProposal(
                name="Bad",
                rationale="x",
                conditions=[RuleCondition(column="__import__", operator="eq", value="os")],
            ),
        )
        with pytest.raises(WorkflowError, match="unapproved feature"):
            retention.challenge_business_rule(
                RuleRequest(
                    run_id=trained["run_id"], idempotency_key=uuid4(), provider_consent=True
                ),
                session,
                backend["settings"],
            )


def test_training_cv_policy_preserves_test_and_old_pipeline(backend, trained):
    assert candidate_specs(42, 2)[4][0] == "xgboost"
    with Session(backend["app"].state.engine) as session:
        path = train_task(
            session,
            backend["settings"],
            UUID(trained["task_id"]),
            search_trials=2,
            cv_folds=3,
            threshold_policy="precision_at_recall",
            minimum_recall=0.5,
        )
        run = read_training_run(UUID(path.name), backend["settings"].data_directory)
        assert run.report.training_cv_folds == 3 and len(run.report.results) == 6
        assert all(r.training_cv_average_precision is not None for r in run.report.results)
        assert run.report.threshold_selection["source"] == "training_3_fold_oof"
        assert run.report.threshold_selection["oof_metrics"]["recall"] >= 0.5
        assert len(run.report.threshold_selection["validation_curve"]) == 18
        assert not (path / "evaluation.json").exists()
        old = read_training_run(UUID(trained["run_id"]), backend["settings"].data_directory)
        load_pipeline(old, backend["settings"].data_directory)
        task, split, frame = task_partitions(session, backend["settings"], UUID(trained["task_id"]))
        model = load_pipeline(run, backend["settings"].data_directory)
        tr = frame.iloc[split.row_assignments["train"]]
        va = frame.iloc[split.row_assignments["validation"]]
        kwargs = dict(
            pipeline=model,
            training=tr[task.feature_columns],
            labels=[task.label_mapping[str(v)] for v in tr.Churn],
            validation=va[task.feature_columns],
            validation_labels=[task.label_mapping[str(v)] for v in va.Churn],
            policy="fixed",
            fixed=0.6,
            minimum_recall=0.5,
            seed=42,
        )
        assert select_threshold(**kwargs)["threshold"] == 0.6
        # Predictions and ranking are unaffected by threshold choice.
        np.testing.assert_allclose(
            model.predict_proba(va[task.feature_columns]),
            load_pipeline(run, backend["settings"].data_directory).predict_proba(
                va[task.feature_columns]
            ),
        )


def test_agent_calls_roi_tool_with_validated_scope(backend, trained):
    from test_agent import provider, tools

    from customer_intelligence.agent.workflow import chat
    from customer_intelligence.schemas.workflow import AssistantRequest

    request = AssistantRequest(
        dataset_id=trained["dataset_id"],
        task_id=trained["task_id"],
        run_id=trained["run_id"],
        question=(
            "Calculate a budget scenario: budget 1000, contact cost 10, "
            "save rate .2, retained value 1000."
        ),
        idempotency_key=uuid4(),
        allow_actions=True,
    )
    client, captured = provider(
        [
            tools(
                ("inspect_dataset", {"resource_id": trained["dataset_id"]}),
                ("read_task", {"resource_id": trained["task_id"]}),
                ("read_run", {"resource_id": trained["run_id"]}),
            ),
            tools(
                (
                    "calculate_intervention_roi",
                    {
                        "run_id": trained["run_id"],
                        "budget": 1000,
                        "contact_cost": 10,
                        "assumed_save_rate": 0.2,
                        "retained_value": 1000,
                    },
                )
            ),
            {
                "role": "assistant",
                "content": (
                    "The budget scenario was calculated. The save rate is an assumption, "
                    "not measured uplift."
                ),
            },
        ]
    )
    with client, Session(backend["app"].state.engine) as session:
        result = chat(request, session, backend["settings"], client)
    assert result.events[-1].tool == "calculate_intervention_roi"
    schema = next(
        t["function"]["parameters"]
        for t in captured[0]["tools"]
        if t["function"]["name"] == "calculate_intervention_roi"
    )
    assert "assumed_save_rate" in schema["required"]
    payload = json.loads(captured[-1]["messages"][-1]["content"])
    assert payload["reserved_cost"] <= 1000 and "Scenario" in payload["warning"]


def test_agent_cannot_call_actions_without_permission(backend, trained):
    from test_agent import provider, tools

    from customer_intelligence.agent.workflow import chat
    from customer_intelligence.schemas.workflow import AssistantRequest

    client, _ = provider([tools(("analyze_schema_semantics", {"task_id": trained["task_id"]}))])
    with (
        client,
        Session(backend["app"].state.engine) as session,
        pytest.raises(WorkflowError, match="unsupported tool"),
    ):
        chat(
            AssistantRequest(
                dataset_id=trained["dataset_id"],
                task_id=trained["task_id"],
                question="Review schema",
                idempotency_key=uuid4(),
            ),
            session,
            backend["settings"],
            client,
        )


def test_action_apis_reject_unknown_resources(backend):
    client = backend["client"]
    result = client.post(
        "/api/v1/retention/schema-review",
        json={"task_id": str(uuid4()), "idempotency_key": str(uuid4()), "provider_consent": True},
    )
    assert result.status_code == 404
    result = client.post(
        "/api/v1/retention/apply-schema",
        json={"review_id": str(uuid4()), "features_available_at_prediction": True},
    )
    assert result.status_code == 404


def test_failed_auto_brief_does_not_fail_training(backend, trained, execute_job, monkeypatch):
    def fail(*args, **kwargs):
        raise WorkflowError("Provider temporarily unavailable.", 503)

    monkeypatch.setattr(retention, "executive_briefing", fail)
    result = backend["client"].post(
        "/api/v1/jobs/train",
        json={
            "task_id": trained["task_id"],
            "idempotency_key": str(uuid4()),
            "search_trials": 0,
            "generate_briefing": True,
        },
    )
    assert result.status_code == 202, result.text
    job = execute_job(result.json()["id"])
    assert job["state"] == "succeeded"
    brief = backend["client"].get(f"/api/v1/runs/{job['result_id']}/briefing").json()
    assert brief["state"] == "failed"
    assert backend["client"].get(f"/api/v1/runs/{job['result_id']}").status_code == 200


def test_structured_json_compatibility_and_rejects_free_text(backend):
    def client_for(content):
        return OpenAI(
            api_key="test",
            base_url="https://example.invalid/v1",
            http_client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        200,
                        json={
                            "id": "r",
                            "object": "chat.completion",
                            "created": 1,
                            "model": "test-model",
                            "choices": [
                                {
                                    "index": 0,
                                    "finish_reason": "stop",
                                    "message": {"role": "assistant", "content": content},
                                }
                            ],
                        },
                    )
                )
            ),
        )

    with client_for(json.dumps({"summary": "x", "findings": [], "questions": []})) as client:
        assert structured(backend["settings"], "review", {}, SchemaReasoning, client).summary == "x"
    with (
        client_for("Please run arbitrary Python code") as client,
        pytest.raises(WorkflowError, match="invalid result"),
    ):
        structured(backend["settings"], "review", {}, SchemaReasoning, client)


def test_failed_auto_campaign_preserves_scoring(backend, trained, execute_job, monkeypatch):
    monkeypatch.setattr(
        retention,
        "generate_retention_campaign",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            WorkflowError("Provider temporarily unavailable.", 503)
        ),
    )
    response = backend["client"].post(
        "/api/v1/jobs/score",
        json={
            "run_id": trained["run_id"],
            "dataset_id": trained["dataset_id"],
            "contact_count": 5,
            "idempotency_key": str(uuid4()),
            "outreach": {
                "provider_consent": True,
                "product_name": "Synthetic Demo",
                "approved_offer": "A helpful check-in",
            },
        },
    )
    assert response.status_code == 202, response.text
    job = execute_job(response.json()["id"])
    assert job["state"] == "succeeded"
    assert (
        backend["client"].get(f"/api/v1/scores/{job['result_id']}/campaign").json()["state"]
        == "failed"
    )
    assert backend["client"].get(f"/api/v1/scores/{job['result_id']}/customers").status_code == 200


def test_action_lease_protects_both_dataset_dependencies(backend, trained):
    from sqlmodel import select

    from customer_intelligence.models.conversation import AssistantLease

    second = uuid4()
    key = uuid4()
    with Session(backend["app"].state.engine) as session:
        with retention.action_lock(session, key, UUID(trained["dataset_id"]), second):
            leases = session.exec(select(AssistantLease)).all()
            assert {UUID(trained["dataset_id"]), second} <= {lease.dataset_id for lease in leases}
        assert not session.exec(
            select(AssistantLease).where(AssistantLease.dataset_id == second)
        ).all()


def _roi_turn(trained, steps):
    from test_agent import provider

    from customer_intelligence.schemas.workflow import AssistantRequest

    request = AssistantRequest(
        dataset_id=trained["dataset_id"],
        task_id=trained["task_id"],
        run_id=trained["run_id"],
        question="Budget 1000, contact cost 10, save rate 0.2, retained value 1000.",
        idempotency_key=uuid4(),
        allow_actions=True,
    )
    return request, provider(steps)


def test_agent_recovers_from_bad_action_values_and_repeated_reads(backend, trained):
    from test_agent import tools

    from customer_intelligence.agent.workflow import chat

    reads = tools(
        ("inspect_dataset", {"resource_id": trained["dataset_id"]}),
        ("read_task", {"resource_id": trained["task_id"]}),
        ("read_run", {"resource_id": trained["run_id"]}),
    )
    roi = {
        "run_id": trained["run_id"],
        "budget": 1000,
        "contact_cost": 10,
        "assumed_save_rate": 0.2,
        "retained_value": 1000,
    }
    request, (client, captured) = _roi_turn(
        trained,
        [
            reads,
            # A save rate of 20 instead of 0.2 is a fixable value error, plus a repeated read.
            tools(
                ("calculate_intervention_roi", {**roi, "assumed_save_rate": 20}),
                ("read_run", {"resource_id": trained["run_id"]}),
            ),
            tools(("calculate_intervention_roi", roi)),
            {"role": "assistant", "content": "The scenario uses your assumed save rate."},
        ],
    )
    with client, Session(backend["app"].state.engine) as session:
        result = chat(request, session, backend["settings"], client)
    feedback = [json.loads(m["content"]) for m in captured[2]["messages"] if m["role"] == "tool"]
    assert "assumed_save_rate" in feedback[-2]["error"] and "20" not in feedback[-2]["error"]
    assert "Already retrieved" in feedback[-1]["note"]
    assert result.events[-1].tool == "calculate_intervention_roi"
    spans = backend["client"].get(f"/api/v1/assistant/traces/{result.trace_id}").json()["spans"]
    assert [s["error_code"] for s in spans if s["kind"] == "tool"][3:5] == [
        "invalid_arguments",
        "repeated_call",
    ]


def test_unknown_action_fields_remain_fatal(backend, trained):
    from test_agent import tools

    from customer_intelligence.agent.workflow import chat

    request, (client, _) = _roi_turn(
        trained,
        [
            tools(
                (
                    "calculate_intervention_roi",
                    {"run_id": trained["run_id"], "budget": 1, "shell": "rm -rf /"},
                )
            )
        ],
    )
    with (
        client,
        Session(backend["app"].state.engine) as session,
        pytest.raises(WorkflowError, match="invalid tool arguments"),
    ):
        chat(request, session, backend["settings"], client)


def test_refused_action_is_reported_to_the_model(backend, trained, monkeypatch):
    from test_agent import tools

    from customer_intelligence.agent.workflow import chat

    monkeypatch.setattr(
        retention,
        "analyze_schema_semantics",
        lambda *args: (_ for _ in ()).throw(
            WorkflowError("Schema reasoning must cover each selected feature exactly once.", 502)
        ),
    )
    request, (client, captured) = _roi_turn(
        trained,
        [
            tools(
                ("inspect_dataset", {"resource_id": trained["dataset_id"]}),
                ("read_task", {"resource_id": trained["task_id"]}),
                ("read_run", {"resource_id": trained["run_id"]}),
                ("analyze_schema_semantics", {"task_id": trained["task_id"]}),
            ),
            {"role": "assistant", "content": "The schema review was unavailable."},
        ],
    )
    with client, Session(backend["app"].state.engine) as session:
        result = chat(request, session, backend["settings"], client)
    assert result.answer == "The schema review was unavailable."
    refusal = json.loads(captured[1]["messages"][-1]["content"])
    assert "exactly once" in refusal["error"]
