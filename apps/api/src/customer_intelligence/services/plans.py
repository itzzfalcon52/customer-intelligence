from uuid import UUID

from sqlmodel import Session

from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.ml.evaluation import candidate_specs
from customer_intelligence.models.task import Task
from customer_intelligence.schemas.task import TaskResponse


def training_plan(task_id: UUID, session: Session) -> dict:
    task = session.get(Task, task_id)
    if task is None:
        raise WorkflowError("Task not found.", 404)
    return {
        "task": TaskResponse.model_validate(task).model_dump(mode="json"),
        "candidates": [
            {"model": name, "candidate_id": identifier, "parameters": parameters}
            for name, identifier, parameters in candidate_specs(task.random_seed)
        ],
        "selection_metric": "average_precision",
        "fit_partition": "train",
        "evaluation_partition": "validation",
        "test_reserved": True,
        "max_extra_search_trials": 8,
        "limitations": [
            "Business label meaning and pre-outcome availability remain user assertions."
        ],
    }
