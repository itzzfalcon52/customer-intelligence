import httpx
from fastapi.testclient import TestClient
from pydantic import SecretStr

from customer_intelligence.core.config import Settings
from customer_intelligence.main import create_app


def test_account_session_scopes_all_resources(tmp_path):
    settings = Settings(
        _env_file=None,
        auth_mode="account",
        auth_bridge_secret=SecretStr("s" * 64),
        data_directory=tmp_path,
    )
    app = create_app(settings)

    def identity(request):
        assert request.headers["authorization"] == "Bearer " + "s" * 64
        cookie = request.headers["cookie"]
        assert "unrelated" not in cookie
        if "expired" in cookie:
            return httpx.Response(401)
        return httpx.Response(200, json={"user_id": "second" if "second" in cookie else "first"})

    with TestClient(app) as client:
        app.state.auth_client = httpx.AsyncClient(transport=httpx.MockTransport(identity))
        assert client.get("/api/v1/datasets").status_code == 401
        assert client.get("/api/v1/health").status_code == 200
        first = {"Cookie": "better-auth.session_token=first; unrelated=do-not-forward"}
        assert (
            client.post(
                "/api/v1/datasets/upload",
                headers={**first, "Origin": "http://127.0.0.1:9999"},
                files={"file": ("no.csv", b"a,b\n1,2")},
            ).status_code
            == 403
        )
        second = {"Cookie": "better-auth.session_token=second"}
        response = client.post(
            "/api/v1/datasets/upload",
            headers=first,
            files={"file": ("private.csv", b"id,feature,churn\nA,1,No\nB,2,Yes\n")},
        )
        assert response.status_code == 201
        dataset = response.json()["id"]
        assert len(client.get("/api/v1/datasets", headers=first).json()) == 1
        assert client.get("/api/v1/datasets", headers=second).json() == []
        assert client.get(f"/api/v1/datasets/{dataset}/profile", headers=second).status_code == 404
        assert client.delete(f"/api/v1/datasets/{dataset}", headers=second).status_code == 404
        assert (
            client.get(
                "/api/v1/datasets", headers={"Cookie": "better-auth.session_token=expired"}
            ).status_code
            == 401
        )
        assert client.get("/api/v1/datasets", headers=first).headers["cache-control"] == "no-store"
        assert not (tmp_path / "metadata.db").exists()


def test_account_service_fails_closed(tmp_path):
    settings = Settings(
        _env_file=None,
        auth_mode="account",
        auth_bridge_secret=SecretStr("s" * 64),
        data_directory=tmp_path,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        app.state.auth_client = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(503))
        )
        assert (
            client.get(
                "/api/v1/datasets", headers={"Cookie": "better-auth.session_token=valid"}
            ).status_code
            == 503
        )
