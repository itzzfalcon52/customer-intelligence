import json
from uuid import UUID

from openai import OpenAI
from sqlmodel import Session

from customer_intelligence.agent.inspection import AgentInspectionError, run_inspection
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
            content = profile_dataset(dataset, settings).model_dump(
                mode="json", exclude={"preview", "original_filename"}
            )
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

    with OpenAI(
        api_key=key.get_secret_value(),
        base_url=str(base_url),
        timeout=20.0,
        max_retries=0,
    ) as client:
        return run_inspection(
            client=client,
            model=model,
            dataset_id=request.dataset_id,
            question=request.question,
            task_id=request.task_id,
            tool_executor=execute,
        )
