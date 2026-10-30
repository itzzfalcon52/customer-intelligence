import hashlib
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlmodel import Session

from customer_intelligence.core.config import Settings
from customer_intelligence.core.permissions import denied
from customer_intelligence.main import create_app
from customer_intelligence.models.conversation import Conversation
from customer_intelligence.models.trace import AgentTrace
from customer_intelligence.services import privacy

CSV = b"id,feature,email_domain,churn\n" + b"".join(
    f"C{i},{i % 7},d{i % 3}.com,{'Yes' if i % 4 == 0 else 'No'}\n".encode() for i in range(40)
)
# cookie token -> (user, active organisation, role)
PEOPLE = {
    "alice": ("alice", None, "owner"),
    "alice-org": ("alice", "org1", "owner"),
    "bob-org": ("bob", "org1", "member"),
    "vic-org": ("vic", "org1", "viewer"),
}


@pytest.fixture
def account(tmp_path):
    settings = Settings(
        _env_file=None,
        auth_mode="account",
        auth_bridge_secret=SecretStr("s" * 64),
        data_directory=tmp_path,
    )
    app = create_app(settings)

    def identity(request: httpx.Request) -> httpx.Response:
        token = request.headers["cookie"].split("=", 1)[1]
        user, organization, role = PEOPLE[token]
        return httpx.Response(
            200, json={"user_id": user, "organization_id": organization, "role": role}
        )

    with TestClient(app) as client:
        app.state.auth_client = httpx.AsyncClient(transport=httpx.MockTransport(identity))

        def as_(token: str) -> dict:
            return {"Cookie": f"better-auth.session_token={token}"}

        yield client, as_, tmp_path


def test_role_rules():
    assert denied("owner", "PUT", "/api/v1/autonomy") is None
    assert denied("member", "POST", "/api/v1/jobs/train") is None
    assert denied("member", "PUT", "/api/v1/autonomy")
    assert denied("member", "POST", "/api/v1/actions/x/approve")
    assert denied("member", "DELETE", "/api/v1/datasets/x")
    assert denied("member", "GET", "/api/v1/connections") is None
    assert denied("member", "POST", "/api/v1/connections")
    assert denied("member", "POST", "/api/v1/connections/x/sync")
    assert denied("viewer", "POST", "/api/v1/jobs/train")
    assert denied("viewer", "GET", "/api/v1/datasets") is None
    assert denied("viewer", "POST", "/api/v1/assistant/messages") is None
    assert denied("stranger", "POST", "/api/v1/jobs/train")


def test_organisation_workspace_is_shared_separate_and_role_limited(account):
    client, as_, root = account
    personal = client.post(
        "/api/v1/datasets/upload", headers=as_("alice"), files={"file": ("mine.csv", CSV)}
    )
    assert personal.status_code == 201
    # The personal workspace keeps its original location (no migration needed).
    assert (root / "workspaces" / hashlib.sha256(b"alice").hexdigest()).exists()
    assert client.get("/api/v1/datasets", headers=as_("alice-org")).json() == []
    shared = client.post(
        "/api/v1/datasets/upload", headers=as_("bob-org"), files={"file": ("team.csv", CSV)}
    )
    assert shared.status_code == 201, shared.text
    assert [d["id"] for d in client.get("/api/v1/datasets", headers=as_("vic-org")).json()] == [
        shared.json()["id"]
    ]
    assert (root / "workspaces" / hashlib.sha256(b"org:org1").hexdigest()).exists()
    viewer = client.post(
        "/api/v1/datasets/upload", headers=as_("vic-org"), files={"file": ("x.csv", CSV)}
    )
    assert viewer.status_code == 403 and "Viewers" in viewer.json()["message"]
    member = client.put("/api/v1/autonomy", headers=as_("bob-org"), json={"paused": True})
    assert member.status_code == 403
    assert client.put("/api/v1/autonomy", headers=as_("alice-org"), json={}).status_code == 200
    me = client.get("/api/v1/workspace/identity", headers=as_("vic-org")).json()
    assert me == {
        "user_id": "vic",
        "organization_id": "org1",
        "role": "viewer",
        "can_manage": False,
        "can_edit": False,
    }
    assert client.get("/api/v1/audit", headers=as_("bob-org")).status_code == 403
    events = client.get("/api/v1/audit", headers=as_("alice-org")).json()
    actions = [(e["actor"], e["action"]) for e in events]
    assert ("bob", "POST /datasets/upload") in actions and ("alice", "PUT /autonomy") in actions
    assert all("vic" != e["actor"] for e in events), "refused requests change nothing"


