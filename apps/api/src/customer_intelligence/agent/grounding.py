"""Numeric grounding: every non-trivial number in generated text must come from evidence.

Shared by the investigation verifier (product) and the eval graders, so both apply one rule.
"""

import math
import re
from collections.abc import Iterable
from typing import Any

# Models often write hyphens and minus signs as Unicode variants (e.g. U+2011 inside UUIDs).
HYPHENS = str.maketrans({c: "-" for c in "\u2010\u2011\u2012\u2013\u2014\u2212\ufe63\uff0d"})
UUID_PATTERN = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE
)
# Short hex fragments such as "3f2a9c1d" are ID prefixes, not measurements.
HEX_FRAGMENT = re.compile(r"\b(?=[0-9a-f]*[a-f])(?=[0-9a-f]*\d)[0-9a-f]{6,}\b", re.IGNORECASE)
# "95% CI" names a confidence level; it is a label, not a measured value.
CONFIDENCE_LEVEL = re.compile(
    r"\b(?:80|90|95|99)\s?%(?=\s*(?:confidence|CI\b|credible|interval|prediction interval))",
    re.IGNORECASE,
)
LIST_MARKER = re.compile(r"^\s*\d+[.)]\s", re.MULTILINE)
# Thousands may be grouped with commas or with the no-break/narrow/thin spaces models emit
# ("30\u202f719"); an ordinary space is not a separator, so "119 500" stays two numbers.
GROUP = "[,\u00a0\u202f\u2009]"
NUMBER = re.compile(
    rf"(?<![\w.])[-+]?\d{{1,3}}(?:{GROUP}\d{{3}})+(?:\.\d+)?%?|(?<![\w.])[-+]?\d+(?:\.\d+)?%?"
)
# Small integers are usually counts or ordinals ("3 candidates", "top 5"); they are too common
# in tool outputs for a match to mean anything, so they are not graded.
TRIVIAL_LIMIT = 10


def numeric_leaves(value: Any) -> Iterable[float]:
    if isinstance(value, bool):
        return
    if isinstance(value, int | float):
        if math.isfinite(value):
            yield float(value)
    elif isinstance(value, dict):
        for item in value.values():
            yield from numeric_leaves(item)
    elif isinstance(value, list):
        for item in value:
            yield from numeric_leaves(item)
    elif isinstance(value, str):
        # Tool outputs sometimes carry numbers inside strings (warnings, labels).
        for match in NUMBER.finditer(UUID_PATTERN.sub(" ", value.translate(HYPHENS))):
            parsed = _parse(match.group())
            if parsed is not None:
                yield parsed[0]


def _parse(token: str) -> tuple[float, int, bool] | None:
    percent = token.endswith("%")
    raw = re.sub(GROUP, "", token.rstrip("%"))
    try:
        value = float(raw)
    except ValueError:
        return None
    decimals = len(raw.split(".")[1]) if "." in raw else 0
    return value, decimals, percent


def answer_numbers(answer: str) -> list[tuple[str, float, int, bool]]:
    text = UUID_PATTERN.sub(" ", answer.translate(HYPHENS))
    text = HEX_FRAGMENT.sub(" ", text)
    text = LIST_MARKER.sub(" ", text)
    text = CONFIDENCE_LEVEL.sub(" ", text)
    found = []
    for match in NUMBER.finditer(text):
        parsed = _parse(match.group())
        if parsed is None:
            continue
        value, decimals, percent = parsed
        if not percent and decimals == 0 and abs(value) <= TRIVIAL_LIMIT:
            continue
        found.append((match.group(), value, decimals, percent))
    return found


def _matches(value: float, decimals: int, percent: bool, source: float) -> bool:
    # A stated number matches when it is the source rounded to the precision it was written at,
    # either directly or as a percentage of a 0-1 fraction (0.7342 -> 73.4%).
    tolerance = 0.5 * 10**-decimals + 1e-9
    candidates = [source, source * 100] if percent or abs(source) <= 1 else [source]
    return any(abs(abs(value) - abs(candidate)) <= tolerance for candidate in candidates)


def ungrounded_numbers(text: str, sources: list[Any]) -> tuple[list[str], list[str]]:
    """Return (checked tokens, tokens with no matching source number)."""
    pool = sorted({round(number, 10) for source in sources for number in numeric_leaves(source)})
    numbers = answer_numbers(text)
    missing = [
        token
        for token, value, decimals, percent in numbers
        if not any(_matches(value, decimals, percent, source) for source in pool)
    ]
    return [token for token, *_ in numbers], missing
