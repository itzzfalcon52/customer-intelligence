from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class Dataset(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)

    original_filename: str
    storage_key: str = Field(unique=True)

    row_count: int = Field(ge=0)
    column_count: int = Field(ge=0)

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
