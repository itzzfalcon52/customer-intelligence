"""Deterministic verification of investigation reports. Code, not a model, decides what is shown."""

import re
from typing import Any

from customer_intelligence.agent.grounding import ungrounded_numbers
from customer_intelligence.schemas.investigation import InvestigationReport

CAUSAL = re.compile(
    r"\b(causes?|caused|causing|drives?|driven by|driving|leads? to|results? in|because of|"
    r"due to|makes? (?:customers|accounts|users))\b",
    re.IGNORECASE,
)
OUTCOME = re.compile(r"\b(churn\w*|cancel\w*|retention|retain\w*|leav\w*|lost)\b", re.I)
NEGATION = re.compile(r"\b(not|no|never|cannot|can't|doesn't|does not|without)\b", re.IGNORECASE)


def causal_claims(text: str) -> list[str]:
    """Causal wording about the outcome, unless negated ("does not prove it causes" is fine).

    Sentences that never mention churn (e.g. "uncertain due to small samples") are not claims
    about what causes churn.
    """
    claims = []
    for sentence in re.split(r"(?<=[.!?;])\s+", text):
        match = CAUSAL.search(sentence)
        if match and OUTCOME.search(sentence) and not NEGATION.search(sentence[: match.start()]):
            claims.append(match.group())
    return claims


def _results(evidence: dict[str, dict[str, Any]], ids: list[str] | None = None) -> list[Any]:
    selected = evidence if ids is None else {key: evidence[key] for key in ids if key in evidence}
    return [item["result"] for item in selected.values() if "result" in item]


def verify_report(
    report: InvestigationReport, evidence: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    findings = []
    for index, finding in enumerate(report.findings):
        problems = []
        unknown = [key for key in finding.evidence if key not in evidence]
        failed = [key for key in finding.evidence if key in evidence and "error" in evidence[key]]
        if unknown:
            problems.append(f"cites unknown evidence {unknown}")
        if failed:
            problems.append(f"cites failed analyses {failed}")
        _, missing = ungrounded_numbers(finding.statement, _results(evidence, finding.evidence))
        if missing:
            problems.append(f"numbers not in the cited evidence: {missing}")
        causal = causal_claims(finding.statement)
        if causal:
            problems.append(f"causal wording {causal}; the evidence shows association only")
        findings.append({"index": index, "supported": not problems, "problems": problems})

    everything = _results(evidence)

    def text_problems(text: str) -> list[str]:
        problems = []
        _, missing = ungrounded_numbers(text, everything)
        if missing:
            problems.append(f"numbers not in any evidence: {missing}")
        causal = causal_claims(text)
        if causal:
            problems.append(f"causal wording {causal}")
        return problems

    headline = text_problems(report.headline)
    caveats = {i: p for i, text in enumerate(report.caveats) if (p := text_problems(text))}
    next_steps = {i: p for i, text in enumerate(report.next_steps) if (p := text_problems(text))}
    return {
        "passed": all(f["supported"] for f in findings)
        and not headline
        and not caveats
        and not next_steps,
        "findings": findings,
        "headline_problems": headline,
        "caveat_problems": caveats,
        "next_step_problems": next_steps,
    }


def feedback(verification: dict[str, Any]) -> list[str]:
    """Problems phrased for the writer's single revision attempt."""
    lines = [
        f"Finding {item['index'] + 1}: " + "; ".join(item["problems"])
        for item in verification["findings"]
        if item["problems"]
    ]
    if verification["headline_problems"]:
        lines.append("Headline: " + "; ".join(verification["headline_problems"]))
    for label, key in (("Caveat", "caveat_problems"), ("Next step", "next_step_problems")):
        for index, problems in verification[key].items():
            lines.append(f"{label} {int(index) + 1}: " + "; ".join(problems))
    return lines


def finalize(report: InvestigationReport, verification: dict[str, Any]) -> dict[str, Any]:
    """Keep only verified content; list what was withheld so nothing disappears silently."""
    kept = [
        finding.model_dump()
        for finding, check in zip(report.findings, verification["findings"], strict=True)
        if check["supported"]
    ]
    withheld = [
        {"statement": finding.statement, "problems": check["problems"]}
        for finding, check in zip(report.findings, verification["findings"], strict=True)
        if not check["supported"]
    ]
    headline = report.headline
    if verification["headline_problems"]:
        headline = kept[0]["statement"] if kept else "No finding passed verification."
    return {
        "headline": headline,
        "findings": kept,
        "caveats": [
            text
            for i, text in enumerate(report.caveats)
            if i not in verification["caveat_problems"]
        ],
        "next_steps": [
            text
            for i, text in enumerate(report.next_steps)
            if i not in verification["next_step_problems"]
        ],
        "withheld": withheld,
        "status": "verified" if verification["passed"] else ("partial" if kept else "unverified"),
    }
