import json
from uuid import UUID, uuid4

import pytest
from sqlmodel import Session

from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.schemas.workflow import ScoreRequest
from customer_intelligence.services import briefs, reasons
from customer_intelligence.services.scoring import read_customers, read_score, score_dataset
from tests.test_agent import provider, tools


def session_for(backend) -> Session:
    session = Session(backend["app"].state.engine)
    session.info["settings"] = backend["settings"]
    return session


@pytest.fixture(scope="module")
def batch(backend, trained) -> str:
    with session_for(backend) as session:
        return str(
            score_dataset(
                session,
                backend["settings"],
                ScoreRequest(
                    run_id=UUID(trained["run_id"]),
                    dataset_id=UUID(trained["dataset_id"]),
                    contact_count=40,
                    holdout_rate=0.2,
                    idempotency_key=uuid4(),
                ),
            )
        )


def deliver(result: dict) -> dict:
    return tools(("deliver_result", result))


def test_drivers_are_computed_for_the_contact_list_only(backend, batch):
    response = backend["client"].get(f"/api/v1/scores/{batch}/reasons")
    assert response.status_code == 200, response.text
    payload = response.json()
    settings = backend["settings"]
    customers = read_customers(
        read_score(UUID(batch), settings.data_directory), settings.data_directory
    )
    held = {c.customer_id for c in customers if c.group == "holdout"}
    ids = [a["customer_id"] for a in payload["accounts"]]
    assert len(ids) == 15 and not held & set(ids)
    top = payload["accounts"][0]
    assert top["drivers"] and all(d["risk_change"] > 0 for d in top["drivers"])
    assert {"feature", "value", "typical"} <= set(top["drivers"][0])
    assert "not causes" in payload["method"]


def test_notes_use_labels_and_withhold_unchecked_text(backend, batch):
    settings = backend["settings"]
    with session_for(backend) as session:
        accounts = reasons.drivers(session, settings, UUID(batch))["accounts"]
    first = accounts[0]["drivers"][0]
    client, captured = provider(
        [
            deliver(
                {
                    "notes": [
                        {
                            "label": "A1",
                            "note": f"{first['feature']} of {first['value']} stands out "
                            f"against a typical {first['typical']}.",
                        },
                        # An invented number and causal wording are both rejected.
                        {"label": "A2", "note": "Low tenure causes churn in 87.3% of accounts."},
                    ]
                }
            )
        ]
    )
    with client, session_for(backend) as session:
        payload = reasons.write_notes(session, settings, UUID(batch), client)
    sent = json.dumps(captured[0]["messages"])
    assert all(a["customer_id"] not in sent for a in accounts), "real IDs never leave the server"
    assert "A1" in sent
    items = payload["notes"]["items"]
    assert items[accounts[0]["customer_id"]]["source"] == "nemotron"
    rejected = items[accounts[1]["customer_id"]]
    assert rejected["source"] == "computed" and "87.3" in rejected["withheld_reason"]
    assert payload["notes"]["verified"] == 1 and payload["notes"]["withheld"] == 1
    # Accounts the model skipped fall back to computed text too.
    assert items[accounts[5]["customer_id"]]["text"].startswith(("Stands out", "No single"))
    cached = backend["client"].get(f"/api/v1/scores/{batch}/reasons").json()
    assert cached["notes"]["verified"] == 1


def test_brief_is_verified_and_maps_accounts_back(backend, batch):
    settings = backend["settings"]
    with session_for(backend) as session:
        accounts = reasons.drivers(session, settings, UUID(batch))["accounts"]
    client, captured = provider(
        [
            deliver(
                {
                    "headline": "Five accounts on today's list share unusually short tenure.",
                    "what_changed": [
                        "No input shifted beyond the stability rule of thumb.",
                        "Revenue will grow by 42% if you call them.",
                    ],
                    "call_first": [
                        {"label": "A1", "why": "Short tenure and a monthly contract stand out."},
                        {"label": "A9", "why": "Not in the evidence."},
                    ],
                    "recommended_play": {
                        "title": "Onboarding check-in",
                        "instructions": "Book a short call to review setup and goals.",
                    },
                    "caveats": ["Drivers are associations, not causes."],
                }
            )
        ]
    )
    with client, session_for(backend) as session:
        brief = briefs.write_brief(session, settings, UUID(batch), client)
        content, verification = brief.content, brief.verification
    sent = json.dumps(captured[0]["messages"])
    assert all(a["customer_id"] not in sent for a in accounts[:5])
    assert content["what_changed"] == ["No input shifted beyond the stability rule of thumb."]
    assert any(w.startswith("what changed") for w in verification["withheld"])
    assert [c["customer_id"] for c in content["call_first"]] == [accounts[0]["customer_id"]]
    assert content["recommended_play"]["title"] == "Onboarding check-in"
    latest = backend["client"].get("/api/v1/briefs/latest").json()
    assert latest["brief"]["id"] == str(brief.id) and latest["enabled"] is False


def test_kill_switch_stops_briefs(backend, batch):
    client_api = backend["client"]
    client_api.put("/api/v1/autonomy", json={"paused": True})
    client, captured = provider([])
    try:
        with client, session_for(backend) as session, pytest.raises(WorkflowError) as stopped:
            briefs.write_brief(session, backend["settings"], UUID(batch), client)
        assert stopped.value.status_code == 423 and captured == []
    finally:
        client_api.put("/api/v1/autonomy", json={})
    refused = client_api.post("/api/v1/briefs", json={"score_id": batch})
    assert refused.status_code == 422, "provider consent is required"


def test_role_capabilities_match_enforcement(backend):
    from customer_intelligence.core.permissions import CAPABILITIES, capabilities, denied

    for role in ("owner", "admin", "member", "viewer"):
        for (label, method, path), item in zip(CAPABILITIES, capabilities(role), strict=True):
            assert item["label"] == label
            assert item["allowed"] == (denied(role, method, path) is None)
    viewer = {c["label"]: c["allowed"] for c in capabilities("viewer")}
    assert viewer["Read everything and ask AI questions"] and not viewer["Delete data"]
    me = backend["client"].get("/api/v1/workspace/permissions").json()
    assert me["role"] == "owner" and all(c["allowed"] for c in me["capabilities"])


def test_a_stringified_play_is_parsed_then_validated():
    raw = {
        "headline": "Five accounts need a call today.",
        "what_changed": [],
        "call_first": [],
        "recommended_play": json.dumps(
            {"title": "Check-in", "instructions": "Ask how things are going.", "citation": None}
        ),
        "caveats": [],
    }
    assert briefs.DailyBrief.model_validate(raw).recommended_play.title == "Check-in"
    with pytest.raises(ValueError):
        briefs.DailyBrief.model_validate({**raw, "recommended_play": "call them"})
    assert reasons._check("Short tenure drives the risk score.", {}) == ["causal wording"]
