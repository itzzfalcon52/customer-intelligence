import json
from collections.abc import Callable
from uuid import UUID

from openai import APIError, OpenAI
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionFunctionToolParam,
    ChatCompletionMessageParam,
    ChatCompletionMessageToolCallParam,
)
from pydantic import ValidationError
from sqlmodel import Session

from customer_intelligence.agent.prompts import load_prompt
from customer_intelligence.core.config import get_settings
from customer_intelligence.core.database import engine
from customer_intelligence.models.dataset import Dataset
from customer_intelligence.models.task import Task
from customer_intelligence.schemas.inspection import (
    InspectDatasetArguments,
    InspectionResult,
    ReadTaskArguments,
)
from customer_intelligence.schemas.task import TaskResponse
from customer_intelligence.services.profiling import DatasetProfileError, profile_dataset

MAX_MODEL_CALLS = 3
MAX_TOOL_CALLS = 2
MAX_TOOL_OUTPUT_CHARACTERS = 50_000

SYSTEM_PROMPT = load_prompt("inspection").text


class AgentInspectionError(ValueError):
    pass


def inspect_dataset(dataset_id: UUID) -> str:
    with Session(engine) as session:
        dataset = session.get(Dataset, dataset_id)
        if dataset is None:
            raise AgentInspectionError("Dataset not found.")

        try:
            profile = profile_dataset(dataset, get_settings())
        except DatasetProfileError as exc:
            raise AgentInspectionError("The stored dataset could not be profiled.") from exc

        from customer_intelligence.services.privacy import ai_profile

        # Aggregate metadata only, under the workspace privacy policy.
        payload = ai_profile(session, profile)
    content = json.dumps(payload, allow_nan=False)

    if len(content) > MAX_TOOL_OUTPUT_CHARACTERS:
        raise AgentInspectionError("The profile exceeds this prototype's tool output limit.")

    return content


def read_task(task_id: UUID, dataset_id: UUID) -> str:
    with Session(engine) as session:
        task = session.get(Task, task_id)
        if task is None:
            raise AgentInspectionError("Task not found.")
        if task.dataset_id != dataset_id:
            raise AgentInspectionError("The task does not belong to this dataset.")

        configuration = TaskResponse.model_validate(task).model_dump(mode="json")

    payload = {
        "source": "saved_user_configuration",
        "task": configuration,
        "limitations": [
            "Feature availability is a recorded user assertion, not independent proof.",
            "This tool does not rerun target checks, train models, or evaluate performance.",
        ],
    }
    content = json.dumps(payload, allow_nan=False)

    if len(content) > MAX_TOOL_OUTPUT_CHARACTERS:
        raise AgentInspectionError("The task exceeds this prototype's tool output limit.")

    return content


def execute_tool(
    name: str,
    arguments_json: str,
    dataset_id: UUID,
    task_id: UUID | None,
) -> str:
    try:
        if name == "inspect_dataset":
            arguments = InspectDatasetArguments.model_validate_json(arguments_json)

            if arguments.dataset_id != dataset_id:
                raise AgentInspectionError("The requested dataset is outside this request's scope.")

            return inspect_dataset(arguments.dataset_id)

        if name == "read_task" and task_id is not None:
            task_arguments = ReadTaskArguments.model_validate_json(arguments_json)

            if task_arguments.task_id != task_id:
                raise AgentInspectionError("The requested task is outside this request's scope.")

            return read_task(task_arguments.task_id, dataset_id)

    except ValidationError:
        raise AgentInspectionError("The model returned invalid tool arguments.") from None

    raise AgentInspectionError("The model requested an unsupported tool.")


