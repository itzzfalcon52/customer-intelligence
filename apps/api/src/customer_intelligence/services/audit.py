"""Workspace audit log: every successful change made through the API, plus automated actions.

Only the method, path, actor, role and status are kept. Bodies (which may hold credentials or
customer data) are never recorded.
"""

from datetime import datetime
from typing import Any

from fastapi import Request
from sqlmodel import Session, SQLModel, col, select

from customer_intelligence.core.config import Settings
from customer_intelligence.models.operations import AuditEvent


def _write(settings: Settings, event: AuditEvent) -> None:
    from customer_intelligence.core.database import create_database_engine

    engine = create_database_engine(settings)
    try:
        SQLModel.metadata.create_all(engine, tables=[SQLModel.metadata.tables["auditevent"]])
        with Session(engine) as session:
            session.add(event)
            session.commit()
    finally:
        engine.dispose()


def record_request(settings: Settings, identity: Any, request: Request, status: int) -> None:
    path = request.url.path
    _write(
        settings,
        AuditEvent(
            actor=identity.user_id,
            role=identity.role,
            action=f"{request.method} {path.removeprefix('/api/v1')}",
            status_code=status,
        ),
    )


def record(session: Session, component: str, action: str, target: str | None = None) -> None:
    """An automated action (scheduled check, monitoring proposal) in the current session."""
    session.add(
        AuditEvent(actor=f"system:{component}", role="system", action=action, target=target)
    )
    session.commit()


def list_events(session: Session, limit: int = 200) -> list[AuditEvent]:
    return list(session.exec(select(AuditEvent).order_by(col(AuditEvent.at).desc()).limit(limit)))


def prune(session: Session, before: datetime) -> int:
    old = session.exec(select(AuditEvent).where(col(AuditEvent.at) < before)).all()
    for event in old:
        session.delete(event)
    session.commit()
    return len(old)
