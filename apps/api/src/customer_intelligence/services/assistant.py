import json
from hashlib import sha256
from uuid import UUID

from sqlmodel import Session

from customer_intelligence.agent.inspection import AgentInspectionError, run_inspection
from customer_intelligence.agent.llm import LLMGateway
from customer_intelligence.agent.prompts import load_prompt
from customer_intelligence.agent.tracing import traced
from customer_intelligence.core.config import Settings
from customer_intelligence.models.dataset import Dataset
from customer_intelligence.models.task import Task
from customer_intelligence.schemas.inspection import (
    InspectDatasetArguments,
    InspectionRequest,
    InspectionResult,
    ReadTaskArguments,
)
from customer_intelligence.schemas.task import TaskResponse
from customer_intelligence.services.profiling import profile_dataset


class ProviderConfigurationError(ValueError):
    pass


def inspect_with_agent(
    request: InspectionRequest,
    settings: Settings,
    session: Session,
) -> InspectionResult:
    key = settings.nebius_api_key
    base_url = settings.nebius_base_url
    model = settings.nebius_model

    if key is None or not key.get_secret_value() or base_url is None or model is None:
        raise ProviderConfigurationError(
            "Configure NEBIUS_API_KEY, NEBIUS_BASE_URL, and NEBIUS_MODEL in apps/api/.env."
        )

    def execute(name: str, payload: str, dataset_id: UUID, task_id: UUID | None) -> str:
        if name == "inspect_dataset":
            arguments = InspectDatasetArguments.model_validate_json(payload)
            if arguments.dataset_id != dataset_id:
                raise AgentInspectionError("Dataset is outside request scope.")
            dataset = session.get(Dataset, dataset_id)
            if dataset is None:
                raise AgentInspectionError("Dataset not found.")
            from customer_intelligence.services.privacy import ai_profile

            content = ai_profile(session, profile_dataset(dataset, settings))
        else:
            arguments_task = ReadTaskArguments.model_validate_json(payload)
            if name != "read_task" or arguments_task.task_id != task_id:
                raise AgentInspectionError("Task is outside request scope.")
            task = session.get(Task, task_id)
            if task is None or task.dataset_id != dataset_id:
                raise AgentInspectionError("Task does not belong to this dataset.")
            content = {
                "source": "saved_user_configuration",
                "task": TaskResponse.model_validate(task).model_dump(mode="json"),
            }
        return json.dumps(content, allow_nan=False)

    prompt = load_prompt("inspection")
    with (
        traced(
            session, "inspection", dataset_id=request.dataset_id, prompt_version=prompt.label
        ) as tracer,
        LLMGateway(settings) as gateway,
    ):

        def traced_execute(name: str, payload: str, dataset_id: UUID, task_id: UUID | None) -> str:
            with tracer.tool(name, {"arguments_sha256": sha256(payload.encode()).hexdigest()}):
                return execute(name, payload, dataset_id, task_id)

        return run_inspection(
            client=gateway.client,
            model=gateway.model_for("primary"),
            dataset_id=request.dataset_id,
            question=request.question,
            task_id=request.task_id,
            tool_executor=traced_execute,
            complete=lambda **options: gateway.complete(
                name="inspection", prompt_version=prompt.label, **options
            ),
        )
