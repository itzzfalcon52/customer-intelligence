"""Retention plays: a person queues a play for a batch's contact list and approves it.

Approval either creates CRM tasks for the account owners (HubSpot or Zoho CRM, only through a
connection the user explicitly opened for writing) or leaves a CSV ready to export. Nothing is
sent to end customers, and holdout accounts are never included.
"""

import csv
from io import StringIO
from uuid import UUID

from sqlmodel import Session

from customer_intelligence.core.config import Settings
from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.models.connection import Connection
from customer_intelligence.models.workspace import PendingAction
from customer_intelligence.services import connectors
from customer_intelligence.services.scoring import read_customers, read_score, spreadsheet_safe

MAX_ACCOUNTS = 200


def contact_list(settings: Settings, score_id: UUID, limit: int) -> list[str]:
    score = read_score(score_id, settings.data_directory)
    customers = read_customers(score, settings.data_directory)
    listed = [c for c in customers if c.group == "contact"]
    if not listed:  # batches scored before groups existed: the top of the ranking
        listed = [c for c in customers if c.group != "holdout"][: score.contact_count]
    return [c.customer_id for c in listed[:limit]]


def propose(
    session: Session,
    settings: Settings,
    score_id: UUID,
    title: str,
    instructions: str,
    accounts: int,
    connection_id: UUID | None,
) -> PendingAction:
    from customer_intelligence.services.autonomy import check_action_quota

    destination = "a CSV export"
    if connection_id:
        connection = session.get(Connection, connection_id)
        if connection is None or connectors.role_of(connection.provider) != "crm":
            raise WorkflowError("Choose a CRM connection for task write-back.", 404)
        if not connection.write_enabled:
            raise WorkflowError("Allow this CRM connection to create tasks first.", 409)
        destination = f"{connectors.name_of(connection.provider)} tasks"
    ids = contact_list(settings, score_id, min(accounts, MAX_ACCOUNTS))
    if not ids:
        raise WorkflowError("This batch has no accounts on its contact list.")
    check_action_quota(session)
    action = PendingAction(
        kind="play",
        summary=f"{title}: {len(ids)} accounts from the contact list, as {destination}. "
        "Holdout accounts are excluded.",
        payload={
            "score_id": str(score_id),
            "title": title,
            "instructions": instructions,
            "accounts": ids,
            "connection_id": str(connection_id) if connection_id else None,
        },
        origin="user",
    )
    session.add(action)
    session.commit()
    session.refresh(action)
    return action


def execute(session: Session, settings: Settings, action: PendingAction) -> dict:
    """Run an approved play. Called only from the approval endpoint."""
    payload = action.payload
    if not payload.get("connection_id"):
        return {"destination": "csv", "accounts": len(payload["accounts"])}
    connection = session.get(Connection, UUID(payload["connection_id"]))
    if connection is None or not connection.write_enabled:
        raise WorkflowError("The CRM connection no longer allows task creation.", 409)
    return connectors.create_tasks(
        session,
        settings,
        connection,
        list(payload["accounts"]),
        payload["title"],
        payload["instructions"],
    )


def export(action: PendingAction) -> str:
    if action.kind != "play" or action.status != "approved":
        raise WorkflowError("Only approved plays can be exported.", 409)
    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["customer_id", "play", "instructions"])
    for customer_id in action.payload["accounts"]:
        writer.writerow(
            [
                spreadsheet_safe(customer_id),
                spreadsheet_safe(action.payload["title"]),
                spreadsheet_safe(action.payload["instructions"]),
            ]
        )
    return output.getvalue()
