import numpy as np
from openai import OpenAI
from sqlmodel import Session

from customer_intelligence.agent.graph.investigator import Investigator
from customer_intelligence.agent.llm import LLMGateway
from customer_intelligence.agent.prompts import load_prompt
from customer_intelligence.agent.tracing import Listener, traced
from customer_intelligence.core.config import Settings
from customer_intelligence.schemas.investigation import InvestigationRequest
from customer_intelligence.services.analysis import run_frame
from customer_intelligence.services.retention import action_lock, save_action, saved_action
from customer_intelligence.services.runs import read_training_run


def run_investigation(
    request: InvestigationRequest,
    session: Session,
    settings: Settings,
    client: OpenAI | None = None,
    listener: Listener | None = None,
) -> dict:
    """Investigate a churn question over development rows and save a verified report."""
    uid, digest, previous = saved_action(settings, "investigation", request)
    if previous:
        return previous
    run = read_training_run(request.run_id, settings.data_directory)
    with action_lock(session, uid, run.task.dataset_id):
        frame = run_frame(session, settings, run)
        rows = run.split.row_assignments["train"] + run.split.row_assignments["validation"]
        development = frame.iloc[rows].reset_index(drop=True)
        labels = np.array(
            [run.task.label_mapping[str(v)] for v in development[run.task.target_column]],
            dtype=int,
        )
        with (
            traced(
                session,
                "investigation",
                dataset_id=run.task.dataset_id,
                prompt_version=load_prompt("investigator_plan").label,
                listener=listener,
            ) as tracer,
            LLMGateway(settings, client) as gateway,
        ):
            from customer_intelligence.services.privacy import withheld

            investigator = Investigator(
                run=run, frame=development, labels=labels, gateway=gateway, tracer=tracer
            )
            hidden = withheld(session, investigator.features)
            investigator.features = [f for f in investigator.features if f not in hidden]
            state = investigator.invoke(request.question)
            trace_id = tracer.id
            model_calls = tracer.model_calls
        return save_action(
            settings,
            "investigation",
            uid,
            digest,
            {
                "run_id": str(run.run_id),
                "task_id": str(run.task.id),
                "question": request.question,
                "partition": "development rows (train + validation); final test excluded",
                "plan": state["plan"],
                "evidence": state["evidence"],
                "draft": state["report"],
                "verification": state["verification"],
                "report": state["result"],
                "trace_id": str(trace_id),
                "model_calls": model_calls,
                "warning": (
                    "Associations in historical data, not causes. Numbers come from deterministic "
                    "analyses; statements that failed verification are withheld."
                ),
            },
        )
