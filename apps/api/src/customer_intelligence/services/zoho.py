"""Zoho CRM (CRM) and Zoho Billing (billing) through a Zoho "Self Client".

Connecting: in Zoho's API Console the admin creates a Self Client, generates a one-time code with
the read scopes listed in the connector guide, and pastes client ID, client secret, code and
their data-centre region. Holdfast exchanges the code once for a refresh token; the code is never
stored. Each sync exchanges the refresh token for a one-hour access token, kept only in memory.

Zoho CRM: Accounts (paged 200 at a time, `page_token` past 2,000 records), Cases as support
tickets, a chosen Accounts date field as the churn date, and Tasks for approved plays.
Zoho Billing: customers, subscriptions and invoices for one organisation; a customer that Zoho
already linked to a CRM account (`zcrm_account_id`) is matched by that ID before email domain.
"""

import re
from collections import defaultdict
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import httpx
import pandas as pd

from customer_intelligence.core.config import Settings
from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.services import connectors

# Data-centre region → accounts server. Holdfast asks which one the Zoho account lives in.
REGIONS = {
    "in": "https://accounts.zoho.in",
    "com": "https://accounts.zoho.com",
    "eu": "https://accounts.zoho.eu",
    "au": "https://accounts.zoho.com.au",
    "jp": "https://accounts.zoho.jp",
    "ca": "https://accounts.zohocloud.ca",
    "sa": "https://accounts.zoho.sa",
}
API_HOST = re.compile(r"^(www\.)?zohoapis\.[a-z.]+$|^(www\.)?zohocloud\.ca$")
PER_PAGE = 200
BILLING_ENDED = {"cancelled", "expired", "cancelled_from_dunning"}
BILLING_FAILED = {"overdue", "unpaid"}
ORG_HEADER = "X-com-zoho-subscriptions-organizationid"


def _accounts_base(settings: Settings, region: str) -> str:
    if settings.zoho_accounts_base:
        return settings.zoho_accounts_base
    if region not in REGIONS:
        raise WorkflowError("Choose the region your Zoho account is in (India is zoho.in).")
    return REGIONS[region]


def _token(settings: Settings, region: str, data: dict[str, str]) -> dict[str, Any]:
    """POST to Zoho's token endpoint. Zoho reports bad codes as HTTP 200 with an `error`."""
    try:
        with httpx.Client(
            base_url=_accounts_base(settings, region),
            timeout=30,
            transport=connectors.transport,
            follow_redirects=False,
        ) as client:
            response = client.post("/oauth/v2/token", data=data)
    except httpx.HTTPError as exc:
        raise WorkflowError("Zoho could not be reached.", 502) from exc
    try:
        body = response.json()
    except ValueError:
        body = {}
    error = str(body.get("error") or "") if isinstance(body, dict) else ""
    if response.status_code >= 400 or error or not isinstance(body, dict):
        messages = {
            "invalid_code": "The one-time code is invalid or expired (they last a few "
            "minutes and work once). Generate a new code and try again.",
            "invalid_client": "Zoho didn't recognise the client ID or secret, or the region is "
            "wrong. Check both and the region your Zoho account is in.",
            "invalid_client_secret": "The client secret is wrong. Copy it again from the Self "
            "Client.",
        }
        raise WorkflowError(
            messages.get(error, "Zoho rejected the credentials. Check them and the region."),
            400,
        )
    return body


def _api_domain(settings: Settings, value: Any) -> str:
    if settings.zoho_api_base:
        return settings.zoho_api_base
    domain = str(value or "")
    host = urlparse(domain).hostname or ""
    if urlparse(domain).scheme != "https" or not API_HOST.match(host):
        raise WorkflowError("Zoho returned an unexpected API address.", 502)
    return f"https://{host}"


def _access(settings: Settings, credential: dict[str, str]) -> tuple[str, str]:
    body = _token(
        settings,
        credential["region"],
        {
            "grant_type": "refresh_token",
            "client_id": credential["client_id"],
            "client_secret": credential["client_secret"],
            "refresh_token": credential["refresh_token"],
        },
    )
    token = body.get("access_token")
    if not isinstance(token, str) or not token:
        raise WorkflowError("Zoho did not return an access token; reconnect.", 400)
    return token, _api_domain(settings, body.get("api_domain") or credential.get("api_domain"))


def _client(
    settings: Settings, credential: dict[str, str], headers: dict[str, str] | None = None
) -> httpx.Client:
    token, api = _access(settings, credential)
    return httpx.Client(
        base_url=api,
        headers={"Authorization": f"Zoho-oauthtoken {token}", **(headers or {})},
        timeout=30,
        transport=connectors.transport,
        follow_redirects=False,
    )


