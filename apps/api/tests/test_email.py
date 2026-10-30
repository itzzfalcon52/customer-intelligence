"""Email digests through a mocked Resend API: opt-in, privacy, idempotency and failures."""

import json
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr
from sqlmodel import Session

from customer_intelligence.core.identity import Identity
from customer_intelligence.core.permissions import denied
from customer_intelligence.models.operations import Brief, DigestItem
from customer_intelligence.services import autonomy, email

API_KEY = "re_synthetic_do_not_leak"


class FakeResend:
    def __init__(self) -> None:
        self.sent: list[httpx.Request] = []
        self.status = 200

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/emails" and request.method == "POST"
        assert request.headers["Authorization"] == f"Bearer {API_KEY}"
        self.sent.append(request)
        return httpx.Response(self.status, json={"id": str(len(self.sent))})

    def body(self, index: int = -1) -> dict:
        return json.loads(self.sent[index].content)


@pytest.fixture
def resend(backend, monkeypatch) -> FakeResend:
    fake = FakeResend()
    settings = backend["settings"]
    monkeypatch.setattr(settings, "resend_api_key", SecretStr(API_KEY))
    monkeypatch.setattr(settings, "email_from", "Holdfast <brief@holdfast.example>")
    monkeypatch.setattr(email, "transport", httpx.MockTransport(fake))
    yield fake
    backend["client"].put("/api/v1/email/subscription", json={"enabled": False})


def session_for(backend) -> Session:
    session = Session(backend["app"].state.engine)
    session.info["settings"] = backend["settings"]
    return session


def test_email_is_off_until_the_server_is_configured(backend):
    client = backend["client"]
    state = client.get("/api/v1/email/subscription").json()
    assert state["configured"] is False and state["enabled"] is False
    refused = client.put(
        "/api/v1/email/subscription", json={"enabled": True, "address": "me@example.com"}
    )
    assert refused.status_code == 409


def test_opt_in_needs_an_address_in_private_mode_and_masks_it(backend, resend):
    client = backend["client"]
    assert client.put("/api/v1/email/subscription", json={"enabled": True}).status_code == 400
    on = client.put(
        "/api/v1/email/subscription", json={"enabled": True, "address": "maya@example.com"}
    ).json()
    assert on["enabled"] and on["address"] == "m…@example.com" and on["needs_address"]
    assert "maya@" not in json.dumps(client.get("/api/v1/email/subscription").json())


def test_account_mode_always_uses_the_signed_in_address(backend, resend):
    with session_for(backend) as session:
        me = Identity("u1", None, "member", "real@company.example")
        state = email.subscribe(
            session, backend["settings"], me, True, address="someone-else@example.com"
        )
        assert state["address"] == "r…@company.example"
        assert email._state(session)["recipients"]["u1"] == "real@company.example"
        email.subscribe(session, backend["settings"], me, False)


def test_digest_is_emailed_once_without_customer_ids(backend, resend):
    client = backend["client"]
    client.put("/api/v1/email/subscription", json={"enabled": True, "address": "maya@example.com"})
    with session_for(backend) as session:
        brief = Brief(
            score_id=uuid4(),
            content={
                "headline": "40 accounts to contact",
                "call_first": [{"label": "A1", "why": "Logins fell <script>x</script> sharply"}],
                "recommended_play": {"title": "Check-in", "instructions": "Ask how it is going."},
            },
        )
        session.add(brief)
        item = DigestItem(
            kind="cycle",
            title="Nemotron brief: 40 accounts to contact",
            body="Scored 610 accounts.\nReview first: ACME-0757, ACME-0629",
            links=[
                {"label": "Read the brief", "href": f"/app?brief={brief.id}"},
                {"label": "Scores", "href": "/app/scores/abc"},
            ],
        )
        session.add(item)
        session.commit()
        session.refresh(item)
        autonomy.notify(session, backend["settings"], item)
        autonomy.notify(session, backend["settings"], item)  # a retry never emails twice
        session.refresh(item)
        assert item.emailed == "sent to 1" and item.emailed_at is not None
    assert len(resend.sent) == 1
    sent = resend.body()
    assert sent["to"] == ["maya@example.com"] and sent["from"].startswith("Holdfast")
    assert resend.sent[0].headers["Idempotency-Key"].startswith(str(item.id))
    everything = sent["html"] + sent["text"]
    assert "ACME-" not in everything, "customer IDs never leave the app"
    assert "Scored 610 accounts." in sent["text"] and "Check-in" in sent["text"]
    assert "<script>" not in sent["html"] and "&lt;script&gt;" in sent["html"]
    assert "/app/settings#email" in sent["headers"]["List-Unsubscribe"]
    assert API_KEY not in everything


def test_provider_failure_is_recorded_not_raised(backend, resend):
    resend.status = 500
    backend["client"].put(
        "/api/v1/email/subscription", json={"enabled": True, "address": "maya@example.com"}
    )
    with session_for(backend) as session:
        item = DigestItem(kind="cycle", title="Scheduled check", body="Scored 10.", links=[])
        session.add(item)
        session.commit()
        session.refresh(item)
        autonomy.notify(session, backend["settings"], item)
        session.refresh(item)
        assert item.emailed == "sent to 0; 1 failed (HTTP 500)"


def test_test_email_is_rate_limited_and_explains_refusals(backend, resend):
    client = backend["client"]
    assert client.post("/api/v1/email/test").status_code == 409
    client.put("/api/v1/email/subscription", json={"enabled": True, "address": "maya@example.com"})
    resend.status = 403
    refused = client.post("/api/v1/email/test")
    assert refused.status_code == 502 and "sender domain" in refused.text
    resend.status = 200
    sent = client.post("/api/v1/email/test")
    assert sent.status_code == 200 and sent.json()["sent_to"] == "m…@example.com"
    assert client.post("/api/v1/email/test").status_code == 429


def test_anyone_may_manage_their_own_digest():
    assert denied("viewer", "PUT", "/api/v1/email/subscription") is None
    assert denied("viewer", "POST", "/api/v1/email/test") is None
