from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from sqlite3 import Connection
from threading import Lock

from fastapi import Request
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from customer_intelligence.core.config import Settings, get_settings
from customer_intelligence.models.connection import Connection as ConnectorConnection
from customer_intelligence.models.conversation import AssistantLease, Conversation, ConversationTurn
from customer_intelligence.models.dataset import Dataset
from customer_intelligence.models.job import Job
from customer_intelligence.models.operations import (
    AuditEvent,
    Brief,
    DigestItem,
    MonitorReport,
)
from customer_intelligence.models.task import Task
from customer_intelligence.models.trace import AgentSpan, AgentTrace
from customer_intelligence.models.workspace import PendingAction, WorkspaceFact

# Register all tables; create_all adds tables without altering existing tables.
TABLE_MODELS = (
    Dataset,
    Task,
    Job,
    Conversation,
    ConversationTurn,
    AssistantLease,
    AgentTrace,
    AgentSpan,
    WorkspaceFact,
    PendingAction,
    ConnectorConnection,
    MonitorReport,
    DigestItem,
    AuditEvent,
    Brief,
)


def create_database_engine(settings: Settings) -> Engine:
    result = create_engine(
        f"sqlite:///{settings.data_directory / 'metadata.db'}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    @event.listens_for(result, "connect")
    def enable_foreign_keys(connection: Connection, record: object) -> None:
        cursor = connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=30000")
        finally:
            cursor.close()

    return result


engine = create_database_engine(get_settings())
_workspace_lock = Lock()
# Workspaces whose tables were checked by this process; new tables reach older workspaces.
_checked_workspaces: set[Path] = set()


def add_missing_columns(db_engine: Engine) -> list[str]:
    """create_all never alters tables; add new nullable columns to existing workspaces."""
    from sqlalchemy import inspect, text

    added: list[str] = []
    inspector = inspect(db_engine)
    with db_engine.begin() as connection:
        for table in SQLModel.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            present = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in present:
                    continue
                if not column.nullable:
                    raise RuntimeError(f"New column {table.name}.{column.name} must be nullable.")
                kind = column.type.compile(dialect=db_engine.dialect)
                connection.execute(
                    text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {kind}')
                )
                added.append(f"{table.name}.{column.name}")
    return added


def init_database(settings: Settings | None = None, db_engine: Engine | None = None) -> None:
    settings = settings or get_settings()
    settings.data_directory.mkdir(parents=True, exist_ok=True)
    (settings.data_directory / "uploads").mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(db_engine or engine)
    add_missing_columns(db_engine or engine)


@contextmanager
def open_session(request: Request) -> Iterator[Session]:
    """Session for the request's workspace; usable outside FastAPI's dependency lifecycle."""
    settings = getattr(request.state, "workspace_settings", request.app.state.settings)
    scoped = settings is not request.app.state.settings
    db = create_database_engine(settings) if scoped else request.app.state.engine
    try:
        if scoped:
            with _workspace_lock:
                marker = settings.data_directory / ".workspace-ready"
                if not marker.exists() or settings.data_directory not in _checked_workspaces:
                    init_database(settings, db)
                    (settings.data_directory / "metadata.db").chmod(0o600)
                    marker.touch(mode=0o600)
                    _checked_workspaces.add(settings.data_directory)
        with Session(db) as session:
            session.info["settings"] = settings
            identity = getattr(request.state, "identity", None)
            session.info["actor"] = identity.user_id if identity else None
            yield session
    finally:
        if scoped:
            db.dispose()


def get_session(request: Request) -> Iterator[Session]:
    with open_session(request) as session:
        yield session
