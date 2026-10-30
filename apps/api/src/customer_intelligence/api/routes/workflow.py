import html
import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlmodel import Session, col, select

from customer_intelligence.core.config import Settings, get_settings
from customer_intelligence.core.database import get_session
from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.ml.evaluation import candidate_specs
from customer_intelligence.models.job import Job
from customer_intelligence.models.task import Task
from customer_intelligence.schemas.runs import TrainingRunResponse
from customer_intelligence.schemas.task import TaskResponse
from customer_intelligence.schemas.workflow import (
    DiagnosticsRequest,
    ExplanationRequest,
    FinalEvaluation,
    JobResponse,
    LeakageRequest,
    RunActionRequest,
    RunComparisonRequest,
    ScoreManifest,
    ScorePage,
    ScoreRequest,
    TrainRequest,
)
from customer_intelligence.services.artifacts import read_json
from customer_intelligence.services.jobs import cancel_job, get_job, submit_job
from customer_intelligence.services.runs import read_training_run
from customer_intelligence.services.scoring import export_scores, read_customers, read_score

router = APIRouter(tags=["Workflow"])
DB = Annotated[Session, Depends(get_session)]
Config = Annotated[Settings, Depends(get_settings)]


@router.get("/tasks/{task_id}/plan")
def training_plan(task_id: UUID, session: DB) -> dict:
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


@router.post("/jobs/train", response_model=JobResponse, status_code=202)
def train(request: TrainRequest, session: DB) -> Job:
    return submit_job(session, "train", request.model_dump(mode="json"), request.idempotency_key)


@router.post("/jobs/evaluate", response_model=JobResponse, status_code=202)
def evaluate(request: RunActionRequest, session: DB, settings: Config) -> Job:
    read_training_run(request.run_id, settings.data_directory)
    return submit_job(session, "evaluate", request.model_dump(mode="json"), request.idempotency_key)


@router.post("/jobs/score", response_model=JobResponse, status_code=202)
def score(request: ScoreRequest, session: DB, settings: Config) -> Job:
    read_training_run(request.run_id, settings.data_directory)
    return submit_job(session, "score", request.model_dump(mode="json"), request.idempotency_key)


@router.post("/jobs/diagnostics", response_model=JobResponse, status_code=202)
def analyze(request: DiagnosticsRequest, session: DB, settings: Config) -> Job:
    read_training_run(request.run_id, settings.data_directory)
    return submit_job(
        session, "diagnostics", request.model_dump(mode="json"), request.idempotency_key
    )


@router.post("/jobs/explain", response_model=JobResponse, status_code=202)
def explain(request: ExplanationRequest, session: DB, settings: Config) -> Job:
    manifest = read_score(request.score_id, settings.data_directory)
    if request.row_reference > manifest.row_count:
        raise WorkflowError("Scoring row not found.", 404)
    return submit_job(session, "explain", request.model_dump(mode="json"), request.idempotency_key)


@router.post("/jobs/leakage-demo", response_model=JobResponse, status_code=202)
def leakage(request: LeakageRequest, session: DB) -> Job:
    return submit_job(session, "leakage", request.model_dump(mode="json"), request.idempotency_key)


@router.get("/jobs", response_model=list[JobResponse])
def jobs(
    session: DB,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Job]:
    return list(
        session.exec(
            select(Job).order_by(col(Job.created_at).desc()).offset(offset).limit(limit)
        ).all()
    )


@router.get("/jobs/{job_id}", response_model=JobResponse)
def job_status(job_id: UUID, session: DB) -> Job:
    return get_job(session, job_id)


@router.post("/jobs/{job_id}/cancel", response_model=JobResponse)
def cancel(job_id: UUID, session: DB) -> Job:
    return cancel_job(session, job_id)


@router.get("/runs/{run_id}", response_model=TrainingRunResponse)
def run_result(run_id: UUID, settings: Config) -> TrainingRunResponse:
    manifest = read_training_run(run_id, settings.data_directory)
    return TrainingRunResponse(
        run_id=run_id,
        created_at=manifest.created_at,
        fit_partition=manifest.fit_partition,
        report=manifest.report,
        calibration=manifest.calibration,
    )


