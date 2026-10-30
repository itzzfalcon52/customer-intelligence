import json
import time
from typing import Any, Literal
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlmodel import Session, col, select

from customer_intelligence.agent.grounding import ungrounded_numbers
from customer_intelligence.agent.llm import LLMGateway, describe_validation_error
from customer_intelligence.agent.prompts import load_prompt
from customer_intelligence.agent.tracing import Listener, Tracer, traced
from customer_intelligence.agent.verification import causal_claims
from customer_intelligence.core.config import Settings
from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.models.conversation import Conversation, ConversationTurn
from customer_intelligence.models.dataset import Dataset
from customer_intelligence.models.task import Task
from customer_intelligence.schemas.retention import (
    BriefingRequest,
    CampaignRequest,
    ROIRequest,
    RuleRequest,
    SchemaReviewRequest,
)
from customer_intelligence.schemas.task import TaskResponse
from customer_intelligence.schemas.workflow import (
    AssistantRequest,
    AssistantResponse,
    JobResponse,
    ToolEvent,
)
from customer_intelligence.schemas.workspace import MemoryResponse
from customer_intelligence.services import playbooks, retention, workspace
from customer_intelligence.services.jobs import get_job, submit_job
from customer_intelligence.services.plans import training_plan
from customer_intelligence.services.profiling import profile_dataset
from customer_intelligence.services.runs import read_training_run
from customer_intelligence.services.scoring import read_score

PROMPT = load_prompt("assistant")


class RecoverableToolError(Exception):
    """A well-formed, in-scope call with a bad value: reported to the model, never executed."""


MEMORY_SCOPE = UUID(int=1)
CATALOG_SCOPE = UUID(int=2)
PLAYBOOK_SCOPE = UUID(int=3)
TOOL_DESCRIPTIONS = {
    "inspect_dataset": "Profile of the dataset: columns, types, missing values, warnings.",
    "read_task": "The confirmed churn definition: outcome, positive label, ID and inputs.",
    "read_run": "Model comparison for a training run: validation metrics per candidate, "
    "threshold policy, calibration and any final test evaluation.",
    "read_job": "Status of a background job.",
    "read_scores": "Summary of a scoring batch: size, ranking method, warnings.",
    "read_analysis": "A saved analysis: importance, contact curves, segments or explanations.",
    "propose_training": "The fixed training plan for a task (candidates and limits).",
    "submit_training": "Queue the training plan. Only after propose_training.",
    "read_workspace_memory": "Business assumptions and decisions the user saved earlier.",
    "list_workspace_resources": "Catalogue of the user's datasets, churn definitions, training "
    "runs and scoring batches, with IDs and headline numbers.",
    "find_accounts": "The highest-risk accounts in the scoring batch, with rank and risk score.",
    "request_training_approval": "Ask the user to approve training this task. Creates a "
    "pending approval; nothing runs until they approve.",
    "search_playbooks": "Search the user's own customer-success playbooks. Returns cited "
    "passages (P1, P2...) to quote when recommending a play.",
}


class ResourceArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resource_id: UUID


class PlaybookSearchArguments(ResourceArguments):
    query: str = Field(min_length=2, max_length=300)


