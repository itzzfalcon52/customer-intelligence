"""Email digests through Resend, sent after each scheduled check to people who opted in.

Privacy: an email carries what the Inbox headline shows (aggregates, the verified brief's
headline, pseudonymous call-first reasons and the recommended play) plus links into the app.
Customer IDs, rows and "Review first" lines never leave the app. Each person opts in for
themselves; in account mode the address is the signed-in account's own, so nobody can
subscribe someone else. One message per recipient, so addresses are never shared.
"""

import html
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
from sqlmodel import Session

from customer_intelligence.core.config import Settings
from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.core.identity import Identity
from customer_intelligence.models.operations import Brief, DigestItem
from customer_intelligence.models.workspace import WorkspaceFact

KEY = "email_digest"
MAX_RECIPIENTS = 50
TEST_COOLDOWN = timedelta(minutes=1)
# Tests replace this with httpx.MockTransport; production uses the default network transport.
transport: httpx.BaseTransport | None = None


def configured(settings: Settings) -> bool:
    return bool(settings.resend_api_key and settings.email_from)


def _state(session: Session) -> dict:
    fact = session.get(WorkspaceFact, KEY)
    return dict(fact.value) if fact else {}


def _save(session: Session, value: dict) -> None:
    fact = session.get(WorkspaceFact, KEY)
    if fact is None:
        fact = WorkspaceFact(key=KEY, value=value, source="user")
    else:
        fact.value, fact.source, fact.updated_at = value, "user", datetime.now(UTC)
    session.add(fact)
    session.commit()


def _mask(address: str) -> str:
    name, _, domain = address.partition("@")
    return f"{name[:1]}…@{domain}"


def subscription(session: Session, settings: Settings, identity: Identity) -> dict:
    recipients = _state(session).get("recipients", {})
    mine = recipients.get(identity.user_id)
    return {
        "configured": configured(settings),
        "enabled": mine is not None,
        "address": _mask(mine) if mine else None,
        "needs_address": identity.email is None,
        "recipients": len(recipients),
    }


def subscribe(
    session: Session,
    settings: Settings,
    identity: Identity,
    enabled: bool,
    address: str | None = None,
) -> dict:
    state = _state(session)
    recipients = dict(state.get("recipients", {}))
    if enabled:
        if not configured(settings):
            raise WorkflowError("Email isn't set up on this server yet.", 409)
        # Account mode always uses the account's own address; only private mode may give one.
        target = identity.email or address
        if not target or "@" not in target or len(target) > 320:
            raise WorkflowError("Enter the address the digest should go to.")
        if identity.user_id not in recipients and len(recipients) >= MAX_RECIPIENTS:
            raise WorkflowError(f"A workspace can email at most {MAX_RECIPIENTS} people.")
        recipients[identity.user_id] = target.strip()
    else:
        recipients.pop(identity.user_id, None)
    _save(session, {**state, "recipients": recipients})
    return subscription(session, settings, identity)


def _brief(session: Session, item: DigestItem) -> Brief | None:
    for link in item.links:
        href = str(link.get("href", ""))
        if href.startswith("/app?brief="):
            try:
                brief = session.get(Brief, UUID(href.split("=", 1)[1]))
            except ValueError:
                return None
            return brief if brief is not None and brief.status == "ready" else None
    return None


