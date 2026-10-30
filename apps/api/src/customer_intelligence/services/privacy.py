"""Field-level privacy policy: columns whose values must never reach the AI provider.

The policy is the user's explicit column list plus, by default, name patterns for direct
identifiers and sensitive or demographic fields. Withheld columns stay usable by the model
training itself (that never leaves the server), but:
- profiles sent to the assistant keep only the column name and type, not its statistics;
- investigations do not analyse them;
- outreach drafts can never be personalised with them.
"""

import re
from typing import Any

from sqlmodel import Session

from customer_intelligence.models.workspace import WorkspaceFact

POLICY = "privacy"
SENSITIVE = re.compile(
    r"email|phone|address|name|gender|senior|age|religio|race|caste|ethnic|health|disabil|"
    r"customer.?id",
    re.I,
)


def read_policy(session: Session) -> dict:
    fact = session.get(WorkspaceFact, POLICY)
    value = fact.value if fact else {}
    return {
        "blocked_columns": list(value.get("blocked_columns", [])),
        "default_patterns": bool(value.get("default_patterns", True)),
    }


def update_policy(session: Session, blocked_columns: list[str], default_patterns: bool) -> dict:
    from datetime import UTC, datetime

    value = {
        "blocked_columns": sorted({c.strip() for c in blocked_columns if c.strip()}),
        "default_patterns": default_patterns,
    }
    fact = session.get(WorkspaceFact, POLICY)
    if fact is None:
        fact = WorkspaceFact(key=POLICY, value=value, source="user")
    else:
        fact.value, fact.source, fact.updated_at = value, "user", datetime.now(UTC)
    session.add(fact)
    session.commit()
    return read_policy(session)


def withheld(session: Session, columns: list[str]) -> set[str]:
    policy = read_policy(session)
    explicit = set(policy["blocked_columns"])
    return {
        c for c in columns if c in explicit or (policy["default_patterns"] and SENSITIVE.search(c))
    }


def ai_profile(session: Session, profile: Any) -> dict:
    """A dataset profile safe to send to the provider under this workspace's policy."""
    payload = profile.model_dump(mode="json", exclude={"preview", "original_filename"})
    hidden = withheld(session, [c["name"] for c in payload["columns"]])
    for column in payload["columns"]:
        if column["name"] in hidden:
            column["numeric_summary"] = None
            column["withheld_by_privacy_policy"] = True
    return payload
