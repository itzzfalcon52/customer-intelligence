"""Why each top account is flagged: deterministic drivers, explained in plain words by Nemotron.

Drivers come from code. For each input, the account's value is swapped for the typical training
value (median or most common) and the account is re-scored; inputs whose swap lowers the risk
the most are its drivers. That is an association with the model's score, not a cause of churn.

Nemotron only rewrites those drivers as a short note and may cite a playbook passage. Accounts
reach the provider as labels (A1, A2...), never as real IDs. Every note is checked: numbers must
appear in the evidence and causal wording about churn is rejected; a note that fails is replaced
by plain text built from the drivers.
"""

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pandas as pd
from openai import OpenAI
from pydantic import BaseModel, Field
from sqlmodel import Session

from customer_intelligence.agent.grounding import ungrounded_numbers
from customer_intelligence.agent.verification import CAUSAL, causal_claims
from customer_intelligence.core.config import Settings
from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.ml.evaluation import positive_scores
from customer_intelligence.models.dataset import Dataset
from customer_intelligence.services.artifacts import read_json
from customer_intelligence.services.profiling import load_dataset_frame
from customer_intelligence.services.runs import load_pipeline, read_training_run
from customer_intelligence.services.scoring import read_customers, read_score

MAX_ACCOUNTS = 15
FIELD_NAME = re.compile(r"\b[a-z0-9]+_[a-z0-9_]+\b")
TOP_DRIVERS = 3


class AccountNote(BaseModel):
    label: str = Field(pattern=r"^A\d{1,2}$")
    note: str = Field(min_length=10, max_length=320)
    citation: str | None = Field(default=None, pattern=r"^P\d$")


class AccountNotes(BaseModel):
    notes: list[AccountNote] = Field(max_length=MAX_ACCOUNTS)


WORDS = {
    "mrr": "monthly revenue",
    "pct": "percent",
    "30d": "in the last 30 days",
    "90d": "in the last 90 days",
    "cancel_intent": "cancellation-intent",
}


def plain(feature: str) -> str:
    """A readable name for an input, e.g. logins_30d -> logins in the last 30 days."""
    text = feature
    for raw, word in WORDS.items():
        text = text.replace(raw, word)
    return text.replace("_", " ").strip()


def _path(settings: Settings, score_id: UUID) -> Path:
    return settings.data_directory / "scores" / str(score_id) / "reasons.json"


def _value(value: Any) -> Any:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, float):
        return round(value, 2)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)[:60]
    return round(number, 2) if not number.is_integer() else int(number)


def drivers(
    session: Session, settings: Settings, score_id: UUID, limit: int = MAX_ACCOUNTS
) -> dict:
    """Top drivers for the first `limit` accounts on the contact list (cached per batch)."""
    path = _path(settings, score_id)
    if path.exists():
        cached = read_json(path)
        if isinstance(cached, dict) and len(cached.get("accounts", [])) >= min(limit, 1):
            return cached
    score = read_score(score_id, settings.data_directory)
    run = read_training_run(score.run_id, settings.data_directory)
    pipeline = load_pipeline(run, settings.data_directory)
    from customer_intelligence.services.analysis import run_frame

    training = run_frame(session, settings, run).iloc[run.split.row_assignments["train"]]
    dataset = session.get(Dataset, score.dataset_id)
    if dataset is None:
        raise WorkflowError("Scoring dataset not found.", 404)
    frame = load_dataset_frame(dataset, settings, expected_sha256=score.dataset_sha256)
    listed = [
        c
        for c in sorted(read_customers(score, settings.data_directory), key=lambda c: c.rank)
        if c.group != "holdout"
    ][:limit]
    if not listed:
        raise WorkflowError("This batch has no accounts to explain.", 409)
    schema = pipeline.named_steps["preprocessing"].named_steps["schema"]
    rows = frame.iloc[[c.row_reference - 1 for c in listed]].loc[:, run.task.feature_columns]
    rows = rows.reset_index(drop=True)
    base = [c.risk_score for c in listed]
    effects: dict[str, list[float]] = {}
    typical: dict[str, Any] = {}
    for feature in run.task.feature_columns:
        values = training[feature].dropna()
        if values.empty:
            continue
        reference = (
            pd.to_numeric(values, errors="coerce").median()
            if feature in schema.numeric_columns_
            else values.mode().iloc[0]
        )
        typical[feature] = reference
        swapped = rows.copy()
        swapped[feature] = reference
        scores = positive_scores(pipeline, swapped)
        # Positive: the account's own value raises its risk relative to a typical value.
        effects[feature] = [b - s for b, s in zip(base, scores, strict=True)]
    accounts = []
    for index, customer in enumerate(listed):
        ranked = sorted(effects, key=lambda f: effects[f][index], reverse=True)
        top = [f for f in ranked if effects[f][index] > 0.005][:TOP_DRIVERS]
        accounts.append(
            {
                "customer_id": customer.customer_id,
                "rank": customer.rank,
                "risk_score": round(customer.risk_score, 3),
                "drivers": [
                    {
                        "feature": f,
                        "input": plain(f),
                        "value": _value(rows.iloc[index][f]),
                        "typical": _value(typical[f]),
                        "risk_change": round(effects[f][index], 3),
                    }
                    for f in top
                ],
            }
        )
    payload = {
        "score_id": str(score_id),
        "run_id": str(score.run_id),
        "created_at": datetime.now(UTC).isoformat(),
        "method": "Swap one input for its typical training value and re-score; drivers are the "
        "inputs whose swap lowers the risk score most. Associations, not causes.",
        "accounts": accounts,
        "notes": None,
    }
    path.write_text(json.dumps(payload, allow_nan=False))
    return payload