def test_conversations_belong_to_their_owner(account):
    client, as_, root = account
    client.get("/api/v1/datasets", headers=as_("bob-org"))  # create the shared workspace
    directory = root / "workspaces" / hashlib.sha256(b"org:org1").hexdigest()
    from customer_intelligence.core.database import create_database_engine

    engine = create_database_engine(
        Settings(_env_file=None, data_directory=directory, auth_mode="private")
    )
    with Session(engine) as session:
        from uuid import uuid4

        mine = Conversation(dataset_id=uuid4(), owner_id="bob")
        session.add(mine)
        session.commit()
        mine_id = str(mine.id)
    engine.dispose()
    assert [
        c["id"]
        for c in client.get("/api/v1/assistant/conversations", headers=as_("bob-org")).json()
    ] == [mine_id]
    assert client.get("/api/v1/assistant/conversations", headers=as_("alice-org")).json() == []
    assert (
        client.get(
            f"/api/v1/assistant/conversations/{mine_id}", headers=as_("alice-org")
        ).status_code
        == 404
    )


def test_privacy_policy_withholds_columns(backend):
    client = backend["client"]
    upload = client.post("/api/v1/datasets/upload", files={"file": ("p.csv", CSV)}).json()
    saved = client.put(
        "/api/v1/privacy", json={"blocked_columns": ["feature"], "default_patterns": True}
    ).json()
    assert saved["blocked_columns"] == ["feature"]
    with Session(backend["app"].state.engine) as session:
        from customer_intelligence.models.dataset import Dataset
        from customer_intelligence.services.profiling import profile_dataset

        dataset = session.get(Dataset, __import__("uuid").UUID(upload["id"]))
        profile = privacy.ai_profile(session, profile_dataset(dataset, backend["settings"]))
        hidden = {c["name"] for c in profile["columns"] if c.get("withheld_by_privacy_policy")}
        # Explicitly listed, and caught by the default email pattern.
        assert hidden == {"feature", "email_domain"}
        assert all(c["numeric_summary"] is None for c in profile["columns"] if c["name"] in hidden)
        assert "preview" not in profile
    client.put("/api/v1/privacy", json={"blocked_columns": [], "default_patterns": True})


def test_usage_and_retention(backend):
    client = backend["client"]
    with Session(backend["app"].state.engine) as session:
        session.add(AgentTrace(kind="assistant", input_tokens=120, output_tokens=30))
        old = AgentTrace(kind="assistant", input_tokens=5, output_tokens=5)
        old.created_at = datetime.now(UTC) - timedelta(days=400)
        session.add(old)
        session.commit()
    usage = client.get("/api/v1/usage").json()
    assert usage["ai_tokens"]["input"] >= 120 and usage["ai_cost_usd"] is None
    assert client.get("/api/v1/usage?month=2026-13").status_code == 400
    assert client.post("/api/v1/retention-policy/apply").status_code == 409
    assert client.put("/api/v1/retention-policy", json={"days": 3}).status_code == 422
    client.put("/api/v1/retention-policy", json={"days": 365})
    result = client.post("/api/v1/retention-policy/apply").json()
    assert result["removed"]["traces"] >= 1
    assert client.get("/api/v1/retention-policy").json()["last_applied_at"]
    client.put("/api/v1/retention-policy", json={"days": None})
