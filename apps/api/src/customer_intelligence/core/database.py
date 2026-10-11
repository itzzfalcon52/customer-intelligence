from collections.abc import Iterator
from sqlite3 import Connection

from sqlalchemy import event
from sqlmodel import Session, create_engine

from customer_intelligence.core.config import get_settings
from customer_intelligence.models.task import Task

settings = get_settings()
database_path = settings.data_directory / "metadata.db"

engine = create_engine(
    f"sqlite:///{database_path}",
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def enable_foreign_keys(
    connection: Connection,
    connection_record: object,
) -> None:
    cursor = connection.cursor()

    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def init_database() -> None:
    settings.data_directory.mkdir(parents=True, exist_ok=True)
    (settings.data_directory / "uploads").mkdir(parents=True, exist_ok=True)
    Task.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session