"""Conservative deterministic checks; semantic ambiguity still needs user context."""

import re


def obvious_leakage(name: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", name.lower())
    return normalized in {
        "churndate",
        "churnreason",
        "cancellationdate",
        "cancellationreason",
        "cancelledat",
        "canceledat",
        "terminationdate",
        "terminationreason",
        "actualchurn",
        "churnoutcome",
    }
