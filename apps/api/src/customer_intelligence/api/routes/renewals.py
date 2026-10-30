from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlmodel import Session

from customer_intelligence.core.config import Settings, get_settings
from customer_intelligence.core.database import get_session
from customer_intelligence.services import renewals

router = APIRouter(prefix="/renewals", tags=["Renewal radar"])
DB = Annotated[Session, Depends(get_session)]
Config = Annotated[Settings, Depends(get_settings)]
Days = Annotated[int, Query(ge=1, le=renewals.MAX_DAYS)]


@router.get("")
def read_radar(
    session: DB,
    settings: Config,
    days: Days = 30,
    sort: renewals.Sort = "risk",
    score_id: UUID | None = None,
) -> dict:
    return renewals.radar(session, settings, days, sort, score_id)


@router.get("/export.csv")
def export(
    session: DB, settings: Config, days: Days = 30, sort: renewals.Sort = "risk"
) -> Response:
    return Response(
        renewals.export_csv(session, settings, days, sort),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="renewals-{days}d.csv"'},
    )
