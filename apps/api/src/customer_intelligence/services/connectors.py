"""Read-only billing and CRM connectors that produce account data sources.

Billing (the record of who paid and who cancelled): Stripe, Razorpay, Zoho Billing.
CRM (companies, support tickets/cases, churn field, optional task write-back): HubSpot, Zoho CRM.

Credentials are verified with one cheap read, then stored only as Fernet ciphertext keyed by
`CI_CREDENTIALS_KEY` (a single key for Stripe/HubSpot, a JSON object for the others). They are
never returned by the API, logged or written to a source. Syncs are bounded (MAX_PAGES per
object) and only read; the one write is a CRM task for an approved play, behind its own opt-in.
"""

import json
import time
from collections import defaultdict
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
import pandas as pd
from cryptography.fernet import Fernet, InvalidToken
from sqlmodel import Session, col, select

from customer_intelligence.core.config import Settings
from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.models.connection import Connection
from customer_intelligence.services import sources

# provider → (display name, role). Billing providers own cancellations; CRMs enrich them.
REGISTRY: dict[str, tuple[str, str]] = {
    "stripe": ("Stripe", "billing"),
    "razorpay": ("Razorpay", "billing"),
    "zoho_billing": ("Zoho Billing", "billing"),
    "hubspot": ("HubSpot", "crm"),
    "zoho_crm": ("Zoho CRM", "crm"),
}
PROVIDERS = tuple(REGISTRY)
# Single pasted key; every other provider sends named fields.
SINGLE_SECRET = {"stripe", "hubspot"}


def name_of(provider: str) -> str:
    return REGISTRY.get(provider, (provider.title(), ""))[0]


def role_of(provider: str) -> str:
    return REGISTRY.get(provider, ("", ""))[1]


MAX_PAGES = 100
# Rate limits and transient provider errors are retried a few times with a short, capped wait.
ATTEMPTS = 3
MAX_WAIT_SECONDS = 5.0
RETRYABLE = {429, 500, 502, 503, 504}
# Tests replace this with httpx.MockTransport; production uses the default network transport.
transport: httpx.BaseTransport | None = None
sleep = time.sleep
# What each endpoint is called in an error, so a missing key permission is easy to fix.
OBJECTS = {
    "/v1/customers": "customers",
    "/v1/subscriptions": "subscriptions",
    "/v1/invoices": "invoices",
    "/crm/v3/objects/companies": "companies",
    "/crm/v3/objects/tickets": "tickets",
    "/v1/plans": "plans",
    "/crm/v8/Accounts": "accounts",
    "/crm/v8/Cases": "cases",
    "/crm/v8/settings/fields": "field settings",
    "/billing/v1/customers": "customers",
    "/billing/v1/subscriptions": "subscriptions",
    "/billing/v1/invoices": "invoices",
    "/billing/v1/organizations": "organizations",
}


def _fernet(settings: Settings) -> Fernet:
    if settings.credentials_key is None:
        raise WorkflowError(
            "Connectors are disabled: set CI_CREDENTIALS_KEY in the API environment first.", 409
        )
    try:
        return Fernet(settings.credentials_key.get_secret_value().encode())
    except ValueError as exc:
        raise WorkflowError("CI_CREDENTIALS_KEY is not a valid Fernet key.", 409) from exc


def _client(settings: Settings, provider: str, secret: str) -> httpx.Client:
    base = settings.stripe_api_base if provider == "stripe" else settings.hubspot_api_base
    return httpx.Client(
        base_url=base,
        headers={"Authorization": f"Bearer {secret}", "Accept": "application/json"},
        timeout=30,
        transport=transport,
        follow_redirects=False,
    )


def _wait(response: httpx.Response | None, attempt: int) -> float:
    header = response.headers.get("Retry-After") if response is not None else None
    try:
        wait = float(header) if header else 0.5 * 2**attempt
    except ValueError:
        wait = 0.5 * 2**attempt
    return min(max(wait, 0.0), MAX_WAIT_SECONDS)