def _chat(
    request: AssistantRequest,
    session: Session,
    settings: Settings,
    tracer: Tracer,
    client: OpenAI | None = None,
) -> AssistantResponse:
    request_json = request.model_dump(mode="json")
    from hashlib import sha256

    digest = sha256(json.dumps(request_json, sort_keys=True).encode()).hexdigest()
    previous = session.exec(
        select(ConversationTurn).where(
            ConversationTurn.idempotency_key == str(request.idempotency_key)
        )
    ).first()
    if previous:
        if previous.request_sha256 != digest:
            raise WorkflowError("This assistant idempotency key was used for another message.", 409)
        return AssistantResponse.model_validate(previous.response)
    dataset = session.get(Dataset, request.dataset_id)
    if dataset is None:
        raise WorkflowError("Dataset not found.", 404)
    scope = {"inspect_dataset": dataset.id}
    required = {"inspect_dataset"}
    if request.task_id:
        task = session.get(Task, request.task_id)
        if task is None or task.dataset_id != dataset.id:
            raise WorkflowError("The selected task does not belong to this dataset.", 400)
        scope["read_task"] = task.id
        required.add("read_task")
    if request.run_id:
        run = read_training_run(request.run_id, settings.data_directory)
        if run.task.dataset_id != dataset.id or (
            request.task_id and run.task.id != request.task_id
        ):
            raise WorkflowError("The selected run is outside this dataset/task context.", 400)
        scope["read_run"] = request.run_id
        required.add("read_run")
    if request.job_id:
        job = get_job(session, request.job_id)
        belongs = False
        if job.payload.get("task_id"):
            task = session.get(Task, UUID(job.payload["task_id"]))
            belongs = bool(task and task.dataset_id == dataset.id)
        elif job.payload.get("run_id"):
            belongs = (
                read_training_run(
                    UUID(job.payload["run_id"]), settings.data_directory
                ).task.dataset_id
                == dataset.id
            )
        elif job.payload.get("score_id"):
            score = read_score(UUID(job.payload["score_id"]), settings.data_directory)
            belongs = (
                read_training_run(score.run_id, settings.data_directory).task.dataset_id
                == dataset.id
            )
        if not belongs:
            raise WorkflowError("The selected job is outside this dataset context.", 400)
        scope["read_job"] = request.job_id
        required.add("read_job")
    if request.score_id:
        score = read_score(request.score_id, settings.data_directory)
        run = read_training_run(score.run_id, settings.data_directory)
        if run.task.dataset_id != dataset.id or (request.run_id and score.run_id != request.run_id):
            raise WorkflowError("The selected score set is outside this run/dataset context.", 400)
        scope["read_scores"] = score.id
        required.add("read_scores")
    if request.analysis_id:
        from customer_intelligence.services.artifacts import read_json

        analysis = read_json(
            settings.data_directory / "analyses" / str(request.analysis_id) / "manifest.json"
        )
        if not isinstance(analysis, dict) or analysis.get("id") != str(request.analysis_id):
            raise WorkflowError("Invalid analysis identity.", 409)
        related = False
        if analysis.get("run_id"):
            related = (
                read_training_run(UUID(analysis["run_id"]), settings.data_directory).task.dataset_id
                == dataset.id
            )
        elif analysis.get("task_id"):
            related_task = session.get(Task, UUID(analysis["task_id"]))
            related = bool(related_task and related_task.dataset_id == dataset.id)
        if not related:
            raise WorkflowError("Analysis is outside this dataset context.", 400)
        scope["read_analysis"] = request.analysis_id
        required.add("read_analysis")
    if request.allow_training:
        if not request.task_id:
            raise WorkflowError("Training requires an explicitly selected confirmed task.")
        scope["propose_training"] = request.task_id
        scope["submit_training"] = request.task_id
        required.update({"propose_training", "submit_training"})
    action_models: dict[str, Any] = {}
    if request.allow_actions:
        if request.task_id:
            scope["analyze_schema_semantics"] = request.task_id
            action_models["analyze_schema_semantics"] = SchemaReviewRequest
        if request.run_id:
            scope["calculate_intervention_roi"] = request.run_id
            scope["challenge_business_rule"] = request.run_id
            scope["generate_executive_briefing"] = request.run_id
            action_models["calculate_intervention_roi"] = ROIRequest
            action_models["challenge_business_rule"] = RuleRequest
            action_models["generate_executive_briefing"] = BriefingRequest
        if request.score_id:
            scope["generate_retention_campaign"] = request.score_id
            action_models["generate_retention_campaign"] = CampaignRequest
    if request.workspace_tools:
        # Workspace-level tools carry fixed sentinel IDs; scope checks still apply.
        scope["read_workspace_memory"] = MEMORY_SCOPE
        scope["list_workspace_resources"] = CATALOG_SCOPE
        if request.score_id:
            scope["find_accounts"] = request.score_id
        if request.task_id and not request.allow_training:
            scope["request_training_approval"] = request.task_id
        if playbooks.list_playbooks(settings):
            scope["search_playbooks"] = PLAYBOOK_SCOPE
    conversation = (
        session.get(Conversation, request.conversation_id) if request.conversation_id else None
    )
    actor = session.info.get("actor")
    if conversation is not None and conversation.owner_id and conversation.owner_id != actor:
        conversation = None  # another member's conversation: indistinguishable from missing
    if request.conversation_id and (conversation is None or conversation.dataset_id != dataset.id):
        raise WorkflowError("Conversation not found in this dataset context.", 404)
    conversation_id = conversation.id if conversation else uuid4()
    turns = session.exec(
        select(ConversationTurn)
        .where(ConversationTurn.conversation_id == conversation_id)
        .order_by(col(ConversationTurn.created_at).desc())
        .limit(4)
    ).all()
    messages: list[dict] = [{"role": "system", "content": PROMPT.text}]
    for turn in reversed(turns):
        messages.extend(
            [
                {"role": "user", "content": turn.question},
                {"role": "assistant", "content": turn.response["answer"]},
            ]
        )
    messages.append(
        {
            "role": "user",
            "content": json.dumps(
                {
                    "question": request.question,
                    "allowed_resource_ids": {k: str(v) for k, v in scope.items()},
                    "required_tools": sorted(required),
                }
            ),
        }
    )
    tools: list[dict] = [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": TOOL_DESCRIPTIONS.get(name, name.replace("_", " "))
                + " Use the supplied resource ID.",
                "parameters": ResourceArguments.model_json_schema(),
            },
        }
        for name in scope
    ]
    for tool in tools:
        if tool["function"]["name"] == "search_playbooks":
            tool["function"]["parameters"] = PlaybookSearchArguments.model_json_schema()
    for tool in tools:
        name = tool["function"]["name"]
        if name in action_models:
            schema = action_models[name].model_json_schema()
            for field in (
                "idempotency_key",
                "provider_consent",
                "permitted_features",
                "approved_offer",
            ):
                schema.get("properties", {}).pop(field, None)
                if field in schema.get("required", []):
                    schema["required"].remove(field)
            tool["function"]["parameters"] = schema
            tool["function"]["description"] = (
                name.replace("_", " ")
                + "; use the scoped task_id/run_id/score_id. Never invent financial assumptions."
            )
    validated_actions: dict[str, Any] = {}
    queries: dict[str, str] = {}
    searches = 0
    events: list[ToolEvent] = []
    completed: set[str] = set()
    gateway = LLMGateway(settings, client)
    # With a separate fast model, it selects tools and the primary model writes the answer.
    tier: Literal["primary", "fast"] = "fast" if gateway.routes_by_tier else "primary"
    deadline = time.monotonic() + 180
    try:
        for number in range(1, 7):
            if tracer.model_calls + 1 > 8:
                raise WorkflowError("Assistant model call budget exceeded.", 502)
            response = gateway.complete(
                name="assistant",
                messages=messages,
                tools=tools,
                tool_choice="auto",
                max_tokens=2048,
                tier=tier,
                deadline=deadline,
                prompt_version=PROMPT.label,
            )
            if not response.choices or response.choices[0].finish_reason not in {
                "stop",
                "tool_calls",
            }:
                raise WorkflowError("Provider returned an incomplete response.", 502)
            message = response.choices[0].message
            calls = message.tool_calls or []
            if not calls:
                if required - completed or not message.content:
                    raise WorkflowError(
                        "Assistant answered before retrieving required evidence.", 502
                    )
                answer, model = message.content, response.model
                if tier == "fast" and tracer.model_calls + 1 <= 8:
                    final = gateway.complete(
                        name="assistant:synthesis",
                        messages=messages,
                        tools=tools,
                        tool_choice="none",
                        max_tokens=2048,
                        deadline=deadline,
                        prompt_version=PROMPT.label,
                    )
                    if final.choices and final.choices[0].message.content:
                        answer, model = final.choices[0].message.content, final.model
                answer, verification = _ground(
                    answer, messages, tools, request.question, gateway, tracer, deadline
                )
                result = AssistantResponse(
                    conversation_id=conversation_id,
                    turn_id=uuid4(),
                    model=model,
                    answer=answer,
                    events=events,
                    model_call_count=tracer.model_calls,
                    trace_id=tracer.id,
                    verification=verification,
                )
                tracer.trace.conversation_id = conversation_id
                tracer.trace.turn_id = result.turn_id
                if conversation is None:
                    session.add(
                        Conversation(id=conversation_id, dataset_id=dataset.id, owner_id=actor)
                    )
                session.add(
                    ConversationTurn(
                        id=result.turn_id,
                        conversation_id=conversation_id,
                        idempotency_key=str(request.idempotency_key),
                        request_sha256=digest,
                        question=request.question,
                        response=result.model_dump(mode="json"),
                    )
                )
                session.commit()
                return result
            generated_actions = sum(
                call.type == "function"
                and call.function.name in action_models
                and call.function.name != "calculate_intervention_roi"
                for call in calls
            )
            if (
                number == 6
                or len(events) + len(calls) > 8
                or tracer.model_calls + generated_actions > 8
            ):
                raise WorkflowError("Assistant tool/model call budget exceeded.", 502)
            serialized = []
            batch_names: set[str] = set()
            # call id -> message returned to the model instead of executing the call
            rejected: dict[str, str] = {}
            repeated: set[str] = set()
            # Validate the entire batch before permitting any mutation.
            for call in calls:
                if call.type != "function" or call.function.name not in scope:
                    raise WorkflowError("Assistant requested an unsupported tool.", 502)
                try:
                    name = call.function.name
                    if name in action_models:
                        payload = json.loads(call.function.arguments)
                        if not isinstance(payload, dict) or set(payload) & {
                            "provider_consent",
                            "idempotency_key",
                            "permitted_features",
                            "approved_offer",
                        }:
                            raise ValueError("Server-owned action fields.")
                        if name != "calculate_intervention_roi":
                            payload["provider_consent"] = True
                            payload["idempotency_key"] = uuid5(
                                NAMESPACE_URL, str(request.idempotency_key) + name
                            )
                        if name == "generate_retention_campaign":
                            payload["permitted_features"] = request.campaign_features
                            payload["approved_offer"] = request.approved_offer
                        try:
                            action = action_models[name].model_validate(payload)
                        except ValidationError as exc:
                            # Unknown fields are a contract violation; bad values are fixable.
                            if any(e["type"] == "extra_forbidden" for e in exc.errors()):
                                raise ValueError("Unexpected action fields.") from None
                            raise RecoverableToolError(describe_validation_error(exc)) from None
                        resource = getattr(
                            action,
                            "task_id",
                            getattr(action, "run_id", getattr(action, "score_id", None)),
                        )
                        if (
                            name == "calculate_intervention_roi"
                            and action.score_id
                            and action.score_id != request.score_id
                        ):
                            raise ValueError("Unscoped scoring batch.")
                        validated_actions[name] = action
                    elif name == "search_playbooks":
                        try:
                            search = PlaybookSearchArguments.model_validate_json(
                                call.function.arguments
                            )
                        except ValidationError as exc:
                            if any(e["type"] == "extra_forbidden" for e in exc.errors()):
                                raise ValueError("Unexpected search fields.") from None
                            raise RecoverableToolError(describe_validation_error(exc)) from None
                        queries[call.id] = search.query
                        resource = search.resource_id
                    else:
                        resource = ResourceArguments.model_validate_json(
                            call.function.arguments
                        ).resource_id
                except RecoverableToolError as exc:
                    rejected[call.id] = str(exc)
                    resource = scope[call.function.name]
                except (ValueError, TypeError):
                    raise WorkflowError("Assistant returned invalid tool arguments.", 502) from None
                if resource != scope[call.function.name]:
                    raise WorkflowError("Assistant tool scope or repetition violation.", 502)
                if call.function.name == "search_playbooks":
                    # Different queries are new evidence; the per-turn count stays bounded.
                    searches += 1
                    if searches > 3:
                        rejected[call.id] = "At most three playbook searches per answer"
                elif call.function.name in completed:
                    repeated.add(call.id)  # answered from the earlier result, not re-executed
                if call.function.name in batch_names:
                    raise WorkflowError("Duplicate tools in one batch are not permitted.", 502)
                batch_names.add(call.function.name)
                serialized.append(call.model_dump(mode="json"))
            messages.append(
                {"role": "assistant", "content": message.content, "tool_calls": serialized}
            )
            for call in calls:
                if call.type != "function":
                    raise WorkflowError("Only function tools are supported.", 502)
                name = call.function.name
                if call.id in rejected or call.id in repeated:
                    note = (
                        {
                            "error": "Invalid arguments: "
                            + rejected[call.id]
                            + ". Correct them and call again, or answer without this tool."
                        }
                        if call.id in rejected
                        else {"note": "Already retrieved earlier in this turn; reuse that result."}
                    )
                    with tracer.tool(name, {"rejected": call.id in rejected}) as outcome:
                        outcome["error_code"] = (
                            "invalid_arguments" if call.id in rejected else "repeated_call"
                        )
                    messages.append(
                        {"role": "tool", "tool_call_id": call.id, "content": json.dumps(note)}
                    )
                    continue
                arguments: dict[str, Any] = (
                    validated_actions[name].model_dump(mode="json")
                    if name in action_models
                    else {"resource_id": str(scope[name])}
                )
                if name == "search_playbooks":
                    arguments["query"] = queries[call.id]
                with tracer.tool(name, arguments) as outcome:
                    event_id = str(scope[name])
                    if name in action_models:
                        operations: dict[str, Any] = {
                            "analyze_schema_semantics": retention.analyze_schema_semantics,
                            "generate_retention_campaign": retention.generate_retention_campaign,
                            "challenge_business_rule": retention.challenge_business_rule,
                            "generate_executive_briefing": retention.executive_briefing,
                        }
                        if name == "calculate_intervention_roi":
                            content = retention.calculate_intervention_roi(
                                validated_actions[name], session, settings
                            )
                        else:
                            # Model calls made inside the action join this trace and its budget.
                            # Share the gateway's client: one connection pool and transport.
                            try:
                                content = operations[name](
                                    validated_actions[name], session, settings, gateway.client
                                )
                            except WorkflowError as exc:
                                # The action refused (e.g. its result failed validation); the
                                # model hears why and may continue without it.
                                outcome["error_code"] = exc.code
                                messages.append(
                                    {
                                        "role": "tool",
                                        "tool_call_id": call.id,
                                        "content": json.dumps(
                                            {"error": str(exc), "code": exc.code}
                                        ),
                                    }
                                )
                                continue
                        if "id" in content:
                            event_id = content["id"]
                    elif name == "inspect_dataset":
                        from customer_intelligence.services.privacy import ai_profile

                        content = ai_profile(session, profile_dataset(dataset, settings))
                    elif name == "read_task":
                        task = session.get(Task, scope[name])
                        content = TaskResponse.model_validate(task).model_dump(mode="json")
                    elif name == "read_run":
                        selected_run = read_training_run(scope[name], settings.data_directory)
                        content = {
                            "base_model_comparison": selected_run.report.model_dump(mode="json"),
                            "calibration": selected_run.calibration,
                        }
                        test_path = (
                            settings.data_directory / "runs" / str(scope[name]) / "evaluation.json"
                        )
                        if test_path.exists():
                            from customer_intelligence.services.artifacts import read_json

                            content["final_evaluation"] = read_json(test_path)
                    elif name == "read_analysis":
                        from customer_intelligence.services.artifacts import read_json

                        analysis_content = read_json(
                            settings.data_directory
                            / "analyses"
                            / str(scope[name])
                            / "manifest.json"
                        )
                        if not isinstance(analysis_content, dict):
                            raise WorkflowError("Invalid analysis artifact.", 409)
                        content = analysis_content
                    elif name == "read_job":
                        content = JobResponse.model_validate(
                            get_job(session, scope[name])
                        ).model_dump(mode="json")
                    elif name == "read_scores":
                        content = read_score(scope[name], settings.data_directory).model_dump(
                            mode="json"
                        )
                    elif name == "read_workspace_memory":
                        content = MemoryResponse.model_validate(
                            workspace.read_memory(session)
                        ).model_dump(mode="json")
                        content["note"] = (
                            "Assumptions the user entered earlier. Confirm before relying on them."
                        )
                    elif name == "list_workspace_resources":
                        content = workspace.workspace_resources(session, settings.data_directory)
                    elif name == "find_accounts":
                        content = workspace.top_accounts(scope[name], settings.data_directory)
                    elif name == "request_training_approval":
                        action = workspace.propose_training(session, scope[name], tracer.id)
                        content = {
                            "pending_action_id": str(action.id),
                            "status": action.status,
                            "summary": action.summary,
                            "note": "Nothing runs until the user approves it in the Inbox.",
                        }
                        event_id = str(action.id)
                    elif name == "search_playbooks":
                        content = playbooks.search(settings, queries[call.id])
                        if content["results"]:
                            event_id = content["results"][0]["playbook_id"]
                    elif name == "propose_training":
                        content = training_plan(scope[name], session)
                    elif name == "submit_training":
                        if "propose_training" not in completed:
                            raise WorkflowError(
                                "The experiment plan must be retrieved before submission.", 502
                            )
                        key = uuid5(NAMESPACE_URL, str(request.idempotency_key) + ":train")
                        job = submit_job(
                            session,
                            "train",
                            {
                                "task_id": str(scope[name]),
                                "search_trials": 0,
                                "threshold": 0.5,
                                "idempotency_key": str(key),
                            },
                            key,
                        )
                        content = JobResponse.model_validate(job).model_dump(mode="json")
                        event_id = str(job.id)
                    else:
                        raise WorkflowError("Unsupported tool.", 502)
                    encoded = json.dumps(content, allow_nan=False)
                    if len(encoded) > 50_000:
                        raise WorkflowError(
                            "Tool output exceeds the assistant context budget.", 502
                        )
                    messages.append({"role": "tool", "tool_call_id": call.id, "content": encoded})
                    completed.add(name)
                    evidence = {
                        "inspect_dataset": f"/api/v1/datasets/{event_id}/profile",
                        "read_task": f"/api/v1/tasks/{event_id}",
                        "read_run": f"/api/v1/runs/{event_id}",
                        "read_job": f"/api/v1/jobs/{event_id}",
                        "read_scores": f"/api/v1/scores/{event_id}",
                        "read_analysis": f"/api/v1/analyses/{event_id}",
                        "propose_training": f"/api/v1/tasks/{event_id}/plan",
                        "submit_training": f"/api/v1/jobs/{event_id}",
                        "read_workspace_memory": "/api/v1/memory",
                        "list_workspace_resources": "/api/v1/runs",
                        "find_accounts": f"/api/v1/scores/{event_id}/customers",
                        "request_training_approval": f"/api/v1/actions/{event_id}",
                        "search_playbooks": f"/api/v1/playbooks/{event_id}"
                        if event_id != str(PLAYBOOK_SCOPE)
                        else "/api/v1/playbooks",
                    }
                    if name in action_models:
                        evidence[name] = (
                            f"/api/v1/analyses/{event_id}"
                            if name != "calculate_intervention_roi"
                            else f"/api/v1/runs/{event_id}"
                        )
                    outcome["evidence_path"] = evidence[name]
                events.append(
                    ToolEvent(tool=name, resource_id=event_id, evidence_path=evidence[name])
                )
    finally:
        gateway.close()
    raise WorkflowError("Assistant ended without an answer.", 502)


