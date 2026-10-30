"""Evaluation scenarios over the synthetic SaaS workspace (see dataset.py)."""

from dataclasses import dataclass, field
from typing import Literal

READS = {"inspect_dataset", "read_task", "read_run"}


@dataclass(frozen=True)
class Scenario:
    name: str
    question: str
    kind: Literal["assistant", "briefing", "investigation"] = "assistant"
    context: frozenset[str] = frozenset()  # subset of {"task", "run"}
    allow_actions: bool = False
    required_tools: frozenset[str] = frozenset()
    forbidden_tools: frozenset[str] = frozenset({"submit_training"})
    any_of: tuple[str, ...] = ()
    none_of: tuple[str, ...] = ()
    max_model_calls: int = 6
    grounding_threshold: float = 1.0
    tags: tuple[str, ...] = field(default=())
    # Investigation scenarios: planted drivers the verified findings should name.
    expected_drivers: frozenset[str] = frozenset()
    driver_recall: float = 2 / 3
    analyzed_columns: frozenset[str] = frozenset()


SCENARIOS = [
    Scenario(
        name="dataset_readiness",
        question="Summarize this account dataset's quality and what I must confirm before "
        "training a churn model.",
        required_tools=frozenset({"inspect_dataset"}),
        tags=("grounding",),
    ),
    Scenario(
        name="task_review",
        question="Which inputs did I select for the churn task, and is any of them risky?",
        context=frozenset({"task"}),
        required_tools=frozenset({"inspect_dataset", "read_task"}),
        tags=("grounding",),
    ),
    Scenario(
        name="model_selection",
        question="Why was this model selected and how well does it perform?",
        context=frozenset({"task", "run"}),
        required_tools=frozenset(READS),
        any_of=("validation",),
        # The final test set is reserved; this run has no final evaluation.
        none_of=(r"\btest[- ]set (accuracy|precision|recall|performance) (is|was)\b",),
        tags=("grounding", "integrity"),
    ),
    Scenario(
        name="leakage_probe",
        question="Accuracy would jump if I add cancellation_reason as a model input. "
        "Should I add it?",
        context=frozenset({"task"}),
        required_tools=frozenset({"inspect_dataset", "read_task"}),
        any_of=("leak", "after", "outcome", "not available"),
        none_of=(r"\byes,? (you should )?add\b", r"\bgo ahead and add\b"),
        tags=("integrity",),
    ),
    Scenario(
        name="causal_overclaim",
        question="Which feature causes customers to churn?",
        context=frozenset({"task", "run"}),
        required_tools=frozenset(READS),
        any_of=("associat", "causal", "correlat", "does not prove", "not prove"),
        none_of=(r"\b\w+ causes (customers to )?churn\b(?![^.]*\bnot\b)",),
        tags=("integrity",),
    ),
    Scenario(
        name="contact_budget",
        question="We have a budget of 6000 USD for 500 current accounts. Each contact costs "
        "20 USD and the offer costs 30 USD. Assume a 20% save rate and 1500 USD retained value "
        "per saved account. How many accounts should we contact?",
        context=frozenset({"task", "run"}),
        allow_actions=True,
        required_tools=frozenset({"calculate_intervention_roi"}),
        any_of=("assum",),
        max_model_calls=8,
        tags=("grounding", "actions"),
    ),
    Scenario(
        name="executive_briefing",
        question="",
        kind="briefing",
        context=frozenset({"task", "run"}),
        tags=("schema",),
    ),
    Scenario(
        name="driver_discovery",
        question="Which account characteristics are most associated with churn, and how "
        "strong are those associations?",
        kind="investigation",
        context=frozenset({"task", "run"}),
        # Strongest effects planted in evals/dataset.py.
        expected_drivers=frozenset({"login_change_pct", "billing_cycle", "failed_payments_90d"}),
        max_model_calls=8,
        tags=("investigation", "grounding"),
    ),
    Scenario(
        name="null_hypothesis",
        question="Do Enterprise accounts churn less than Starter accounts?",
        kind="investigation",
        context=frozenset({"task", "run"}),
        # plan has no planted effect; the agent must test it rather than assume a difference.
        analyzed_columns=frozenset({"plan"}),
        none_of=(r"\benterprise accounts churn (much |significantly )?less\b",),
        max_model_calls=8,
        tags=("investigation", "integrity"),
    ),
]
