import hashlib
from dataclasses import dataclass
from http.cookies import SimpleCookie

import httpx
from fastapi import HTTPException, Request

from customer_intelligence.core.config import Settings

ROLES = ("owner", "admin", "member", "viewer")


@dataclass(frozen=True)
class Identity:
    user_id: str
    organization_id: str | None = None
    role: str = "owner"  # a personal workspace's user owns it
    email: str | None = None  # the signed-in account's address (None in private CLI mode)


async def verify_identity(request: Request, settings: Settings) -> Identity:
    if not settings.auth_bridge_secret:
        raise HTTPException(503, "Account service is not configured.")
    raw = request.headers.get("cookie", "")
    if not raw or len(raw) > 16384:
        raise HTTPException(401, "Sign in to continue.")
    cookies: SimpleCookie = SimpleCookie()
    try:
        cookies.load(raw)
    except Exception:
        raise HTTPException(401, "Sign in to continue.") from None
    allowed = {"better-auth.session_token", "__Secure-better-auth.session_token"}
    forwarded = "; ".join(
        f"{name}={value.coded_value}" for name, value in cookies.items() if name in allowed
    )
    if not forwarded:
        raise HTTPException(401, "Sign in to continue.")
    try:
        response = await request.app.state.auth_client.get(
            settings.auth_service_url + "/internal/identity",
            headers={
                "Cookie": forwarded,
                "Authorization": "Bearer " + settings.auth_bridge_secret.get_secret_value(),
            },
        )
        if response.status_code == 401:
            raise HTTPException(401, "Sign in to continue.")
        response.raise_for_status()
        body = response.json()
        user_id = body.get("user_id")
        if not isinstance(user_id, str) or not user_id or len(user_id) > 200:
            raise ValueError("Invalid identity")
        organization = body.get("organization_id")
        if organization is not None and (
            not isinstance(organization, str) or len(organization) > 200
        ):
            raise ValueError("Invalid organisation")
        role = body.get("role", "owner")
        email = body.get("email")
        if not isinstance(email, str) or "@" not in email or len(email) > 320:
            email = None
        # Unknown roles get the least access rather than an error.
        return Identity(user_id, organization or None, role if role in ROLES else "viewer", email)
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503, "Account service is unavailable. Please try again.") from None


def scoped_settings(settings: Settings, identity: Identity | str) -> Settings:
    """Personal workspaces hash the user ID (unchanged, so existing data stays in place);
    organisation workspaces hash a separate namespace, so the two can never collide."""
    if isinstance(identity, str):
        identity = Identity(identity)
    key = f"org:{identity.organization_id}" if identity.organization_id else identity.user_id
    directory = settings.data_directory / "workspaces" / hashlib.sha256(key.encode()).hexdigest()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    return settings.model_copy(update={"data_directory": directory})


def request_settings(request: Request) -> Settings:
    return getattr(request.state, "workspace_settings", request.app.state.settings)