def _scope_problem(response: httpx.Response) -> bool:
    try:
        body = response.json()
    except ValueError:
        return False
    return isinstance(body, dict) and "SCOPE" in str(body.get("code", "")).upper()


def _get(client: httpx.Client, path: str, params: dict[str, Any]) -> dict:
    response: httpx.Response | None = None
    for attempt in range(ATTEMPTS):
        try:
            response = client.get(path, params=params)
        except httpx.HTTPError as exc:
            if attempt == ATTEMPTS - 1:
                raise WorkflowError("The provider could not be reached.", 502) from exc
            sleep(_wait(None, attempt))
            continue
        if response.status_code not in RETRYABLE or attempt == ATTEMPTS - 1:
            break
        sleep(_wait(response, attempt))
    assert response is not None
    if response.status_code == 204:
        return {}  # Zoho answers "no records" with an empty 204
    if response.status_code == 401 and not _scope_problem(response):
        raise WorkflowError("The provider rejected the key. Check that it was copied whole.", 400)
    if response.status_code in (401, 403):
        what = OBJECTS.get(path, "this data")
        raise WorkflowError(f"This key can't read {what}. Give it read access and try again.", 400)
    if response.status_code == 429:
        raise WorkflowError("The provider rate-limited this sync. Try again shortly.", 429)
    if response.status_code >= 400:
        raise WorkflowError(f"The provider returned HTTP {response.status_code}.", 502)
    body = response.json()
    if not isinstance(body, dict):
        raise WorkflowError("Unexpected provider response.", 502)
    return body


def _stripe_pages(client: httpx.Client, path: str, params: dict[str, Any]) -> Iterator[dict]:
    after = None
    for _ in range(MAX_PAGES):
        body = _get(
            client, path, {**params, "limit": 100, **({"starting_after": after} if after else {})}
        )
        items = body.get("data") or []
        yield from items
        if not body.get("has_more") or not items:
            return
        after = items[-1]["id"]


def _hubspot_pages(client: httpx.Client, path: str, params: dict[str, Any]) -> Iterator[dict]:
    after = None
    for _ in range(MAX_PAGES):
        body = _get(client, path, {**params, "limit": 100, **({"after": after} if after else {})})
        yield from body.get("results") or []
        after = (body.get("paging") or {}).get("next", {}).get("after")
        if not after:
            return


def _day(timestamp: Any) -> str:
    if timestamp in (None, ""):
        return ""
    if isinstance(timestamp, (int, float)):
        return datetime.fromtimestamp(timestamp, UTC).date().isoformat()
    return pd.Timestamp(timestamp).date().isoformat()