def readable(account: dict) -> list[dict]:
    """Drivers as sent to the model: plain names and values, strongest first, no internals."""
    return [
        {"input": plain(d["feature"]), "account_value": d["value"], "typical_value": d["typical"]}
        for d in account["drivers"]
    ]


def plain_text(account: dict) -> str:
    """The fallback reason, built only from the computed drivers."""
    if not account["drivers"]:
        return "No single input stands out; the risk comes from several small differences."
    parts = [
        f"{plain(d['feature'])} {d['value']} (typical {d['typical']})" for d in account["drivers"]
    ]
    return "Stands out on " + "; ".join(parts) + "."


def _check(text: str, evidence: Any) -> list[str]:
    problems = []
    _, missing = ungrounded_numbers(text, [evidence])
    if missing:
        problems.append("unsupported numbers: " + ", ".join(missing))
    # Stricter than the investigation rule: any causal verb, even about the score itself.
    if causal_claims(text) or CAUSAL.search(text):
        problems.append("causal wording")
    if FIELD_NAME.search(text):
        problems.append("internal field name")
    return problems


def write_notes(
    session: Session,
    settings: Settings,
    score_id: UUID,
    client: OpenAI | None = None,
    limit: int = MAX_ACCOUNTS,
) -> dict:
    """Nemotron notes for the top accounts; traced, budgeted and verified before saving."""
    from customer_intelligence.agent.llm import LLMGateway
    from customer_intelligence.agent.prompts import load_prompt
    from customer_intelligence.agent.tracing import traced
    from customer_intelligence.services import playbooks

    payload = drivers(session, settings, score_id, limit)
    accounts = payload["accounts"][:limit]
    labelled = {f"A{i}": a for i, a in enumerate(accounts, start=1)}
    features = {plain(d["feature"]) for a in accounts for d in a["drivers"]}
    passages = playbooks.search(settings, " ".join(sorted(features)) or "churn risk", 3)["results"]
    evidence = {
        "accounts": [
            {"label": label, "risk_score": a["risk_score"], "stands_out": readable(a)}
            for label, a in labelled.items()
        ],
        "playbook_passages": [
            {"citation": p["citation"], "heading": p["heading"], "text": p["text"]}
            for p in passages
        ],
        "method": payload["method"],
    }
    prompt = load_prompt("account_notes")
    with traced(session, "account_notes") as tracer, LLMGateway(settings, client) as gateway:
        result = gateway.structured(
            prompt.text,
            evidence,
            AccountNotes,
            max_tokens=2048,
            name="account_notes",
            prompt_label=prompt.label,
        )
        trace_id = str(tracer.id)
    citations = {p["citation"]: p for p in passages}
    written = {n.label: n for n in result.notes if n.label in labelled}
    notes, verified, withheld = {}, 0, 0
    for label, account in labelled.items():
        note = written.get(label)
        problems = _check(note.note, evidence) if note else ["no note"]
        if note and not problems:
            verified += 1
            passage = citations.get(note.citation or "")
            notes[account["customer_id"]] = {
                "text": note.note,
                "source": "nemotron",
                "citation": {
                    "label": note.citation,
                    "playbook_id": passage["playbook_id"],
                    "playbook": passage["playbook"],
                    "heading": passage["heading"],
                    "passage": passage["passage"],
                }
                if passage
                else None,
            }
        else:
            withheld += int(note is not None)
            notes[account["customer_id"]] = {
                "text": plain_text(account),
                "source": "computed",
                "citation": None,
                "withheld_reason": "; ".join(problems) if note else None,
            }
    payload["notes"] = {
        "items": notes,
        "verified": verified,
        "withheld": withheld,
        "trace_id": trace_id,
        "model": settings.nebius_model,
        "created_at": datetime.now(UTC).isoformat(),
    }
    _path(settings, score_id).write_text(json.dumps(payload, allow_nan=False))
    return payload


def read_reasons(session: Session, settings: Settings, score_id: UUID) -> dict:
    return drivers(session, settings, score_id)