def _ground(
    answer: str,
    messages: list[dict],
    tools: list[dict],
    question: str,
    gateway: LLMGateway,
    tracer: Tracer,
    deadline: float,
) -> tuple[str, dict[str, Any]]:
    """Check numbers against tool outputs and wording for causal claims about churn.

    One revision is allowed; anything left is reported to the user. Code never edits the answer.
    The same rules gate investigation reports (agent/verification.py).
    """
    sources: list[Any] = [question]
    for message in messages:
        if message.get("role") == "tool":
            sources.append(json.loads(message["content"]))

    def check(text: str) -> tuple[list[str], list[str], list[str]]:
        checked, missing = ungrounded_numbers(text, sources)
        return checked, missing, causal_claims(text)

    checked, missing, causal = check(answer)
    revised = False
    if (missing or causal) and tracer.model_calls + 1 <= 8 and deadline - time.monotonic() > 15:
        problems = []
        if missing:
            problems.append(
                "these figures are not stated in any tool output: "
                + ", ".join(missing)
                + " (leave them out or use the exact values the tools stated)"
            )
        if causal:
            problems.append(
                "it uses causal wording ("
                + ", ".join(causal)
                + ") although the evidence only shows association (describe it as an association)"
            )
        response = gateway.complete(
            name="assistant:ground",
            messages=[
                *messages,
                {"role": "assistant", "content": answer},
                {
                    "role": "user",
                    "content": "Rewrite your previous answer for the user: "
                    + "; ".join(problems)
                    + ". Do not add new calculations and do not mention this revision.",
                },
            ],
            tools=tools,
            tool_choice="none",
            max_tokens=2048,
            deadline=deadline,
            prompt_version=PROMPT.label,
        )
        content = response.choices[0].message.content if response.choices else None
        if content:
            new_checked, new_missing, new_causal = check(content)
            if len(new_missing) + len(new_causal) < len(missing) + len(causal):
                answer, checked, missing, causal = content, new_checked, new_missing, new_causal
                revised = True
    return answer, {
        "grounded": not missing and not causal,
        "numbers_checked": len(checked),
        "ungrounded": missing,
        "causal_claims": causal,
        "revised": revised,
    }