def run_inspection(
    client: OpenAI,
    model: str,
    dataset_id: UUID,
    question: str,
    task_id: UUID | None = None,
    tool_executor: Callable[[str, str, UUID, UUID | None], str] | None = None,
    complete: Callable[..., ChatCompletion] | None = None,
) -> InspectionResult:
    """Run the read-only inspection loop.

    `complete` routes calls through the LLM gateway (retries, tracing); without it the plain
    client is used, as in the standalone check_agent.py learning script.
    """
    if not question.strip() or len(question) > 2000:
        raise AgentInspectionError("Provide a question between 1 and 2000 characters.")

    tools: list[ChatCompletionFunctionToolParam] = [
        {
            "type": "function",
            "function": {
                "name": "inspect_dataset",
                "description": "Read a dataset profile with computed aggregate statistics.",
                "parameters": InspectDatasetArguments.model_json_schema(),
            },
        }
    ]
    required_tools = {"inspect_dataset"}

    if task_id is not None:
        # Reject missing tasks or dataset mismatches before spending provider credits.
        if tool_executor:
            tool_executor("read_task", json.dumps({"task_id": str(task_id)}), dataset_id, task_id)
        else:
            read_task(task_id, dataset_id)

        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "read_task",
                    "description": "Read the user's saved target, labels, and feature choices.",
                    "parameters": ReadTaskArguments.model_json_schema(),
                },
            }
        )
        required_tools.add("read_task")

    context = f"Dataset ID: {dataset_id}\n"
    if task_id is not None:
        context += f"Saved task ID: {task_id}\n"
    context += f"Required tools before answering: {', '.join(sorted(required_tools))}\n"
    context += f"Question: {question}"

    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": context},
    ]
    completed_tools: list[str] = []

    for call_number in range(1, MAX_MODEL_CALLS + 1):
        try:
            if complete:
                response = complete(
                    messages=messages, tools=tools, tool_choice="auto", max_tokens=2048
                )
            else:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    max_tokens=2048,
                )
        except APIError as exc:
            status = getattr(exc, "status_code", None)
            raise AgentInspectionError(
                f"Nebius request failed: {type(exc).__name__}, HTTP status: {status}"
            ) from None

        if not response.choices:
            raise AgentInspectionError("Nebius returned no response choices.")

        choice = response.choices[0]
        message = choice.message

        if choice.finish_reason not in {"stop", "tool_calls"}:
            raise AgentInspectionError(
                f"The model response was incomplete: {choice.finish_reason}."
            )

        calls = message.tool_calls or []

        if not calls:
            missing = required_tools - set(completed_tools)
            if missing:
                raise AgentInspectionError(
                    f"The model answered before completing: {', '.join(sorted(missing))}."
                )

            if not message.content or not message.content.strip():
                raise AgentInspectionError("The model returned no visible final answer.")

            return InspectionResult(
                dataset_id=dataset_id,
                task_id=task_id,
                model=response.model,
                answer=message.content,
                completed_tools=completed_tools,
                model_call_count=call_number,
            )

        if call_number == MAX_MODEL_CALLS:
            raise AgentInspectionError("Model call limit reached without a final answer.")

        if len(completed_tools) + len(calls) > MAX_TOOL_CALLS:
            raise AgentInspectionError("Tool call limit reached.")

        serialized_calls: list[ChatCompletionMessageToolCallParam] = []

        for call in calls:
            if call.type != "function" or call.function.name not in required_tools:
                raise AgentInspectionError("The model requested an unsupported tool.")

            serialized_calls.append(
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                    },
                }
            )

        messages.append(
            {"role": "assistant", "content": message.content, "tool_calls": serialized_calls}
        )

        for call in calls:
            if call.type != "function":
                raise AgentInspectionError("Only function tools are supported.")

            if call.function.name in completed_tools:
                raise AgentInspectionError("The model requested the same tool twice.")

            content = (tool_executor or execute_tool)(
                call.function.name,
                call.function.arguments,
                dataset_id,
                task_id,
            )
            messages.append({"role": "tool", "tool_call_id": call.id, "content": content})
            completed_tools.append(call.function.name)

    raise AgentInspectionError("Inspection ended without a final answer.")