def stripe_tables(client: httpx.Client) -> dict[str, pd.DataFrame]:
    customers = list(_stripe_pages(client, "/v1/customers", {}))
    subscriptions = list(_stripe_pages(client, "/v1/subscriptions", {"status": "all"}))
    invoices = list(_stripe_pages(client, "/v1/invoices", {}))
    by_customer: dict[str, list[dict]] = defaultdict(list)
    for sub in subscriptions:
        by_customer[str(sub.get("customer"))].append(sub)
    accounts = []
    for customer in customers:
        subs = sorted(by_customer.get(customer["id"], []), key=lambda s: s.get("created") or 0)
        latest = subs[-1] if subs else {}
        item = ((latest.get("items") or {}).get("data") or [{}])[0]
        price = item.get("price") or {}
        ended = [s for s in subs if s.get("status") in ("canceled", "incomplete_expired")]
        cancelled = ""
        if subs and len(ended) == len(subs):
            cancelled = _day(max((s.get("ended_at") or s.get("canceled_at") or 0) for s in ended))
        live = [s for s in subs if s.get("status") in ("active", "trialing", "past_due")]
        current = live[-1] if live else {}
        # Newer Stripe API versions moved the period end onto the subscription item.
        period_end = current.get("current_period_end") or (
            ((current.get("items") or {}).get("data") or [{}])[0].get("current_period_end")
        )
        accounts.append(
            {
                "account_id": customer["id"],
                "domain": _domain(customer.get("email")),
                "renews_at": "" if cancelled else _day(period_end),
                "cancel_scheduled": "yes"
                if current.get("cancel_at_period_end") or current.get("cancel_at")
                else "",
                "created_at": _day(customer.get("created")),
                "cancelled_at": cancelled,
                "plan": price.get("nickname") or price.get("product") or "",
                "seats": item.get("quantity"),
                "billing_cycle": "annual"
                if (price.get("recurring") or {}).get("interval") == "year"
                else "monthly",
            }
        )
    known = {a["account_id"] for a in accounts}
    invoice_rows = []
    for invoice in invoices:
        owner = str(invoice.get("customer"))
        status = invoice.get("status")
        if owner not in known or status in ("draft", "void"):
            continue
        failed = status in ("open", "uncollectible") and (invoice.get("attempt_count") or 0) > 0
        if status != "paid" and not failed:
            continue
        invoice_rows.append(
            {
                "account_id": owner,
                "date": _day(invoice.get("created")),
                "amount": float(
                    (invoice.get("amount_paid") if status == "paid" else invoice.get("amount_due"))
                    or 0
                )
                / 100,
                "status": "paid" if status == "paid" else "failed",
            }
        )
    return {
        "accounts": pd.DataFrame(
            accounts,
            columns=[
                "account_id",
                "domain",
                "created_at",
                "cancelled_at",
                "plan",
                "seats",
                "billing_cycle",
                "renews_at",
                "cancel_scheduled",
            ],
        ),
        "invoices": pd.DataFrame(invoice_rows, columns=["account_id", "date", "amount", "status"]),
    }


def hubspot_tables(client: httpx.Client, churn_property: str | None) -> dict[str, pd.DataFrame]:
    """Companies and tickets. Without a chosen churn property no account is marked cancelled."""
    wanted = ["createdate", "industry", "domain", *([churn_property] if churn_property else [])]
    companies = list(
        _hubspot_pages(client, "/crm/v3/objects/companies", {"properties": ",".join(wanted)})
    )
    tickets = list(
        _hubspot_pages(
            client,
            "/crm/v3/objects/tickets",
            {"properties": "subject,content,createdate", "associations": "companies"},
        )
    )
    accounts = [
        {
            "account_id": str(c["id"]),
            "created_at": _day((c.get("properties") or {}).get("createdate") or c.get("createdAt")),
            "domain": _domain((c.get("properties") or {}).get("domain")),
            "cancelled_at": _day((c.get("properties") or {}).get(churn_property))
            if churn_property
            else "",
            "industry": (c.get("properties") or {}).get("industry") or "",
        }
        for c in companies
    ]
    known = {a["account_id"] for a in accounts}
    rows = []
    for ticket in tickets:
        links = (((ticket.get("associations") or {}).get("companies") or {}).get("results")) or []
        company = str(links[0]["id"]) if links else None
        if company not in known:
            continue
        props = ticket.get("properties") or {}
        rows.append(
            {
                "account_id": company,
                "created_at": _day(props.get("createdate") or ticket.get("createdAt")),
                "subject": props.get("subject") or "",
                "body": props.get("content") or "",
            }
        )
    return {
        "accounts": pd.DataFrame(
            accounts, columns=["account_id", "domain", "created_at", "cancelled_at", "industry"]
        ),
        "tickets": pd.DataFrame(rows, columns=["account_id", "created_at", "subject", "body"]),
    }


