import argparse
import os
import threading
import time
from uuid import UUID

from sqlmodel import Session

from customer_intelligence.core.config import get_settings
from customer_intelligence.core.database import engine
from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.schemas.workflow import DiagnosticsRequest, ScoreRequest
from customer_intelligence.services.analysis import (
    customer_explanation,
    diagnostics,
    final_evaluation,
    leakage_demonstration,
)
from customer_intelligence.services.jobs import finish_job, get_job, set_stage
from customer_intelligence.services.scoring import score_dataset
from customer_intelligence.services.training import train_task


def watch_parent(parent_pid: int) -> None:
    while True:
        time.sleep(1)
        if os.getppid() != parent_pid:
            os._exit(1)


def execute(job_id: UUID) -> None:
    settings = get_settings()
    with Session(engine) as session:
        job = get_job(session, job_id)
        if job.state != "running" or job.cancel_requested:
            return
        kind, payload = job.kind, dict(job.payload)
        result: UUID | None = None
        try:
            set_stage(session, job_id, kind)
            if kind == "train":
                destination = train_task(
                    session,
                    settings,
                    UUID(payload["task_id"]),
                    payload["search_trials"],
                    payload["threshold"],
                    lambda stage: set_stage(session, job_id, stage),
                )
                result = UUID(destination.name)
            elif kind == "calibrate":
                from customer_intelligence.services.calibration import calibrate_run

                result = calibrate_run(session, settings, UUID(payload["run_id"]))
            elif kind == "evaluate":
                result = final_evaluation(session, settings, UUID(payload["run_id"]))
            elif kind == "score":
                result = score_dataset(session, settings, ScoreRequest.model_validate(payload))
            elif kind == "diagnostics":
                result = diagnostics(session, settings, DiagnosticsRequest.model_validate(payload))
            elif kind == "explain":
                result = customer_explanation(
                    session,
                    settings,
                    UUID(payload["score_id"]),
                    payload["row_reference"],
                    UUID(payload["idempotency_key"]),
                )
            elif kind == "leakage":
                result = leakage_demonstration(
                    session,
                    settings,
                    UUID(payload["task_id"]),
                    UUID(payload["idempotency_key"]),
                )
            else:
                raise WorkflowError("Unsupported job operation.")
            finish_job(session, job_id, result)
            # A cancellation received during artifact publication must not retain new outputs.
            if (
                get_job(session, job_id).state == "cancelled"
                and result
                and kind in {"train", "calibrate", "score", "explain", "leakage", "diagnostics"}
            ):
                import shutil

                folder = (
                    "runs"
                    if kind in {"train", "calibrate"}
                    else "scores"
                    if kind == "score"
                    else "analyses"
                )
                shutil.rmtree(settings.data_directory / folder / str(result), ignore_errors=True)
        except Exception as exc:
            session.rollback()
            error = (
                str(exc)
                if isinstance(exc, WorkflowError)
                else f"{kind} failed ({type(exc).__name__}). Review data/schema compatibility."
            )
            finish_job(session, job_id, None, error)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("job_id", type=UUID)
    parser.add_argument("--parent-pid", required=True, type=int)
    args = parser.parse_args()
    threading.Thread(target=watch_parent, args=(args.parent_pid,), daemon=True).start()
    execute(args.job_id)


if __name__ == "__main__":
    main()
