from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, SecretStr
from sqlmodel import Session

from customer_intelligence.core.config import Settings, get_settings
from customer_intelligence.core.database import get_session
from customer_intelligence.services import connectors

router = APIRouter(prefix="/connections", tags=["Read-only connectors"])
DB = Annotated[Session, Depends(get_session)]
Config = Annotated[Settings, Depends(get_settings)]


class ConnectionCreate(BaseModel):
    model_config = {"extra": "forbid"}
    provider: Literal["stripe", "razorpay", "zoho_billing", "hubspot", "zoho_crm"]
    label: str = Field(min_length=1, max_length=80)
    # SecretStr keeps credentials out of reprs, logs and validation errors.
    # Stripe and HubSpot send one key; Razorpay and Zoho send named fields.
    secret: SecretStr | None = Field(default=None, min_length=8, max_length=500)
    fields: dict[str, SecretStr] | None = Field(default=None, max_length=8)


@router.get("")
def list_connections(session: DB, settings: Config) -> dict:
    return {
        "enabled": settings.credentials_key is not None,
        "connections": connectors.list_connections(session, settings),
    }


@router.post("", status_code=201)
def create(request: ConnectionCreate, session: DB, settings: Config) -> dict:
    fields = {
        key[:40]: value.get_secret_value()[:1000] for key, value in (request.fields or {}).items()
    }
    return connectors.create(
        session,
        settings,
        request.provider,
        request.label,
        request.secret.get_secret_value() if request.secret else None,
        fields,
    )


@router.post("/{connection_id}/sync", status_code=201)
def sync(connection_id: UUID, session: DB, settings: Config) -> dict:
    return connectors.sync(session, settings, connection_id)


class WriteAccess(BaseModel):
    model_config = {"extra": "forbid"}
    enabled: bool
    # Turning writes on must be confirmed explicitly; the credential needs a tasks write scope.
    confirm: bool = False


@router.put("/{connection_id}/write")
def write_access(connection_id: UUID, request: WriteAccess, session: DB) -> dict:
    from customer_intelligence.core.errors import WorkflowError

    if request.enabled and not request.confirm:
        raise WorkflowError("Confirm that approved plays may create tasks in HubSpot.")
    return connectors.set_write(session, connection_id, request.enabled)


@router.get("/{connection_id}/properties")
def properties(connection_id: UUID, session: DB, settings: Config) -> list[dict]:
    return connectors.date_properties(session, settings, connection_id)


class ConnectionSettings(BaseModel):
    """Only the fields sent are changed; send null to clear one."""

    model_config = {"extra": "forbid"}
    churn_property: str | None = Field(default=None, max_length=200)
    enrich_connection_id: UUID | None = None


@router.put("/{connection_id}/settings")
def configure(
    connection_id: UUID, request: ConnectionSettings, session: DB, settings: Config
) -> dict:
    changes = request.model_dump(include=request.model_fields_set)
    return connectors.configure(session, settings, connection_id, changes)


@router.delete("/{connection_id}", status_code=204)
def delete(connection_id: UUID, session: DB) -> None:
    connectors.delete(session, connection_id)
