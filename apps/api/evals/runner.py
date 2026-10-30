"""Build a temporary synthetic workspace, run each scenario through the real agent, grade it."""

import json
import tempfile
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field, SecretStr
from sqlmodel import Session

from customer_intelligence.agent import provider
from customer_intelligence.agent.llm import LLMGateway
from customer_intelligence.agent.prompts import ACTIVE, load_prompt
from customer_intelligence.agent.tracing import traced
from customer_intelligence.agent.workflow import chat
from customer_intelligence.core.config import PROJECT_DIRECTORY, Settings
from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.main import create_app
from customer_intelligence.models.trace import AgentTrace
from customer_intelligence.schemas.investigation import InvestigationRequest
from customer_intelligence.schemas.retention import BriefingRequest
from customer_intelligence.schemas.workflow import AssistantRequest
from customer_intelligence.services import retention
from customer_intelligence.services.investigation import run_investigation
from customer_intelligence.services.training import train_task
from evals import graders
from evals.cassette import CassetteMismatch, Exchange, RecordingTransport, ReplayTransport
from evals.dataset import FEATURES, saas_accounts_csv
from evals.scenarios import SCENARIOS, Scenario

REPORT_DIRECTORY = PROJECT_DIRECTORY / ".data" / "evals"


class JudgeVerdict(BaseModel):
    groundedness: int = Field(ge=1, le=5)
    caveats: int = Field(ge=1, le=5)
    usefulness: int = Field(ge=1, le=5)
    unsupported_statements: list[str] = Field(default_factory=list, max_length=10)


def eval_settings(directory: Path, live: bool) -> Settings:
    if live:
        settings = Settings(auth_mode="private", data_directory=directory, environment="test")
        if not (settings.nebius_api_key and settings.nebius_base_url and settings.nebius_model):
            raise SystemExit("Live evals need NEBIUS_API_KEY, NEBIUS_BASE_URL and NEBIUS_MODEL.")
        return settings
    return Settings(
        auth_mode="private",
        _env_file=None,  # type: ignore[call-arg]
        data_directory=directory,
        environment="test",
        nebius_api_key=SecretStr("replay"),
        nebius_base_url="https://replay.invalid/v1",  # type: ignore[arg-type]
        nebius_model="replay-model",
        nebius_max_retries=0,
    )


def build_workspace(app_client: TestClient, settings: Settings, engine: Any) -> dict[str, str]:
    upload = app_client.post(
        "/api/v1/datasets/upload",
        files={"file": ("saas_accounts.csv", saas_accounts_csv(), "text/csv")},
    )
    upload.raise_for_status()
    dataset_id = upload.json()["id"]
    task = app_client.post(
        f"/api/v1/datasets/{dataset_id}/tasks",
        json={
            "target_column": "churned",
            "positive_label": "Yes",
            "id_column": "account_id",
            "feature_columns": FEATURES,
            "features_available_at_prediction": True,
        },
    )
    task.raise_for_status()
    task_id = task.json()["id"]
    with Session(engine) as session:
        run_id = train_task(session, settings, UUID(task_id)).name
    return {"dataset_id": dataset_id, "task_id": task_id, "run_id": run_id}