# Personal mailboxes say nothing about which company a customer is, so they never match.
FREEMAIL = {
    "gmail.com",
    "googlemail.com",
    "yahoo.com",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "msn.com",
    "icloud.com",
    "me.com",
    "aol.com",
    "proton.me",
    "protonmail.com",
    "gmx.com",
    "yandex.com",
    "mail.com",
    "zoho.com",
}


def _domain(value: Any) -> str:
    """A bare lowercase domain from an email address or a website, or "" when there is none."""
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = text.rpartition("@")[2]
    text = text.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
    text = text.removeprefix("www.")
    return text if "." in text else ""


def merge(
    billing: dict[str, pd.DataFrame], crm: dict[str, pd.DataFrame]
) -> tuple[dict[str, pd.DataFrame], dict[str, str], dict]:
    """Billing accounts enriched with CRM industry and tickets.

    A billing record that already carries its CRM account ID (Zoho Billing ↔ Zoho CRM) links
    directly; the rest match by company domain. Billing stays the record of who cancelled. A
    domain shared by several CRM companies, and personal mailboxes, are not matched. Returns the
    tables, the billing → CRM account links and match statistics.
    """
    companies = crm["accounts"]
    accounts = billing["accounts"].copy()
    known = set(companies["account_id"].astype(str))
    links: dict[str, str] = {}
    by_id = 0
    if "crm_id" in accounts:
        for account, crm_id in zip(accounts["account_id"], accounts["crm_id"], strict=True):
            if isinstance(crm_id, str) and crm_id in known:
                links[str(account)] = crm_id
        by_id = len(links)
    usable = companies[(companies["domain"] != "") & ~companies["domain"].isin(FREEMAIL)]
    counts = usable["domain"].value_counts()
    unique = usable[usable["domain"].map(counts) == 1].set_index("domain")["account_id"]
    for account, domain in zip(accounts["account_id"], accounts["domain"], strict=True):
        if str(account) not in links and domain in unique.index:
            links[str(account)] = str(unique[domain])
    industry = dict(zip(companies["account_id"], companies["industry"], strict=True))
    accounts["industry"] = [industry.get(links.get(a, ""), "") for a in accounts["account_id"]]
    reverse = {company: account for account, company in links.items()}
    tickets = crm.get("tickets", pd.DataFrame(columns=["account_id", "created_at"])).copy()
    tickets = tickets[tickets["account_id"].isin(reverse)]
    tickets["account_id"] = tickets["account_id"].map(reverse)
    total = int(len(accounts))
    stats = {
        "billing_accounts": total,
        "matched": len(links),
        "matched_by_crm_id": by_id,
        "rate": round(len(links) / total, 4) if total else 0.0,
        "ambiguous_domains": int((counts > 1).sum()),
    }
    return {**billing, "accounts": accounts, "tickets": tickets}, links, stats


