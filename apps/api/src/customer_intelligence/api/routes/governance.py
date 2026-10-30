from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session

from customer_intelligence.core.config import Settings, get_settings
from customer_intelligence.core.database import get_session
from customer_intelligence.models.operations import AuditEvent
from customer_intelligence.services import audit, governance, privacy

router = APIRouter(tags=["Workspace governance"])
DB = Annotated[Session, Depends(get_session)]
Config = Annotated[Settings, Depends(get_settings)]


class PrivacyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blocked_columns: list[str] = Field(default_factory=list, max_length=200)
    default_patterns: bool = True


class RetentionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    days: int | None = Field(default=None, ge=7, le=3650)


@router.get("/workspace/identity")
def identity(request: Request) -> dict:
    who = request.state.identity
    return {
        "user_id": who.user_id,
        "organization_id": who.organization_id,
        "role": who.role,
        "can_manage": who.role in ("owner", "admin"),
        "can_edit": who.role != "viewer",
    }


@router.get("/workspace/permissions")
def permissions(request: Request) -> dict:
    from customer_intelligence.core.permissions import capabilities

    role = request.state.identity.role
    return {
        "role": role,
        "capabilities": capabilities(role),
        "roles": {r: capabilities(r) for r in ("admin", "member", "viewer")},
    }


@router.get("/audit")
def audit_log(session: DB) -> list[AuditEvent]:
    return audit.list_events(session)


@router.get("/usage")
def usage(
    session: DB,
    settings: Config,
    month: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")] = None,
) -> dict:
    return governance.usage(session, settings, month)


@router.get("/privacy")
def read_privacy(session: DB) -> dict:
    return privacy.read_policy(session)


@router.put("/privacy")
def update_privacy(update: PrivacyUpdate, session: DB) -> dict:
    return privacy.update_policy(session, update.blocked_columns, update.default_patterns)


@router.get("/retention-policy")
def read_retention(session: DB) -> dict:
    return governance.read_retention(session)


@router.put("/retention-policy")
def update_retention(update: RetentionUpdate, session: DB) -> dict:
    return governance.update_retention(session, update.days)


@router.post("/retention-policy/apply")
def apply_retention(session: DB, settings: Config) -> dict:
    return governance.apply_retention(session, settings)
