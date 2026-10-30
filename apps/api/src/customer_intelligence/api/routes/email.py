from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session

from customer_intelligence.core.config import Settings, get_settings
from customer_intelligence.core.database import get_session
from customer_intelligence.services import email

router = APIRouter(prefix="/email", tags=["Email digest"])
DB = Annotated[Session, Depends(get_session)]
Config = Annotated[Settings, Depends(get_settings)]


class Subscription(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    # Used only in private CLI mode; account mode always emails the signed-in address.
    address: str | None = Field(default=None, max_length=320)


@router.get("/subscription")
def read_subscription(request: Request, session: DB, settings: Config) -> dict:
    return email.subscription(session, settings, request.state.identity)


@router.put("/subscription")
def update_subscription(
    update: Subscription, request: Request, session: DB, settings: Config
) -> dict:
    return email.subscribe(
        session, settings, request.state.identity, update.enabled, update.address
    )


@router.post("/test")
def send_test(request: Request, session: DB, settings: Config) -> dict:
    return email.send_test(session, settings, request.state.identity)
