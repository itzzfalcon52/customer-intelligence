from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from customer_intelligence.models.dataset import Dataset


class Task(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    dataset_id: UUID = Field(
        foreign_key=f"{Dataset.__tablename__}.id",
        index=True,
    )
    target_column: str
    positive_label: str
    id_column: str | None = None
    feature_columns: list[str] = Field(sa_column=Column(JSON, nullable=False))
    label_mapping: dict[str, int] = Field(sa_column=Column(JSON, nullable=False))
    features_available_at_prediction: bool
    dataset_sha256: str
    evaluation_strategy: str = "stratified_random"
    # Set for time-ordered evaluation: rows are split by this date column, oldest first.
    time_column: str | None = None
    random_seed: int = 42
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