def compose(session: Session, settings: Settings, item: DigestItem) -> dict[str, str]:
    """Subject, HTML and plain text for one digest item. Every dynamic string is escaped."""
    origin = settings.auth_public_origin.rstrip("/")
    lines = [x for x in item.body.splitlines() if x.strip() and not x.startswith("Review first:")]
    brief = _brief(session, item)
    content: dict[str, Any] = brief.content if brief else {}
    calls = [c for c in content.get("call_first", []) if isinstance(c, dict)][:5]
    play = content.get("recommended_play") if isinstance(content, dict) else None
    links = [(str(x["label"]), origin + str(x["href"])) for x in item.links[:4]]
    settings_url = f"{origin}/app/settings#email"

    text = [item.title, "", *lines]
    if calls:
        text += ["", "Call first (names are in the app):"]
        text += [f"  {i}. {c.get('why', '')}" for i, c in enumerate(calls, 1)]
    if isinstance(play, dict) and play.get("title"):
        text += ["", f"Recommended play: {play['title']}", str(play.get("instructions", ""))]
    text += ["", *[f"{label}: {url}" for label, url in links]]
    text += ["", f"Stop these emails: {settings_url}"]

    e = html.escape
    ink, field, muted = "#141615", "#0f5a54", "#56615d"
    parts = [
        f'<div style="font-family:Arial,Helvetica,sans-serif;color:{ink};max-width:560px">',
        '<div style="height:6px;background:#d7262e"></div>',
        f'<h1 style="font-size:20px;margin:20px 0 12px">{e(item.title)}</h1>',
        *[f'<p style="margin:0 0 8px;font-size:14px;line-height:1.5">{e(x)}</p>' for x in lines],
    ]
    if calls:
        parts.append(
            f'<p style="margin:18px 0 6px;font-size:12px;letter-spacing:.06em;'
            f'text-transform:uppercase;color:{muted}">Call first · names are in the app</p><ol '
            'style="margin:0 0 8px;padding-left:20px;font-size:14px;line-height:1.5">'
            + "".join(f"<li>{e(str(c.get('why', '')))}</li>" for c in calls)
            + "</ol>"
        )
    if isinstance(play, dict) and play.get("title"):
        parts.append(
            f'<div style="margin:16px 0;padding:12px 14px;background:#f0f8f6">'
            f'<strong style="font-size:14px">{e(str(play["title"]))}</strong>'
            f'<p style="margin:6px 0 0;font-size:14px;line-height:1.5">'
            f"{e(str(play.get('instructions', '')))}</p></div>"
        )
    parts.append(
        '<p style="margin:18px 0">'
        + " ".join(
            f'<a href="{e(url, quote=True)}" style="display:inline-block;margin:0 8px 8px 0;'
            f"padding:9px 14px;background:{field};color:#f5f7f4;text-decoration:none;"
            f'font-size:14px">{e(label)}</a>'
            for label, url in links
        )
        + "</p>"
    )
    parts.append(
        f'<p style="font-size:12px;color:{muted}">Risk scores rank accounts; they are not '
        "guarantees. You get this because you turned on email digests. "
        f'<a href="{e(settings_url, quote=True)}" style="color:{muted}">Stop these emails</a>.'
        "</p></div>"
    )
    return {
        "subject": item.title[:180],
        "html": "".join(parts),
        "text": "\n".join(text),
        "unsubscribe": settings_url,
    }


def _send(settings: Settings, to: str, message: dict[str, str], key: str) -> int:
    assert settings.resend_api_key is not None and settings.email_from is not None
    with httpx.Client(
        base_url=settings.resend_api_base,
        timeout=15,
        transport=transport,
        follow_redirects=False,
        headers={"Authorization": f"Bearer {settings.resend_api_key.get_secret_value()}"},
    ) as client:
        response = client.post(
            "/emails",
            headers={"Idempotency-Key": key[:256]},
            json={
                "from": settings.email_from,
                "to": [to],
                "subject": message["subject"],
                "html": message["html"],
                "text": message["text"],
                "headers": {"List-Unsubscribe": f"<{message['unsubscribe']}>"},
            },
        )
    return response.status_code


def send_digest(session: Session, settings: Settings, item: DigestItem) -> None:
    """Email one digest item to everyone who opted in. Never twice; a failure is recorded."""
    if item.emailed_at is not None or not configured(settings):
        return
    recipients = _state(session).get("recipients", {})
    if not recipients:
        return
    message = compose(session, settings, item)
    sent, failed = 0, []
    for user_id, address in recipients.items():
        try:
            status = _send(settings, address, message, f"{item.id}:{user_id}")
        except httpx.HTTPError:
            failed.append("unreachable")
            continue
        if status < 300:
            sent += 1
        else:
            failed.append(f"HTTP {status}")
    item.emailed_at = datetime.now(UTC)
    item.emailed = f"sent to {sent}" + (f"; {len(failed)} failed ({failed[0]})" if failed else "")
    session.add(item)
    session.commit()


def send_test(session: Session, settings: Settings, identity: Identity) -> dict:
    """A sample digest to the requester's own subscribed address, at most once a minute."""
    state = _state(session)
    address = state.get("recipients", {}).get(identity.user_id)
    if not configured(settings) or not address:
        raise WorkflowError("Turn on the email digest first.", 409)
    last = state.get("tests", {}).get(identity.user_id)
    now = datetime.now(UTC)
    if last and now - datetime.fromisoformat(last) < TEST_COOLDOWN:
        raise WorkflowError("A test email was just sent. Try again in a minute.", 429)
    sample = DigestItem(
        kind="test",
        title="Holdfast test email",
        body="This is a test of your daily digest. Real digests arrive after each "
        "scheduled check, with the brief headline and the accounts to call first.",
        links=[{"label": "Open Holdfast", "href": "/app"}],
    )
    try:
        status = _send(settings, address, compose(session, settings, sample), f"test:{now}")
    except httpx.HTTPError as exc:
        raise WorkflowError("The email service could not be reached.", 502) from exc
    if status >= 300:
        raise WorkflowError(
            f"The email service refused the message (HTTP {status}). Check the sender domain "
            "is verified and the API key is valid.",
            502,
        )
    _save(
        session, {**state, "tests": {**state.get("tests", {}), identity.user_id: now.isoformat()}}
    )
    return {"sent_to": _mask(address)}
