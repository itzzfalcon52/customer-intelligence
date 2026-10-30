from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Query, UploadFile

from customer_intelligence.core.config import Settings, get_settings
from customer_intelligence.services import playbooks

router = APIRouter(prefix="/playbooks", tags=["Playbooks"])
Config = Annotated[Settings, Depends(get_settings)]


@router.get("")
def list_playbooks(settings: Config) -> list[dict]:
    return playbooks.list_playbooks(settings)


@router.post("", status_code=201)
async def upload(
    settings: Config,
    file: UploadFile,
    title: Annotated[str | None, Form(max_length=120)] = None,
) -> dict:
    content = await file.read(playbooks.MAX_BYTES + 1)
    return playbooks.create(settings, file.filename or "playbook.txt", title, content)


@router.get("/search")
def search(
    settings: Config,
    q: Annotated[str, Query(min_length=2, max_length=300)],
    limit: Annotated[int, Query(ge=1, le=10)] = 4,
) -> dict:
    return playbooks.search(settings, q, limit)


@router.get("/{playbook_id}")
def read_playbook(playbook_id: UUID, settings: Config) -> dict:
    return playbooks.read_playbook(settings, playbook_id)


@router.delete("/{playbook_id}", status_code=204)
def delete(playbook_id: UUID, settings: Config) -> None:
    playbooks.delete(settings, playbook_id)
