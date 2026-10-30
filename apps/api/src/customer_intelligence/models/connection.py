from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class Connection(SQLModel, table=True):
    """A connector. The credential is stored only as Fernet ciphertext.

    Connectors read by default. `write_enabled` is an explicit, separate opt-in that lets an
    approved play create HubSpot tasks; nothing else ever writes.
    """

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    provider: str = Field(index=True)
    label: str = Field(max_length=80)
    secret_ciphertext: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_synced_at: datetime | None = None
    last_source_id: UUID | None = None
    last_error: str | None = Field(default=None, max_length=500)
    write_enabled: bool | None = None
    # HubSpot: the company date property that records when a customer churned (chosen by an admin;
    # churn is never guessed). Stripe: a HubSpot connection whose companies and tickets enrich this
    # connection's accounts, matched by email domain.
    churn_property: str | None = Field(default=None, max_length=200)
    enrich_connection_id: UUID | None = None