def _strip_domains(tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Domains and CRM IDs are only for matching; they are identifiers, never saved to a source."""
    return {
        name: frame.drop(columns=["domain", "crm_id"], errors="ignore")
        for name, frame in tables.items()
    }


def _verify(client: httpx.Client, provider: str) -> None:
    path = "/v1/customers" if provider == "stripe" else "/crm/v3/objects/companies"
    _get(client, path, {"limit": 1})


def _last_counts(settings: Settings | None, connection: Connection) -> dict | None:
    if settings is None or connection.last_source_id is None:
        return None
    try:
        manifest = sources.read_source(settings, connection.last_source_id)
    except WorkflowError:
        return None
    return {**manifest.get("counts", {}), "cancelled": manifest.get("cancelled_accounts")}


def _last(settings: Settings | None, connection: Connection, key: str) -> Any:
    if settings is None or connection.last_source_id is None:
        return None
    try:
        return sources.read_source(settings, connection.last_source_id).get(key)
    except WorkflowError:
        return None


def _last_match(settings: Settings | None, connection: Connection) -> dict | None:
    match = _last(settings, connection, "match")
    return match if isinstance(match, dict) else None


def public(connection: Connection, settings: Settings | None = None) -> dict:
    return {
        "id": str(connection.id),
        "provider": connection.provider,
        "label": connection.label,
        "created_at": connection.created_at.isoformat(),
        "last_synced_at": connection.last_synced_at.isoformat()
        if connection.last_synced_at
        else None,
        "last_source_id": str(connection.last_source_id) if connection.last_source_id else None,
        "last_error": connection.last_error,
        "write_enabled": bool(connection.write_enabled),
        "last_counts": _last_counts(settings, connection),
        "last_match": _last_match(settings, connection),
        "last_notes": [str(n) for n in _last(settings, connection, "notes") or []],
        "role": role_of(connection.provider),
        "churn_property": connection.churn_property,
        "enrich_connection_id": str(connection.enrich_connection_id)
        if connection.enrich_connection_id
        else None,
    }


def create(
    session: Session,
    settings: Settings,
    provider: str,
    label: str,
    secret: str | None = None,
    fields: dict[str, str] | None = None,
) -> dict:
    """Verify a credential with one read, then store it encrypted. Nothing is synced yet."""
    if provider not in PROVIDERS:
        raise WorkflowError("Unsupported provider.")
    fernet = _fernet(settings)
    if provider in SINGLE_SECRET:
        if not secret:
            raise WorkflowError(f"Paste the {name_of(provider)} key.")
        with _client(settings, provider, secret) as client:
            _verify(client, provider)
        stored = secret
    else:
        from customer_intelligence.services import razorpay, zoho

        given = {k: v.strip() for k, v in (fields or {}).items() if v and v.strip()}
        credential = (
            razorpay.connect(settings, given)
            if provider == "razorpay"
            else zoho.connect(settings, provider, given)
        )
        stored = json.dumps(credential)
    connection = Connection(
        provider=provider, label=label, secret_ciphertext=fernet.encrypt(stored.encode()).decode()
    )
    session.add(connection)
    session.commit()
    session.refresh(connection)
    return public(connection)


def list_connections(session: Session, settings: Settings | None = None) -> list[dict]:
    return [
        public(c, settings)
        for c in session.exec(select(Connection).order_by(col(Connection.created_at).desc())).all()
    ]


def _decrypt(settings: Settings, connection: Connection) -> str:
    try:
        return _fernet(settings).decrypt(connection.secret_ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise WorkflowError("The stored credential can't be decrypted with this key.", 409) from exc


def credential(settings: Settings, connection: Connection) -> dict[str, str]:
    """The stored JSON credential of a multi-field provider (Razorpay, Zoho)."""
    try:
        value = json.loads(_decrypt(settings, connection))
    except ValueError as exc:
        raise WorkflowError("The stored credential is unreadable; reconnect.", 409) from exc
    if not isinstance(value, dict):
        raise WorkflowError("The stored credential is unreadable; reconnect.", 409)
    return {str(k): str(v) for k, v in value.items()}


def _fetch(settings: Settings, connection: Connection) -> tuple[dict[str, pd.DataFrame], list[str]]:
    """The provider's tables plus notes about anything it couldn't read."""
    provider = connection.provider
    if provider == "stripe":
        with _client(settings, provider, _decrypt(settings, connection)) as client:
            return stripe_tables(client), []
    if provider == "hubspot":
        with _client(settings, provider, _decrypt(settings, connection)) as client:
            return hubspot_tables(client, connection.churn_property), []
    from customer_intelligence.services import razorpay, zoho

    stored = credential(settings, connection)
    if provider == "razorpay":
        return razorpay.tables(settings, stored), []
    if provider == "zoho_crm":
        return zoho.crm_tables(settings, stored, connection.churn_property)
    if provider == "zoho_billing":
        return zoho.billing_tables(settings, stored), []
    raise WorkflowError("Unsupported provider.")


def sync(session: Session, settings: Settings, connection_id: UUID) -> dict:
    connection = session.get(Connection, connection_id)
    if connection is None:
        raise WorkflowError("Connection not found.", 404)
    links: dict[str, str] = {}
    extra: dict[str, Any] = {"connection_id": str(connection.id)}
    try:
        tables, notes = _fetch(settings, connection)
        if tables["accounts"].empty:
            raise WorkflowError("The provider returned no accounts.")
        partner = (
            session.get(Connection, connection.enrich_connection_id)
            if connection.enrich_connection_id
            else None
        )
        if partner is not None:
            try:
                crm, crm_notes = _fetch(settings, partner)
            except WorkflowError as exc:
                raise WorkflowError(
                    f"{partner.label} ({name_of(partner.provider)}): {exc}", exc.status_code
                ) from exc
            tables, links, extra["match"] = merge(tables, crm)
            notes += crm_notes
            extra["enriched_with"] = str(partner.id)
        if notes:
            extra["notes"] = notes
        manifest = sources._save(
            settings,
            f"{connection.label} ({name_of(connection.provider)})",
            f"{connection.provider}+{partner.provider}" if partner else connection.provider,
            _strip_domains(tables),
            extra,
        )
    except WorkflowError as exc:
        connection.last_error = str(exc)[:500]
        session.add(connection)
        session.commit()
        raise
    if links:
        path = sources._directory(settings, UUID(manifest["id"])) / "links.json"
        path.write_text(json.dumps(links))
    connection.last_error = None
    connection.last_synced_at = datetime.now(UTC)
    connection.last_source_id = UUID(manifest["id"])
    session.add(connection)
    session.commit()
    return manifest


def date_properties(session: Session, settings: Settings, connection_id: UUID) -> list[dict]:
    """CRM account/company date fields, for choosing which one records churn."""
    connection = session.get(Connection, connection_id)
    if connection is None:
        raise WorkflowError("Connection not found.", 404)
    if role_of(connection.provider) != "crm":
        raise WorkflowError("Only CRM connections have a churn field.")
    if connection.provider == "zoho_crm":
        from customer_intelligence.services import zoho

        found = zoho.date_fields(settings, credential(settings, connection))
    else:
        with _client(settings, "hubspot", _decrypt(settings, connection)) as client:
            body = _get(client, "/crm/v3/properties/companies", {})
        found = [
            {"name": str(p["name"]), "label": str(p.get("label") or p["name"])}
            for p in body.get("results") or []
            if isinstance(p, dict) and p.get("name") and p.get("type") in ("date", "datetime")
        ]
    return sorted(found, key=lambda p: p["label"].lower())


def configure(
    session: Session, settings: Settings, connection_id: UUID, changes: dict[str, Any]
) -> dict:
    """Set a CRM's churn field or a billing → CRM link (only the given keys)."""
    connection = session.get(Connection, connection_id)
    if connection is None:
        raise WorkflowError("Connection not found.", 404)
    role = role_of(connection.provider)
    if "churn_property" in changes:
        field = changes["churn_property"]
        if role != "crm":
            raise WorkflowError("Only CRM connections have a churn field.")
        if field is not None and field not in {
            p["name"] for p in date_properties(session, settings, connection_id)
        }:
            raise WorkflowError("Choose one of this CRM's date fields.")
        connection.churn_property = field
    if "enrich_connection_id" in changes:
        target = changes["enrich_connection_id"]
        if role != "billing":
            raise WorkflowError("Only a billing connection can be matched with a CRM.")
        if target is not None:
            partner = session.get(Connection, target)
            if partner is None or role_of(partner.provider) != "crm":
                raise WorkflowError("Choose a CRM connection to match with.", 404)
        connection.enrich_connection_id = target
    session.add(connection)
    session.commit()
    session.refresh(connection)
    return public(connection, settings)


def company_links(session: Session, settings: Settings, crm_id: UUID) -> dict[str, str]:
    """Billing account → CRM account, from each linked billing connection's latest sync."""
    links: dict[str, str] = {}
    partners = session.exec(
        select(Connection).where(Connection.enrich_connection_id == crm_id)
    ).all()
    for billing in partners:
        if billing.last_source_id is None:
            continue
        path = sources._directory(settings, billing.last_source_id) / "links.json"
        if path.exists():
            loaded = json.loads(path.read_text())
            if isinstance(loaded, dict):
                links.update({str(k): str(v) for k, v in loaded.items()})
    return links


def set_write(session: Session, connection_id: UUID, enabled: bool) -> dict:
    connection = session.get(Connection, connection_id)
    if connection is None:
        raise WorkflowError("Connection not found.", 404)
    if enabled and role_of(connection.provider) != "crm":
        raise WorkflowError("Only CRM connections can create tasks.")
    connection.write_enabled = enabled
    session.add(connection)
    session.commit()
    session.refresh(connection)
    return public(connection)


def create_tasks(
    session: Session,
    settings: Settings,
    connection: Connection,
    accounts: list[str],
    title: str,
    instructions: str,
) -> dict:
    """One task per CRM account for an approved play. Billing-anchored accounts reach their CRM
    account through the latest match; anything that isn't a CRM account ID is skipped."""
    links = company_links(session, settings, connection.id)
    known = _crm_accounts(settings, connection)
    targets: list[str] = []
    skipped = 0
    for customer_id in accounts:
        account = customer_id.rpartition("@")[0] or customer_id
        # Only real CRM records: a matched billing account, or an ID from the CRM's own sync.
        # (Billing IDs can be numeric too, so "looks like an ID" is never enough.)
        target = links.get(account) or (account if account in known else None)
        if target:
            targets.append(target)
        else:
            skipped += 1  # stays in the CSV export
    if connection.provider == "zoho_crm":
        from customer_intelligence.services import zoho

        written, failed = zoho.create_tasks(
            settings, credential(settings, connection), targets, title, instructions
        )
    else:
        written, failed = _hubspot_tasks(
            settings, _decrypt(settings, connection), targets, title, instructions
        )
    return {
        "destination": connection.provider,
        "written": written,
        "skipped": skipped,
        "failed": failed,
    }


def _crm_accounts(settings: Settings, connection: Connection) -> set[str]:
    """Account IDs from the CRM connection's latest sync (empty before its first sync)."""
    if connection.last_source_id is None:
        return set()
    try:
        frame = sources.load_tables(settings, connection.last_source_id)["accounts"]
    except (WorkflowError, KeyError):
        return set()
    return set(frame["account_id"].astype(str))


def _hubspot_tasks(
    settings: Settings, secret: str, companies: list[str], title: str, instructions: str
) -> tuple[int, int]:
    due = int((datetime.now(UTC) + timedelta(days=2)).timestamp() * 1000)
    written = failed = 0
    with _client(settings, "hubspot", secret) as client:
        for company in companies:
            try:
                response = client.post(
                    "/crm/v3/objects/tasks",
                    json={
                        "properties": {
                            "hs_task_subject": title[:200],
                            "hs_task_body": instructions[:4000],
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
    return written, failed


def secret_for(session: Session, settings: Settings, connection: Connection) -> str:
    try:
        return _fernet(settings).decrypt(connection.secret_ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise WorkflowError("The stored credential can't be decrypted with this key.", 409) from exc


def delete(session: Session, connection_id: UUID) -> None:
    connection = session.get(Connection, connection_id)
    if connection is None:
        raise WorkflowError("Connection not found.", 404)
    from customer_intelligence.services.autonomy import detach_connection

    detach_connection(session, connection_id)
    for linked in session.exec(
        select(Connection).where(Connection.enrich_connection_id == connection_id)
    ).all():
        linked.enrich_connection_id = None
        session.add(linked)
    session.delete(connection)
    session.commit()
