from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Form, UploadFile
from pydantic import BaseModel, Field
from sqlmodel import Session

from customer_intelligence.core.config import Settings, get_settings
from customer_intelligence.core.database import get_session
from customer_intelligence.services import sources

router = APIRouter(prefix="/sources", tags=["Account data sources"])
DB = Annotated[Session, Depends(get_session)]
Config = Annotated[Settings, Depends(get_settings)]


class BuildRequest(BaseModel):
    model_config = {"extra": "forbid"}
    horizon_days: int = Field(default=90, ge=14, le=365)
    purpose: Literal["training", "scoring"] = "training"


@router.get("")
def list_sources(settings: Config) -> list[dict]:
    return sources.list_sources(settings)


@router.get("/schema")
def schema() -> dict:
    return {
        "required_columns": sources.required_columns(),
        "optional_columns": {
            "accounts": ["cancelled_at", "plan", "seats", "billing_cycle", "industry", "region"],
            "usage": ["logins"],
            "tickets": ["subject", "body"],
        },
    }


@router.post("/synthetic", status_code=201)
def synthetic(settings: Config) -> dict:
    return sources.create_synthetic(settings)


@router.post("/upload", status_code=201)
async def upload(
    settings: Config,
    name: Annotated[str, Form(min_length=1, max_length=80)],
    accounts: UploadFile,
    invoices: UploadFile | None = None,
    usage: UploadFile | None = None,
    tickets: UploadFile | None = None,
) -> dict:
    files = {}
    for table, upload in (
        ("accounts", accounts),
        ("invoices", invoices),
        ("usage", usage),
        ("tickets", tickets),
    ):
        if upload is not None:
            files[table] = await upload.read(settings.max_upload_mb * 1024 * 1024 + 1)
    return sources.save_bundle(settings, name, files)


@router.get("/{source_id}")
def read_source(source_id: UUID, settings: Config) -> dict:
    return sources.read_source(settings, source_id)


@router.post("/{source_id}/datasets", status_code=201)
def build_dataset(source_id: UUID, request: BuildRequest, session: DB, settings: Config) -> dict:
    return sources.build_dataset(
        session, settings, source_id, request.horizon_days, request.purpose
    )


@router.get("/{source_id}/accounts/{account_id}")
def account(source_id: UUID, account_id: str, settings: Config) -> dict:
    return sources.account_timeline(settings, source_id, account_id)