def connect(settings: Settings, provider: str, fields: dict[str, str]) -> dict[str, str]:
    """Exchange the one-time code, verify one read, and return what to store (no code)."""
    region = fields.get("region", "")
    missing = [k for k in ("client_id", "client_secret", "code") if not fields.get(k)]
    if region not in REGIONS or missing:
        raise WorkflowError(
            "Enter the region, client ID, client secret and the one-time code from the "
            "Zoho API Console."
        )
    body = _token(
        settings,
        region,
        {
            "grant_type": "authorization_code",
            "client_id": fields["client_id"],
            "client_secret": fields["client_secret"],
            "code": fields["code"],
        },
    )
    refresh = body.get("refresh_token")
    if not isinstance(refresh, str) or not refresh:
        raise WorkflowError(
            "Zoho returned no refresh token. Generate a fresh code (codes work only once).", 400
        )
    credential = {
        "region": region,
        "client_id": fields["client_id"],
        "client_secret": fields["client_secret"],
        "refresh_token": refresh,
        "api_domain": _api_domain(settings, body.get("api_domain")),
    }
    if provider == "zoho_crm":
        with _client(settings, credential) as client:
            connectors._get(client, "/crm/v8/Accounts", {"fields": "Account_Name", "per_page": 1})
    else:
        credential["organization_id"] = _organization(
            settings, credential, fields.get("organization_id")
        )
        with _client(settings, credential, {ORG_HEADER: credential["organization_id"]}) as client:
            connectors._get(client, "/billing/v1/customers", {"per_page": 1})
    return credential


# --------------------------------------------------------------------------- Zoho CRM


def _crm_pages(client: httpx.Client, path: str, params: dict[str, Any]) -> Iterator[dict]:
    page, token = 1, None
    for _ in range(connectors.MAX_PAGES):
        query = {
            **params,
            "per_page": PER_PAGE,
            **({"page_token": token} if token else {"page": page}),
        }
        body = connectors._get(client, path, query)
        yield from (r for r in body.get("data") or [] if isinstance(r, dict))
        info = body.get("info") or {}
        if not info.get("more_records"):
            return
        # Past 2,000 records Zoho requires the page token it returns.
        token, page = info.get("next_page_token") or None, page + 1


def _lookup_id(value: Any) -> str | None:
    if isinstance(value, dict) and value.get("id"):
        return str(value["id"])
    return None


def crm_tables(
    settings: Settings, credential: dict[str, str], churn_field: str | None
) -> tuple[dict[str, pd.DataFrame], list[str]]:
    notes: list[str] = []
    fields = [
        "Account_Name",
        "Website",
        "Industry",
        "Created_Time",
        *([churn_field] if churn_field else []),
    ]
    with _client(settings, credential) as client:
        records = list(_crm_pages(client, "/crm/v8/Accounts", {"fields": ",".join(fields)}))
        try:
            cases = list(
                _crm_pages(
                    client,
                    "/crm/v8/Cases",
                    {"fields": "Subject,Description,Created_Time,Account_Name"},
                )
            )
        except WorkflowError as exc:
            if exc.status_code >= 500:
                raise
            cases = []
            notes.append(f"Zoho CRM Cases weren't read, so there are no support tickets: {exc}")
    day = connectors._day
    accounts = [
        {
            "account_id": str(r["id"]),
            "domain": connectors._domain(r.get("Website")),
            "created_at": day(r.get("Created_Time")),
            "cancelled_at": day(r.get(churn_field)) if churn_field else "",
            "industry": r.get("Industry") or "",
        }
        for r in records
        if r.get("id")
    ]
    known = {a["account_id"] for a in accounts}
    tickets = [
        {
            "account_id": account,
            "created_at": day(c.get("Created_Time")),
            "subject": c.get("Subject") or "",
            "body": c.get("Description") or "",
        }
        for c in cases
        if (account := _lookup_id(c.get("Account_Name"))) in known
    ]
    return {
        "accounts": pd.DataFrame(
            accounts, columns=["account_id", "domain", "created_at", "cancelled_at", "industry"]
        ),
        "tickets": pd.DataFrame(tickets, columns=["account_id", "created_at", "subject", "body"]),
    }, notes


def date_fields(settings: Settings, credential: dict[str, str]) -> list[dict]:
    with _client(settings, credential) as client:
        body = connectors._get(client, "/crm/v8/settings/fields", {"module": "Accounts"})
    return [
        {"name": str(f["api_name"]), "label": str(f.get("field_label") or f["api_name"])}
        for f in body.get("fields") or []
        if isinstance(f, dict) and f.get("api_name") and f.get("data_type") in ("date", "datetime")
    ]


def create_tasks(
    settings: Settings,
    credential: dict[str, str],
    accounts: list[str],
    title: str,
    instructions: str,
) -> tuple[int, int]:
    """One Zoho CRM Task per account, related to it through What_Id."""
    due = (datetime.now(UTC) + timedelta(days=2)).date().isoformat()
    written = failed = 0
    with _client(settings, credential) as client:
        for start in range(0, len(accounts), 100):  # Zoho inserts up to 100 records per call
            batch = accounts[start : start + 100]
            try:
                response = client.post(
                    "/crm/v8/Tasks",
                    json={
                        "data": [
                            {
                                "Subject": title[:255],
                                "Description": instructions[:4000],
                                "Due_Date": due,
                                "Status": "Not Started",
                                "What_Id": {"id": account},
                                "$se_module": "Accounts",
                            }
                            for account in batch
                        ]
                    },
                )
            except httpx.HTTPError:
                failed += len(batch)
                continue
            if response.status_code in (401, 403):
                raise WorkflowError(
                    "Zoho CRM refused task creation; add the ZohoCRM.modules.tasks.CREATE scope "
                    "and reconnect.",
                    400,
                )
            try:
                results = response.json().get("data") or []
            except ValueError:
                results = []
            ok = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "success")
            written += ok
            failed += len(batch) - ok
    return written, failed


