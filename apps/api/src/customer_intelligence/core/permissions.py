"""Role permissions for shared workspaces, enforced on every API request.

- owner and admin: everything.
- member: day-to-day work (upload, train, score, ask, propose), but not guardrails, connectors,
  the active model, approvals, data-policy changes or deletions.
- viewer: read-only, plus asking the assistant questions.
Personal workspaces and private CLI mode act as owner.
"""

import re

READ = {"GET", "HEAD", "OPTIONS"}
VIEWER_WRITES = (
    re.compile(r"^/api/v1/assistant/messages(/stream)?$"),
    # Anyone may turn their own email digest on or off and send themselves a test.
    re.compile(r"^/api/v1/email/(subscription|test)$"),
)
ADMIN_ONLY = (
    ("PUT", re.compile(r"^/api/v1/(autonomy|schedule|privacy|retention-policy)$")),
    ("POST", re.compile(r"^/api/v1/retention-policy/apply$")),
    # Anyone in the workspace may see connection status; only admins connect or sync.
    ("POST", re.compile(r"^/api/v1/connections(/.*)?$")),
    ("PUT", re.compile(r"^/api/v1/connections(/.*)?$")),
    # Listing HubSpot properties uses the stored credential, so it is an admin action too.
    ("GET", re.compile(r"^/api/v1/connections/[^/]+/properties$")),
    ("POST", re.compile(r"^/api/v1/registry/(promote|rollback)$")),
    ("POST", re.compile(r"^/api/v1/actions/[^/]+/(approve|reject)$")),
    ("GET", re.compile(r"^/api/v1/audit$")),
    ("DELETE", re.compile(r"^/api/v1/.+$")),
)


def denied(role: str, method: str, path: str) -> str | None:
    """A message when the role may not make this request; None when it may."""
    if role in ("owner", "admin"):
        return None
    for verb, pattern in ADMIN_ONLY:
        if verb in ("*", method) and pattern.match(path):
            return "Only workspace owners and admins can do this."
    if role == "viewer" and method not in READ and not any(p.match(path) for p in VIEWER_WRITES):
        return "Viewers can look but not change anything in this workspace."
    if role not in ("member", "viewer"):
        return "Unknown workspace role."
    return None


# What each role can do, in plain words, with one representative request per line so a test
# can prove these descriptions match `denied` exactly.
CAPABILITIES: tuple[tuple[str, str, str], ...] = (
    ("Read everything and ask AI questions", "POST", "/api/v1/assistant/messages"),
    ("Upload data, define churn, train and score", "POST", "/api/v1/jobs/train"),
    ("Request Nemotron briefs and account reasons", "POST", "/api/v1/briefs"),
    ("Assign plays and propose actions for approval", "POST", "/api/v1/actions/plays"),
    ("Approve or reject actions", "POST", "/api/v1/actions/x/approve"),
    ("Choose the active model", "POST", "/api/v1/registry/promote"),
    ("Connect and sync Stripe or HubSpot", "POST", "/api/v1/connections"),
    ("Change automation, privacy and retention", "PUT", "/api/v1/autonomy"),
    ("Delete data", "DELETE", "/api/v1/datasets/x"),
    ("Read the audit log", "GET", "/api/v1/audit"),
)


def capabilities(role: str) -> list[dict[str, object]]:
    return [
        {"label": label, "allowed": denied(role, method, path) is None}
        for label, method, path in CAPABILITIES
    ]