def run_scenario(
    scenario: Scenario,
    ids: dict[str, str],
    settings: Settings,
    engine: Any,
    live: bool,
    record: bool,
    judge: bool,
) -> dict[str, Any]:
    placeholders = {actual: "{{" + key + "}}" for key, actual in ids.items()}
    transport: Exchange
    if live:
        recorder = RecordingTransport(httpx.HTTPTransport(retries=1), placeholders)
        transport = recorder
    else:
        transport = ReplayTransport(scenario.name, placeholders)
    client = provider.provider_client(settings, transport)
    result: dict[str, Any] = {"name": scenario.name, "tags": list(scenario.tags)}
    grades: list[graders.GradeResult] = []
    started = time.monotonic()
    trace_id: UUID | None = None
    try:
        with Session(engine) as session:
            if scenario.kind == "briefing":
                with traced(session, "eval.briefing") as tracer:
                    briefing = retention.executive_briefing(
                        BriefingRequest(
                            run_id=UUID(ids["run_id"]),
                            provider_consent=True,
                            idempotency_key=uuid4(),
                        ),
                        session,
                        settings,
                        client,
                    )
                trace_id = tracer.id
                paragraphs = briefing.get("paragraphs", [])
                answer = "\n\n".join(paragraphs)
                evidence = json.loads(transport.requests[-1]["messages"][1]["content"])
                grades.append(
                    graders.schema_valid(
                        "briefing_schema",
                        len(paragraphs) == 3 and all(p.strip() for p in paragraphs),
                        None if len(paragraphs) == 3 else f"{len(paragraphs)} paragraphs",
                    )
                )
                grades.append(
                    graders.numeric_grounding(answer, [evidence], scenario.grounding_threshold)
                )
                outputs: list[Any] = [evidence]
            elif scenario.kind == "investigation":
                saved = run_investigation(
                    InvestigationRequest(
                        run_id=UUID(ids["run_id"]),
                        question=scenario.question,
                        provider_consent=True,
                        idempotency_key=uuid4(),
                    ),
                    session,
                    settings,
                    client,
                )
                trace_id = UUID(saved["trace_id"])
                final = saved["report"]
                answer = "\n".join(
                    [final["headline"], *(f["statement"] for f in final["findings"])]
                )
                outputs = [
                    item["result"] for item in saved["evidence"].values() if "result" in item
                ]
                result["investigation"] = {
                    "status": final["status"],
                    "withheld": final["withheld"],
                    "checks": [item.get("hypothesis") for item in saved["evidence"].values()],
                    "draft_verification_passed": saved["verification"]["passed"],
                }
                grades.append(
                    graders.schema_valid(
                        "verified_report",
                        final["status"] != "unverified",
                        None if final["status"] != "unverified" else "no verified findings",
                    )
                )
                grades.append(
                    graders.numeric_grounding(answer, outputs, scenario.grounding_threshold)
                )
                if scenario.expected_drivers:
                    grades.append(
                        graders.driver_recall(
                            answer, set(scenario.expected_drivers), scenario.driver_recall
                        )
                    )
                if scenario.analyzed_columns:
                    grades.append(
                        graders.analyzed(saved["evidence"], set(scenario.analyzed_columns))
                    )
                if scenario.none_of:
                    grades.append(graders.required_language(answer, [], list(scenario.none_of)))
                grades.append(graders.budget(saved["model_calls"], scenario.max_model_calls))
            else:
                request = AssistantRequest(
                    dataset_id=UUID(ids["dataset_id"]),
                    task_id=UUID(ids["task_id"]) if "task" in scenario.context else None,
                    run_id=UUID(ids["run_id"]) if "run" in scenario.context else None,
                    question=scenario.question,
                    idempotency_key=uuid4(),
                    allow_actions=scenario.allow_actions,
                )
                response = chat(request, session, settings, client)
                trace_id = response.trace_id
                answer = response.answer
                outputs = graders.tool_outputs(transport.requests[-1]["messages"])
                called = [event.tool for event in response.events]
                grades.append(
                    graders.trajectory(
                        called, set(scenario.required_tools), set(scenario.forbidden_tools)
                    )
                )
                grades.append(
                    graders.numeric_grounding(
                        answer, [*outputs, scenario.question], scenario.grounding_threshold
                    )
                )
                if scenario.any_of or scenario.none_of:
                    grades.append(
                        graders.required_language(
                            answer, list(scenario.any_of), list(scenario.none_of)
                        )
                    )
                grades.append(graders.budget(response.model_call_count, scenario.max_model_calls))
            trace = session.get(AgentTrace, trace_id) if trace_id else None
            result["metrics"] = {
                "model_calls": trace.model_calls if trace else None,
                "retries": trace.retries if trace else None,
                "input_tokens": trace.input_tokens if trace else None,
                "output_tokens": trace.output_tokens if trace else None,
                "cost_usd": trace.cost_usd if trace else None,
                "duration_ms": round((time.monotonic() - started) * 1000),
            }
            result["answer"] = answer
            if judge and live and scenario.kind == "assistant":
                result["judge"] = run_judge(settings, scenario.question, answer, outputs)
    except (WorkflowError, CassetteMismatch) as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        client.close()
    if live and record:
        result["cassette"] = str(recorder.save(scenario.name))
    result["grades"] = [asdict(grade) for grade in grades]
    result["passed"] = "error" not in result and all(grade.passed for grade in grades)
    return result


def run_judge(settings: Settings, question: str, answer: str, outputs: list[Any]) -> dict:
    encoded = json.dumps(outputs, default=str)[:40_000]
    with LLMGateway(settings) as gateway:
        try:
            verdict = gateway.structured(
                load_prompt("eval_judge").text,
                {"question": question, "answer": answer, "tool_outputs": encoded},
                JudgeVerdict,
            )
        except WorkflowError as exc:
            return {"error": str(exc)}
    return verdict.model_dump()


def run(
    live: bool, record: bool, judge: bool, only: list[str] | None, repeat: int = 1
) -> tuple[dict[str, Any], Path]:
    selected = [s for s in SCENARIOS if not only or s.name in only]
    with tempfile.TemporaryDirectory(prefix="ci-evals-") as directory:
        settings = eval_settings(Path(directory), live)
        app = create_app(settings)
        with TestClient(app) as app_client:
            ids = build_workspace(app_client, settings, app.state.engine)
            # Model output varies between samples; repeats turn one sample into a pass rate.
            results = []
            for index in range(repeat):
                for scenario in selected:
                    item = run_scenario(
                        scenario,
                        ids,
                        settings,
                        app.state.engine,
                        live,
                        record and index == 0,
                        judge,
                    )
                    item["repeat"] = index + 1
                    results.append(item)
        model = settings.nebius_model if live else "recorded"
    grounding = [
        grade["score"]
        for item in results
        for grade in item["grades"]
        if grade["name"] == "numeric_grounding"
    ]
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "mode": "live" if live else "replay",
        "model": model,
        "prompts": {name: load_prompt(name).label for name in ACTIVE},
        "summary": {
            "passed": sum(item["passed"] for item in results),
            "total": len(results),
            "mean_numeric_grounding": round(sum(grounding) / len(grounding), 4)
            if grounding
            else None,
        },
        "by_scenario": {
            scenario.name: {
                "runs": sum(item["name"] == scenario.name for item in results),
                "passed": sum(item["name"] == scenario.name and item["passed"] for item in results),
            }
            for scenario in selected
        },
        "scenarios": results,
    }
    REPORT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIRECTORY / f"report-{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{report['mode']}.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    return report, path
