"""Retention plays: a person queues a play for a batch's contact list and approves it.

Approval either creates HubSpot tasks for the account owners (only through a HubSpot
connection the user explicitly opened for writing) or leaves a CSV ready to export. Nothing is
sent to end customers, and holdout accounts are never included.
"""

import csv
from datetime import UTC, datetime, timedelta
from io import StringIO
from uuid import UUID

import httpx
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

    if connection_id:
        connection = session.get(Connection, connection_id)
        if connection is None or connection.provider != "hubspot":
            raise WorkflowError("Choose a HubSpot connection for task write-back.", 404)
        if not connection.write_enabled:
            raise WorkflowError("Allow this HubSpot connection to create tasks first.", 409)
    ids = contact_list(settings, score_id, min(accounts, MAX_ACCOUNTS))
    if not ids:
        raise WorkflowError("This batch has no accounts on its contact list.")
    check_action_quota(session)
    destination = "HubSpot tasks" if connection_id else "a CSV export"
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
        raise WorkflowError("The HubSpot connection no longer allows task creation.", 409)
    secret = connectors.secret_for(session, settings, connection)
    due = int((datetime.now(UTC) + timedelta(days=2)).timestamp() * 1000)
    written, skipped, failed = 0, 0, 0
    # Stripe-anchored accounts reach their HubSpot company through the domain match.
    links = connectors.company_links(session, settings, connection.id)
    with connectors._client(settings, "hubspot", secret) as client:
        for customer_id in payload["accounts"]:
            company = customer_id.rpartition("@")[0] or customer_id
            company = links.get(company, company)
            if not company.isdigit():
                skipped += 1  # not a HubSpot company ID; stays in the CSV export
                continue
            try:
                response = client.post(
                    "/crm/v3/objects/tasks",
                    json={
                        "properties": {
                            "hs_task_subject": payload["title"][:200],
                            "hs_task_body": payload["instructions"][:4000],
                            "hs_task_status": "NOT_STARTED",
                            "hs_timestamp": due,
                        },
                        "associations": [
                            {
                                "to": {"id": company},
                                "types": [
                                    {
                                        "associationCategory": "HUBSPOT_DEFINED",
                                        "associationTypeId": 192,
                                    }
                                ],
                            }
                        ],
                    },
                )
            except httpx.HTTPError:
                failed += 1
                continue
            if response.status_code in (401, 403):
                raise WorkflowError(
                    "HubSpot refused task creation; check the credential's write scope.", 400
                )
            if response.status_code >= 300:
                failed += 1
            else:
                written += 1
    return {"destination": "hubspot", "written": written, "skipped": skipped, "failed": failed}


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
