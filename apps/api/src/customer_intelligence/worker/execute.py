import argparse
import os
import threading
import time
from uuid import UUID

from sqlmodel import Session

from customer_intelligence.agent.tracing import traced
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
                    cv_folds=payload.get("cv_folds", 0),
                    threshold_policy=payload.get("threshold_policy", "fixed"),
                    minimum_recall=payload.get("minimum_recall", 0.5),
                )
                result = UUID(destination.name)
                if payload.get("generate_briefing"):
                    import json
                    from uuid import NAMESPACE_URL, uuid5

                    from customer_intelligence.schemas.retention import BriefingRequest
                    from customer_intelligence.services.retention import executive_briefing

                    status: dict = {"state": "pending"}
                    try:
                        set_stage(session, job_id, "executive_briefing")
                        with traced(session, "job.executive_briefing"):
                            briefing = executive_briefing(
                                BriefingRequest(
                                    run_id=result,
                                    provider_consent=True,
                                    idempotency_key=uuid5(NAMESPACE_URL, f"{job_id}:briefing"),
                                ),
                                session,
                                settings,
                            )
                        status = {
                            "state": "succeeded",
                            "analysis_id": briefing["id"],
                            "paragraphs": briefing["paragraphs"],
                            "source": "nebius",
                        }
                    except Exception as exc:
                        session.rollback()
                        status = {
                            "state": "failed",
                            "message": str(exc)
                            if isinstance(exc, WorkflowError)
                            else "AI briefing failed. The trained model is saved and ready.",
                        }
                    temporary = destination / ".briefing-status.tmp"
                    temporary.write_text(json.dumps(status), encoding="utf-8")
                    temporary.replace(destination / "briefing-status.json")
            elif kind == "calibrate":
                from customer_intelligence.services.calibration import calibrate_run

                result = calibrate_run(session, settings, UUID(payload["run_id"]))
            elif kind == "evaluate":
                result = final_evaluation(session, settings, UUID(payload["run_id"]))
            elif kind == "score":
                score_request = ScoreRequest.model_validate(payload)
                result = score_dataset(session, settings, score_request)
                if score_request.outreach:
                    import json
                    from uuid import NAMESPACE_URL, uuid5

                    from customer_intelligence.schemas.retention import CampaignRequest
                    from customer_intelligence.services.retention import generate_retention_campaign

                    try:
                        set_stage(session, job_id, "retention_drafts")
                        with traced(session, "job.campaign"):
                            campaign = generate_retention_campaign(
                                CampaignRequest(
                                    score_id=result,
                                    idempotency_key=uuid5(NAMESPACE_URL, f"{job_id}:campaign"),
                                    **score_request.outreach.model_dump(),
                                ),
                                session,
                                settings,
                            )
                        campaign_status = {"state": "succeeded", "analysis_id": campaign["id"]}
                    except Exception as exc:
                        session.rollback()
                        campaign_status = {
                            "state": "failed",
                            "message": str(exc)
                            if isinstance(exc, WorkflowError)
                            else "AI drafting failed. Customer scores are saved.",
                        }
                    score_folder = settings.data_directory / "scores" / str(result)
                    temporary = score_folder / ".campaign-status.tmp"
                    temporary.write_text(json.dumps(campaign_status), encoding="utf-8")
                    temporary.replace(score_folder / "campaign-status.json")
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
            elif kind == "cycle":
                from customer_intelligence.services.autonomy import run_cycle

                session.info["settings"] = settings
                result = run_cycle(session, settings, job_id)
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
            if kind == "cycle":
                from customer_intelligence.services.autonomy import record_failure

                session.info["settings"] = settings
                record_failure(session, job_id, error)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("job_id", type=UUID)
    parser.add_argument("--parent-pid", required=True, type=int)
    args = parser.parse_args()
    threading.Thread(target=watch_parent, args=(args.parent_pid,), daemon=True).start()
    execute(args.job_id)


if __name__ == "__main__":
    main()