# --------------------------------------------------------------------------- Zoho Billing


def _organization(settings: Settings, credential: dict[str, str], chosen: str | None) -> str:
    with _client(settings, credential) as client:
        body = connectors._get(client, "/billing/v1/organizations", {})
    orgs = [o for o in body.get("organizations") or [] if isinstance(o, dict)]
    ids = {str(o.get("organization_id")): str(o.get("name") or "") for o in orgs}
    if chosen:
        if chosen not in ids:
            raise WorkflowError("That organisation ID isn't in this Zoho Billing account.")
        return chosen
    if len(ids) == 1:
        return next(iter(ids))
    if not ids:
        raise WorkflowError("This Zoho account has no Zoho Billing organisation.")
    listed = ", ".join(f"{name} ({oid})" for oid, name in ids.items())
    raise WorkflowError(
        f"This Zoho account has several Billing organisations; enter the ID of one: {listed}."
    )


def _billing_pages(client: httpx.Client, path: str, key: str) -> Iterator[dict]:
    for page in range(1, connectors.MAX_PAGES + 1):
        body = connectors._get(client, path, {"page": page, "per_page": PER_PAGE})
        yield from (r for r in body.get(key) or [] if isinstance(r, dict))
        if not (body.get("page_context") or {}).get("has_more_page"):
            return


def billing_tables(settings: Settings, credential: dict[str, str]) -> dict[str, pd.DataFrame]:
    headers = {ORG_HEADER: credential["organization_id"]}
    with _client(settings, credential, headers) as client:
        customers = list(_billing_pages(client, "/billing/v1/customers", "customers"))
        subscriptions = list(_billing_pages(client, "/billing/v1/subscriptions", "subscriptions"))
        invoices = list(_billing_pages(client, "/billing/v1/invoices", "invoices"))
    return build_billing(customers, subscriptions, invoices)


def build_billing(
    customers: list[dict], subscriptions: list[dict], invoices: list[dict]
) -> dict[str, pd.DataFrame]:
    day = connectors._day
    by_customer: dict[str, list[dict]] = defaultdict(list)
    for sub in subscriptions:
        if sub.get("customer_id"):
            by_customer[str(sub["customer_id"])].append(sub)
    accounts = []
    for customer in customers:
        customer_id = str(customer.get("customer_id") or "")
        if not customer_id:
            continue
        subs = sorted(
            by_customer.get(customer_id, []), key=lambda s: str(s.get("created_time") or "")
        )
        latest = subs[-1] if subs else {}
        ended = [s for s in subs if s.get("status") in BILLING_ENDED]
        cancelled = ""
        if subs and len(ended) == len(subs):
            cancelled = max(
                day(s.get("cancelled_date") or s.get("expires_at") or s.get("updated_time"))
                for s in ended
            )
        live = [s for s in subs if s.get("status") not in BILLING_ENDED]
        current = live[-1] if live else {}
        accounts.append(
            {
                "account_id": customer_id,
                "domain": connectors._domain(customer.get("email")),
                "crm_id": str(customer.get("zcrm_account_id") or ""),
                "renews_at": ""
                if cancelled
                else day(current.get("current_term_ends_at") or current.get("next_billing_at")),
                # "Non-renewing" means the customer already chose to stop at the term end.
                "cancel_scheduled": "yes" if current.get("status") == "non_renewing" else "",
                "created_at": day(customer.get("created_time")),
                "cancelled_at": cancelled,
                "plan": latest.get("plan_name") or latest.get("plan_code") or "",
                "seats": latest.get("quantity"),
                "billing_cycle": "annual"
                if str(latest.get("interval_unit") or "").startswith("year")
                else "monthly",
            }
        )
    known = {a["account_id"] for a in accounts}
    rows = []
    for invoice in invoices:
        owner = str(invoice.get("customer_id") or "")
        status = invoice.get("status")
        if owner not in known or status not in ({"paid"} | BILLING_FAILED):
            continue
        amount = (
            invoice.get("total")
            if status == "paid"
            else invoice.get("balance") or invoice.get("total")
        )
        rows.append(
            {
                "account_id": owner,
                "date": day(invoice.get("date") or invoice.get("created_time")),
                "amount": float(amount or 0),
                "status": "paid" if status == "paid" else "failed",
            }
        )
    return {
        "accounts": pd.DataFrame(
            accounts,
            columns=[
                "account_id",
                "domain",
                "crm_id",
                "created_at",
                "cancelled_at",
                "plan",
                "seats",
                "billing_cycle",
                "renews_at",
                "cancel_scheduled",
            ],
        ),
        "invoices": pd.DataFrame(rows, columns=["account_id", "date", "amount", "status"]),
    }
