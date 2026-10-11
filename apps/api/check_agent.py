import argparse
import os
from uuid import UUID

from dotenv import load_dotenv
from openai import OpenAI
from sqlmodel import Session

from customer_intelligence.agent.inspection import AgentInspectionError, run_inspection
from customer_intelligence.core.config import API_DIRECTORY
from customer_intelligence.core.database import engine
from customer_intelligence.models.dataset import Dataset


def main(dataset_id: UUID, question: str, task_id: UUID | None) -> None:
    load_dotenv(API_DIRECTORY / ".env")

    required = ["NEBIUS_API_KEY", "NEBIUS_BASE_URL", "NEBIUS_MODEL"]
    missing = [name for name in required if not os.getenv(name)]

    if missing:
        raise SystemExit(f"Missing configuration: {', '.join(missing)}")

    with Session(engine) as session:
        if session.get(Dataset, dataset_id) is None:
            raise SystemExit("Dataset not found. Use an uploaded dataset ID.")

    try:
        with OpenAI(
            api_key=os.environ["NEBIUS_API_KEY"],
            base_url=os.environ["NEBIUS_BASE_URL"],
            timeout=20.0,
            max_retries=0,
        ) as client:
            result = run_inspection(
                client=client,
                model=os.environ["NEBIUS_MODEL"],
                dataset_id=dataset_id,
                question=question,
                task_id=task_id,
            )
    except AgentInspectionError as exc:
        raise SystemExit(str(exc)) from None

    print("Model:", result.model)
    print("Task:", result.task_id or "(not supplied)")
    print("Completed tools:", ", ".join(result.completed_tools))
    print("Model calls:", result.model_call_count)
    print("\nAnswer:\n", result.answer)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset_id", type=UUID)
    parser.add_argument("--task-id", type=UUID, default=None)
    parser.add_argument(
        "--question",
        default=(
            "Inspect this dataset and read the saved task if provided. Summarize "
            "recorded choices, missing values, and remaining limitations before training."
        ),
    )
    arguments = parser.parse_args()
    main(arguments.dataset_id, arguments.question, arguments.task_id)