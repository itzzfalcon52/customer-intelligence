"""Deterministic graders. Each returns a GradeResult; none of them calls a model."""

import json
import re
from dataclasses import dataclass, field
from typing import Any

from customer_intelligence.agent.grounding import ungrounded_numbers


@dataclass
class GradeResult:
    name: str
    passed: bool
    score: float
    details: dict[str, Any] = field(default_factory=dict)


def numeric_grounding(answer: str, sources: list[Any], threshold: float = 1.0) -> GradeResult:
    """Every non-trivial number in the answer must appear in a tool output or the question."""
    checked, ungrounded = ungrounded_numbers(answer, sources)
    score = 1.0 if not checked else (len(checked) - len(ungrounded)) / len(checked)
    return GradeResult(
        "numeric_grounding",
        score >= threshold,
        score,
        {"checked": checked, "ungrounded": ungrounded},
    )


def trajectory(called: list[str], required: set[str], forbidden: set[str]) -> GradeResult:
    missing = sorted(required - set(called))
    violations = sorted(forbidden & set(called))
    passed = not missing and not violations
    return GradeResult(
        "tool_trajectory",
        passed,
        1.0 if passed else 0.0,
        {"called": called, "missing": missing, "forbidden_called": violations},
    )


def required_language(
    answer: str, any_of: list[str], none_of: list[str], name: str = "required_language"
) -> GradeResult:
    """Cheap guard for caveats (e.g. leakage or association wording); the judge covers nuance."""
    lowered = answer.lower()
    present = [phrase for phrase in any_of if phrase.lower() in lowered]
    banned = [pattern for pattern in none_of if re.search(pattern, answer, re.IGNORECASE)]
    passed = (not any_of or bool(present)) and not banned
    return GradeResult(
        name, passed, 1.0 if passed else 0.0, {"matched": present, "banned_matches": banned}
    )


def budget(model_calls: int, limit: int) -> GradeResult:
    return GradeResult(
        "call_budget",
        model_calls <= limit,
        1.0 if model_calls <= limit else 0.0,
        {"model_calls": model_calls, "limit": limit},
    )


def schema_valid(name: str, ok: bool, problem: str | None = None) -> GradeResult:
    return GradeResult(name, ok, 1.0 if ok else 0.0, {"problem": problem} if problem else {})


def tool_outputs(request_messages: list[dict[str, Any]]) -> list[Any]:
    """Decode the tool results the model actually saw in its final request."""
    outputs: list[Any] = []
    for message in request_messages:
        if message.get("role") == "tool":
            try:
                outputs.append(json.loads(message["content"]))
            except (TypeError, ValueError):
                outputs.append(message.get("content"))
    return outputs


def driver_recall(text: str, expected: set[str], threshold: float) -> GradeResult:
    found = sorted(name for name in expected if name.lower() in text.lower())
    score = len(found) / len(expected) if expected else 1.0
    return GradeResult(
        "driver_recall", score >= threshold, score, {"found": found, "expected": sorted(expected)}
    )


def analyzed(evidence: dict[str, Any], columns: set[str]) -> GradeResult:
    """The investigation actually ran an analysis touching each required column."""
    touched = json.dumps([item.get("arguments") for item in evidence.values() if "result" in item])
    missing = sorted(column for column in columns if f'"{column}"' not in touched)
    return GradeResult(
        "analyzed_columns", not missing, 0.0 if missing else 1.0, {"missing": missing}
    )
