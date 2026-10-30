from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from customer_intelligence.core.config import Settings, get_settings
from customer_intelligence.core.database import get_session
from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.models.operations import DigestItem, MonitorReport
from customer_intelligence.schemas.operations import (
    AutonomySettings,
    AutonomyUpdate,
    DigestItemResponse,
    MonitorReportResponse,
    OutcomesRequest,
    PromoteRequest,
    Schedule,
    ScheduleUpdate,
    SourceOutcomesRequest,
)
from customer_intelligence.schemas.workflow import JobResponse
from customer_intelligence.services import autonomy, monitoring

router = APIRouter(tags=["Monitoring and autonomy"])
DB = Annotated[Session, Depends(get_session)]
Config = Annotated[Settings, Depends(get_settings)]


@router.get("/registry")
def registry(session: DB) -> dict:
    return monitoring.active_model(session)


@router.post("/registry/promote")
def promote(request: PromoteRequest, session: DB, settings: Config) -> dict:
    return monitoring.promote(session, settings, request.run_id)


@router.post("/registry/rollback")
def rollback(session: DB, settings: Config) -> dict:
    return monitoring.rollback(session, settings)


@router.get("/monitoring", response_model=list[MonitorReportResponse])
def reports(
    session: DB,
    kind: Annotated[str | None, Query(pattern="^(drift|performance|lift)$")] = None,
) -> list[MonitorReport]:
    return monitoring.list_reports(session, kind)


@router.get("/monitoring/{report_id}", response_model=MonitorReportResponse)
def report(report_id: UUID, session: DB) -> MonitorReport:
    found = session.get(MonitorReport, report_id)
    if found is None:
        raise WorkflowError("Monitoring report not found.", 404)
    return found


@router.post("/monitoring/drift", response_model=MonitorReportResponse, status_code=201)
def drift(score_id: Annotated[UUID, Query()], session: DB, settings: Config) -> MonitorReport:
    return monitoring.feature_drift(session, settings, score_id)


@router.post("/monitoring/performance", response_model=MonitorReportResponse, status_code=201)
def performance(request: OutcomesRequest, session: DB, settings: Config) -> MonitorReport:
    return monitoring.performance_from_file(
        session,
        settings,
        request.score_id,
        request.dataset_id,
        request.id_column,
        request.outcome_column,
        request.positive_label,
    )


@router.post("/monitoring/lift", response_model=MonitorReportResponse, status_code=201)
def lift(request: OutcomesRequest, session: DB, settings: Config) -> MonitorReport:
    outcomes, segments = monitoring.outcomes_from_file(
        session,
        settings,
        request.dataset_id,
        request.id_column,
        request.outcome_column,
        request.positive_label,
        request.segment_column,
    )
    return monitoring.measure_lift(
        session,
        settings,
        request.score_id,
        outcomes,
        {"kind": "outcomes_file", "dataset_id": str(request.dataset_id)},
        segments,
    )


@router.post("/monitoring/lift/source", response_model=MonitorReportResponse, status_code=201)
def lift_from_source(
    request: SourceOutcomesRequest, session: DB, settings: Config
) -> MonitorReport:
    outcomes, segments = monitoring.outcomes_from_source(
        settings, request.score_id, request.source_id, request.horizon_days
    )
    return monitoring.measure_lift(
        session,
        settings,
        request.score_id,
        outcomes,
        {
            "kind": "source_sync",
            "source_id": str(request.source_id),
            "horizon_days": request.horizon_days,
        },
        segments,
    )


@router.get("/autonomy")
def read_autonomy(session: DB) -> dict:
    return {
        **autonomy.read_autonomy(session).model_dump(),
        "usage": autonomy.usage(session),
    }


@router.put("/autonomy", response_model=AutonomySettings)
def update_autonomy(update: AutonomyUpdate, session: DB, settings: Config) -> AutonomySettings:
    return autonomy.update_autonomy(session, settings, update)


@router.get("/schedule", response_model=Schedule)
def read_schedule(session: DB) -> Schedule:
    return autonomy.read_schedule(session)


@router.put("/schedule", response_model=Schedule)
def update_schedule(update: ScheduleUpdate, session: DB, settings: Config) -> Schedule:
    return autonomy.update_schedule(session, settings, update)


@router.post("/schedule/run", response_model=JobResponse, status_code=202)
def run_now(session: DB) -> object:
    if autonomy.read_autonomy(session).paused:
        raise WorkflowError("Cycles are paused for this workspace (kill switch).", 423)
    return autonomy.submit_cycle(session, "manual", f"manual:{uuid4()}")


@router.get("/digest", response_model=list[DigestItemResponse])
def digest(session: DB) -> list[DigestItem]:
    return autonomy.list_digest(session)


@router.post("/digest/{item_id}/read", response_model=DigestItemResponse)
def mark_read(item_id: UUID, session: DB) -> DigestItem:
    return autonomy.mark_read(session, item_id)
