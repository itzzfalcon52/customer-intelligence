"""Nemotron's daily brief: what changed, who to call first and which play to run.

The deterministic engine measures (scores, drift, outcomes, per-account drivers); Nemotron reads
those results and writes the brief. Code then verifies every sentence: numbers must appear in the
evidence and causal wording about churn is rejected. Failing items are withheld and counted.
Accounts are sent as labels (A1...) and mapped back to real IDs only on the server.
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from openai import OpenAI
from pydantic import BaseModel, Field, field_validator
from sqlmodel import Session, col, select

from customer_intelligence.core.config import Settings
from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.models.operations import Brief, MonitorReport
from customer_intelligence.services import monitoring, playbooks, reasons
from customer_intelligence.services.runs import read_training_run
from customer_intelligence.services.scoring import read_score
from customer_intelligence.services.workspace import read_memory

CALL_FIRST = 5


class CallFirst(BaseModel):
    label: str = Field(pattern=r"^A\d{1,2}$")
    why: str = Field(min_length=5, max_length=240)
    citation: str | None = Field(default=None, pattern=r"^P\d$")


class Play(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    instructions: str = Field(min_length=10, max_length=800)
    citation: str | None = Field(default=None, pattern=r"^P\d$")


class DailyBrief(BaseModel):
    headline: str = Field(min_length=10, max_length=220)
    what_changed: list[str] = Field(max_length=4)
    call_first: list[CallFirst] = Field(max_length=CALL_FIRST)
    recommended_play: Play
    caveats: list[str] = Field(max_length=4)

    @field_validator("recommended_play", mode="before")
    @classmethod
    def parse_nested(cls, value: Any) -> Any:
        # Some hosts return a nested object as a JSON string; it is still validated strictly.
        if isinstance(value, str):
            try:
                return json.loads(value)
            except ValueError:
                return value
        return value


def _evidence(
    session: Session, settings: Settings, score_id: UUID
) -> tuple[dict[str, Any], dict[str, dict], list[dict]]:
    score = read_score(score_id, settings.data_directory)
    run = read_training_run(score.run_id, settings.data_directory)
    chosen = max(run.report.results, key=lambda r: r.validation.average_precision).validation
    chance = chosen.positive_count / max(1, chosen.row_count)
    drift = session.exec(
        select(MonitorReport)
        .where(MonitorReport.score_id == score_id, MonitorReport.kind == "drift")
        .order_by(col(MonitorReport.created_at).desc())
    ).first() or monitoring.feature_drift(session, settings, score_id)
    since = datetime.now(UTC) - timedelta(days=30)
    measured = session.exec(
        select(MonitorReport)
        .where(
            col(MonitorReport.kind).in_(["performance", "lift"]),
            col(MonitorReport.created_at) >= since,
        )
        .order_by(col(MonitorReport.created_at).desc())
        .limit(3)
    ).all()
    driven = reasons.drivers(session, settings, score_id)
    accounts = {f"A{i}": a for i, a in enumerate(driven["accounts"][:CALL_FIRST], start=1)}
    moved = [f for f in drift.payload["features"] if f["band"] != "stable"][:5]
    words = {reasons.plain(f["feature"]) for f in moved} | {
        reasons.plain(d["feature"]) for a in accounts.values() for d in a["drivers"]
    }
    passages = playbooks.search(settings, " ".join(sorted(words)) or "churn risk", 3)["results"]
    memory = read_memory(session)
    evidence = {
        "model": {
            "validation_average_precision": round(chosen.average_precision, 3),
            "chance_level": round(chance, 3),
            "times_better_than_chance": round(chosen.average_precision / chance, 1)
            if chance
            else None,
        },
        "batch": {
            "accounts_scored": score.row_count,
            "contact_list": score.contact_count,
            "holdout_accounts": score.holdout_count,
        },
        "customer_traits_that_changed_since_training": [
            {"input": reasons.plain(f["feature"]), "how_much": SIZE[f["band"]]} for f in moved
        ],
        "customer_traits_checked": len(drift.payload["features"]),
        "median_risk_score": _shift(drift.payload.get("score_shift")),
        "measured_outcomes": [{"kind": m.kind, "summary": m.summary} for m in measured],
        "top_accounts": [
            {"label": label, "risk_score": a["risk_score"], "stands_out": reasons.readable(a)}
            for label, a in accounts.items()
        ],
        "playbook_passages": [
            {"citation": p["citation"], "heading": p["heading"], "text": p["text"]}
            for p in passages
        ],
        "assumptions": memory["assumptions"],
        "notes": "What stands out for an account is an association with the model's score, "
        "not a cause. Changes are rated with a common rule of thumb, not a statistical test.",
    }
    return evidence, accounts, passages


SIZE = {"watch": "changed somewhat", "alert": "changed a lot"}


def _shift(shift: dict | None) -> dict | None:
    if not shift:
        return None
    return {"previous_batch": shift["previous_median"], "this_batch": shift["current_median"]}


def _problems(text: str, evidence: dict) -> list[str]:
    return reasons._check(text, evidence)


def write_brief(
    session: Session, settings: Settings, score_id: UUID, client: OpenAI | None = None
) -> Brief:
    from customer_intelligence.agent.grounding import ungrounded_numbers
    from customer_intelligence.agent.llm import LLMGateway
    from customer_intelligence.agent.prompts import load_prompt
    from customer_intelligence.agent.tracing import traced

    evidence, accounts, passages = _evidence(session, settings, score_id)
    prompt = load_prompt("daily_brief")
    with traced(session, "daily_brief") as tracer, LLMGateway(settings, client) as gateway:
        draft = gateway.structured(
            prompt.text,
            evidence,
            DailyBrief,
            max_tokens=2048,
            name="daily_brief",
            prompt_label=prompt.label,
        )
        trace_id = tracer.id
    cited = {p["citation"]: p for p in passages}
    withheld: list[str] = []
    checked = 0

    def keep(text: str, where: str) -> bool:
        nonlocal checked
        checked += len(ungrounded_numbers(text, [evidence])[0])
        problems = _problems(text, evidence)
        if problems:
            withheld.append(f"{where}: {'; '.join(problems)}")
        return not problems

    def citation(label: str | None) -> dict | None:
        passage = cited.get(label or "")
        if passage is None:
            return None
        return {
            "label": label,
            "playbook_id": passage["playbook_id"],
            "playbook": passage["playbook"],
            "heading": passage["heading"],
            "passage": passage["passage"],
        }

    headline = draft.headline if keep(draft.headline, "headline") else None
    if headline is None:
        headline = (
            f"{evidence['batch']['contact_list']} accounts are on today's contact list; "
            "the top ones are below."
        )
    play = draft.recommended_play
    play_ok = keep(play.title, "play title") and keep(play.instructions, "play")
    changed = [t["input"] for t in evidence["customer_traits_that_changed_since_training"]]

    def on_topic(text: str) -> bool:
        # A "what changed" point must be about a measured change, so it has to name one.
        lowered = text.lower()
        ok = (
            any(name.lower() in lowered for name in changed)
            or "risk score" in lowered
            or ("median" in lowered and "risk" in lowered)
            or (not changed and ("no " in lowered or "none" in lowered))
        )
        if not ok:
            withheld.append("what changed: not about a measured change")
        return ok

    content = {
        "headline": headline,
        "what_changed": [t for t in draft.what_changed if on_topic(t) and keep(t, "what changed")],
        "call_first": [
            {
                "customer_id": accounts[item.label]["customer_id"],
                "rank": accounts[item.label]["rank"],
                "why": item.why,
                "citation": citation(item.citation),
            }
            for item in draft.call_first
            if item.label in accounts and keep(item.why, f"call first {item.label}")
        ],
        "recommended_play": {
            "title": play.title,
            "instructions": play.instructions,
            "citation": citation(play.citation),
        }
        if play_ok
        else None,
        "caveats": [t for t in draft.caveats if keep(t, "caveat")],
        "model": settings.nebius_model,
    }
    brief = Brief(
        score_id=score_id,
        trace_id=trace_id,
        content=content,
        verification={"numbers_checked": checked, "withheld": withheld},
    )
    session.add(brief)
    session.commit()
    session.refresh(brief)
    return brief


def record_failure(session: Session, score_id: UUID, error: str) -> Brief:
    brief = Brief(score_id=score_id, status="failed", error=error[:500])
    session.add(brief)
    session.commit()
    session.refresh(brief)
    return brief


def latest(session: Session) -> Brief | None:
    return session.exec(select(Brief).order_by(col(Brief.created_at).desc())).first()


def get(session: Session, brief_id: UUID) -> Brief:
    brief = session.get(Brief, brief_id)
    if brief is None:
        raise WorkflowError("Brief not found.", 404)
    return brief