def chat(
    request: AssistantRequest,
    session: Session,
    settings: Settings,
    client: OpenAI | None = None,
    listener: Listener | None = None,
) -> AssistantResponse:
    from datetime import UTC, datetime

    from sqlalchemy import text

    from customer_intelligence.models.conversation import AssistantLease

    session.rollback()
    session.exec(text("BEGIN IMMEDIATE"))  # type: ignore[call-overload]
    lease = session.get(AssistantLease, str(request.idempotency_key))
    if lease and (datetime.now(UTC) - lease.created_at.replace(tzinfo=UTC)).total_seconds() < 300:
        session.rollback()
        raise WorkflowError("This assistant message is already being processed.", 409)
    if lease:
        session.delete(lease)
        session.flush()
    lease = AssistantLease(
        idempotency_key=str(request.idempotency_key), dataset_id=request.dataset_id
    )
    owner_id = lease.owner_id
    session.add(lease)
    session.commit()
    try:
        with traced(
            session,
            "assistant",
            dataset_id=request.dataset_id,
            conversation_id=request.conversation_id,
            prompt_version=PROMPT.label,
            listener=listener,
        ) as tracer:
            return _chat(request, session, settings, tracer, client)
    finally:
        session.rollback()
        current = session.get(AssistantLease, str(request.idempotency_key))
        if current and current.owner_id == owner_id:
            session.delete(current)
            session.commit()