@router.get("/runs")
def run_history(
    settings: Config,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict]:
    directory = settings.data_directory / "runs"
    results: list[dict] = []
    if not directory.exists():
        return results
    paths = sorted(
        (p for p in directory.iterdir() if p.is_dir() and not p.name.startswith(".")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in paths[offset : offset + limit]:
        try:
            run = read_training_run(UUID(path.name), settings.data_directory)
            results.append(
                {
                    "run_id": str(run.run_id),
                    "created_at": run.created_at.isoformat(),
                    "task_id": str(run.task.id),
                    "model": run.report.best_validation_model,
                    "average_precision": max(
                        r.validation.average_precision for r in run.report.results
                    ),
                    "test_evaluated": (path / "evaluation.json").exists(),
                }
            )
        except ValueError:
            results.append({"run_id": path.name, "error": "Saved manifest is unreadable."})
    return results


@router.get("/runs/{run_id}/evaluation", response_model=FinalEvaluation)
def evaluation_result(run_id: UUID, settings: Config) -> FinalEvaluation:
    read_training_run(run_id, settings.data_directory)
    return FinalEvaluation.model_validate(
        read_json(settings.data_directory / "runs" / str(run_id) / "evaluation.json")
    )


@router.get("/analyses/{analysis_id}")
def analysis_result(analysis_id: UUID, settings: Config) -> dict:
    payload = read_json(settings.data_directory / "analyses" / str(analysis_id) / "manifest.json")
    if not isinstance(payload, dict) or payload.get("id") != str(analysis_id):
        raise WorkflowError("Analysis artifact identity mismatch.", 409)
    return payload


@router.get("/scores/{score_id}", response_model=ScoreManifest)
def score_result(score_id: UUID, settings: Config) -> ScoreManifest:
    return read_score(score_id, settings.data_directory)


@router.get("/scores/{score_id}/customers", response_model=ScorePage)
def customers(
    score_id: UUID,
    settings: Config,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> ScorePage:
    manifest = read_score(score_id, settings.data_directory)
    rows = read_customers(manifest, settings.data_directory)
    return ScorePage(
        score_id=score_id, total=len(rows), offset=offset, customers=rows[offset : offset + limit]
    )


@router.get("/scores/{score_id}/export")
def export(
    score_id: UUID,
    settings: Config,
    top_k: Annotated[int | None, Query(ge=1, le=10_000_000)] = None,
) -> Response:
    manifest = read_score(score_id, settings.data_directory)
    content = export_scores(manifest, read_customers(manifest, settings.data_directory), top_k)
    return Response(
        content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="scores-{score_id}.csv"'},
    )


@router.get("/runs/{run_id}/report")
def experiment_report(run_id: UUID, settings: Config) -> Response:
    run = read_training_run(run_id, settings.data_directory)
    rows = "".join(
        f"<tr><td>{html.escape(r.candidate_id or r.model_name)}</td>"
        f"<td>{r.validation.average_precision:.6f}</td><td>{r.validation.roc_auc:.6f}</td>"
        f"<td>{r.validation.recall:.6f}</td><td>{r.elapsed_seconds:.3f}</td></tr>"
        for r in run.report.results
    )
    test_path = settings.data_directory / "runs" / str(run_id) / "evaluation.json"
    final = (
        html.escape(json.dumps(read_json(test_path), indent=2))
        if test_path.exists()
        else "Not evaluated."
    )
    selected = run.report.best_validation_candidate_id or run.report.best_validation_model
    content = "".join(
        [
            '<!doctype html><html lang="en"><meta charset="utf-8"><title>Experiment report</title>',
            "<style>body{font:16px system-ui;max-width:1000px;margin:40px auto;padding:20px}",
            "td,th{padding:10px;border:1px solid #ddd}table{border-collapse:collapse}",
            "pre{white-space:pre-wrap}</style>",
            f"<h1>Customer intelligence experiment</h1><p>Run: {run_id}</p>",
            f"<p>Target: {html.escape(run.task.target_column)}; ",
            f"positive label: {html.escape(run.task.positive_label)}</p>",
            f"<p>Selected: {html.escape(selected)}; objective: average precision; ",
            f"threshold: {run.report.classification_threshold}</p>",
            f"<p>Features: {html.escape(', '.join(run.task.feature_columns))}</p>",
            f"<p>ID excluded: {html.escape(run.task.id_column or 'No ID specified')}; ",
            f"seed: {run.task.random_seed}</p>",
            "<table><tr><th>Candidate</th><th>Validation AP</th><th>ROC-AUC</th>",
            "<th>Recall</th><th>Seconds</th></tr>",
            f"{rows}</table><h2>Calibration development diagnostics</h2>",
            f"<pre>{html.escape(json.dumps(run.calibration, indent=2))}</pre>",
            f"<h2>Frozen final test evaluation</h2><pre>{final}</pre>",
            f"<h2>Provenance</h2><pre>{html.escape(run.report.model_dump_json(indent=2))}</pre>",
            "<p>Feature availability and label meaning require business validation. ",
            "Scores are not causal explanations or proof of saved revenue. ",
            "Static benchmarks do not establish future-window performance.</p></html>",
        ]
    )
    return Response(
        content,
        media_type="text/html",
        headers={"Content-Disposition": f'attachment; filename="experiment-{run_id}.html"'},
    )


@router.post("/jobs/calibrate", response_model=JobResponse, status_code=202)
def calibrate(request: RunActionRequest, session: DB, settings: Config) -> Job:
    read_training_run(request.run_id, settings.data_directory)
    return submit_job(
        session, "calibrate", request.model_dump(mode="json"), request.idempotency_key
    )


@router.post("/runs/compare")
def compare_runs(request: RunComparisonRequest, settings: Config) -> dict:
    manifests = [read_training_run(uid, settings.data_directory) for uid in request.run_ids]
    first = manifests[0]
    differences = set()
    for current in manifests[1:]:
        for attribute in (
            "dataset_sha256",
            "target_column",
            "positive_label",
            "label_mapping",
            "feature_columns",
        ):
            if getattr(current.task, attribute) != getattr(first.task, attribute):
                differences.add(attribute)
        if current.split.row_assignments != first.split.row_assignments:
            differences.add("split_row_assignments")
        if current.package_versions != first.package_versions:
            differences.add("library_versions")
        if current.source_sha256 != first.source_sha256:
            differences.add("source_code")
        if bool(current.calibration) != bool(first.calibration):
            differences.add("calibration_status")
    return {
        "comparable": not differences,
        "differences": sorted(differences),
        "comparison_role": "base_model_validation_selection",
        "runs": [
            {
                "run_id": str(run.run_id),
                "report": run.report.model_dump(mode="json"),
                "calibration": run.calibration,
            }
            for run in manifests
        ],
        "warning": (
            "Different datasets, labels, splits, or environments make a direct "
            "leaderboard comparison misleading."
        ),
    }


@router.get("/scores")
def score_history(
    settings: Config, limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0)
) -> list[dict]:
    directory = settings.data_directory / "scores"
    if not directory.exists():
        return []
    paths = sorted(
        (p for p in directory.iterdir() if p.is_dir() and not p.name.startswith(".")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return [
        read_score(UUID(p.name), settings.data_directory).model_dump(mode="json")
        for p in paths[offset : offset + limit]
    ]


@router.get("/analyses")
def analysis_history(
    settings: Config, limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0)
) -> list[dict]:
    directory = settings.data_directory / "analyses"
    if not directory.exists():
        return []
    paths = sorted(
        (p for p in directory.iterdir() if p.is_dir() and not p.name.startswith(".")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return [dict(read_json(p / "manifest.json")) for p in paths[offset : offset + limit]]


@router.get("/runs/{run_id}/briefing")
def saved_briefing(run_id: UUID, settings: Config) -> dict:
    run = read_training_run(run_id, settings.data_directory)
    path = settings.data_directory / "runs" / str(run_id) / "briefing-status.json"
    if path.exists():
        payload = read_json(path)
        if isinstance(payload, dict):
            return payload
    return {"state": "not_requested", "source": "computed", **run.report.executive_briefing}


@router.get("/scores/{score_id}/campaign")
def score_campaign(score_id: UUID, settings: Config) -> dict:
    read_score(score_id, settings.data_directory)
    path = settings.data_directory / "scores" / str(score_id) / "campaign-status.json"
    if path.exists():
        payload = read_json(path)
        if isinstance(payload, dict):
            return payload
    return {"state": "not_requested"}
