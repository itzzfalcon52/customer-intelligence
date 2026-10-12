from collections.abc import Iterator
from sqlite3 import Connection

from fastapi import Request
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from customer_intelligence.core.config import Settings, get_settings
from customer_intelligence.models.conversation import AssistantLease, Conversation, ConversationTurn
from customer_intelligence.models.dataset import Dataset
from customer_intelligence.models.job import Job
from customer_intelligence.models.task import Task

# Register all tables; create_all adds tables without altering existing tables.
TABLE_MODELS = (Dataset, Task, Job, Conversation, ConversationTurn, AssistantLease)


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


def init_database(settings: Settings | None = None, db_engine: Engine | None = None) -> None:
    settings = settings or get_settings()
    settings.data_directory.mkdir(parents=True, exist_ok=True)
    (settings.data_directory / "uploads").mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(db_engine or engine)


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        session.info["settings"] = request.app.state.settings
        yield session
