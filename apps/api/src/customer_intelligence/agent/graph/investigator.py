"""Multi-step churn investigation as a LangGraph state graph.

    gather -> plan -> analyze -> follow_up -> (analyze) -> write -> verify -> (write) -> finalize

Only plan, follow_up and write call the model. Analyses are deterministic code over development
rows, and verify is deterministic code that decides which statements are shown.
"""

import json
import time
from typing import Any, Literal, TypedDict

import numpy as np
import pandas as pd
from langgraph.graph import END, START, StateGraph

from customer_intelligence.agent.llm import LLMGateway
from customer_intelligence.agent.prompts import load_prompt
from customer_intelligence.agent.tracing import Tracer
from customer_intelligence.agent.verification import feedback, finalize, verify_report
from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.ml import investigation as analyses
from customer_intelligence.schemas.investigation import (
    Check,
    FollowUp,
    InvestigationPlan,
    InvestigationReport,
)
from customer_intelligence.schemas.runs import TrainingRunManifest

MAX_MODEL_CALLS = 8
TIME_BUDGET_SECONDS = 180
# Each structured step may use a repair call, so optional steps need two calls of headroom.
STEP_CALLS = 2


class InvestigationState(TypedDict, total=False):
    question: str
    plan: dict[str, Any]
    pending: list[dict[str, Any]]
    evidence: dict[str, dict[str, Any]]
    followed_up: bool
    report: dict[str, Any]
    verification: dict[str, Any]
    revisions: int
    result: dict[str, Any]


def model_summary(run: TrainingRunManifest) -> dict[str, Any]:
    report = run.report
    selected = next(
        (
            result
            for result in report.results
            if result.candidate_id == report.best_validation_candidate_id
        ),
        next(r for r in report.results if r.model_name == report.best_validation_model),
    )
    return {
        "selected_model": report.best_validation_model,
        "selection_metric": "validation average precision",
        "classification_threshold": report.classification_threshold,
        "validation": selected.validation.model_dump(
            include={
                "row_count",
                "positive_count",
                "average_precision",
                "roc_auc",
                "precision",
                "recall",
            }
        ),
        "final_test_evaluated": False,
        "note": "Validation metrics; the reserved final test is not used by investigations.",
    }


class Investigator:
    def __init__(
        self,
        *,
        run: TrainingRunManifest,
        frame: pd.DataFrame,
        labels: np.ndarray,
        gateway: LLMGateway,
        tracer: Tracer,
    ) -> None:
        self.run = run
        self.frame = frame
        self.labels = labels
        self.features = list(run.task.feature_columns)
        self.gateway = gateway
        self.tracer = tracer
        self.deadline = time.monotonic() + TIME_BUDGET_SECONDS

    # -- helpers -------------------------------------------------------------------------------

    def _stage(self, name: str, status: str, **detail: Any) -> None:
        self.tracer.emit({"type": "stage", "name": name, "status": status, **detail})

    def _can_call(self) -> bool:
        return (
            self.tracer.model_calls + STEP_CALLS <= MAX_MODEL_CALLS
            and self.deadline - time.monotonic() > 20
        )

    def _record(
        self,
        evidence: dict[str, dict[str, Any]],
        tool: str,
        arguments: dict[str, Any],
        compute: Any,
        hypothesis: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        key = f"E{len(evidence) + 1}"
        item: dict[str, Any] = {"tool": tool, "arguments": arguments}
        if hypothesis:
            item["hypothesis"] = hypothesis
        with self.tracer.tool(f"analysis.{tool}", arguments) as outcome:
            try:
                item["result"] = compute()
            except analyses.AnalysisError as exc:
                item["error"] = str(exc)
            outcome["evidence_path"] = f"evidence:{key}"
        self._stage(
            "evidence",
            "end",
            id=key,
            tool=tool,
            hypothesis=hypothesis,
            error=item.get("error"),
        )
        return {**evidence, key: item}

    def _check_columns(self, check: Check) -> None:
        columns = [check.column] if check.column else []
        columns += [c.column for c in (check.cohort_a or []) + (check.cohort_b or [])]
        rejected = [c for c in columns if c not in self.features]
        if rejected:
            raise analyses.AnalysisError(
                f"{rejected} are not approved pre-outcome features for this task."
            )

    def _execute(self, check: Check) -> dict[str, Any]:
        self._check_columns(check)
        if check.tool == "segment_rates":
            assert check.column is not None
            return analyses.segment_rates(self.frame, self.labels, check.column)
        return analyses.compare_cohorts(
            self.frame,
            self.labels,
            check.cohort_a or [],
            check.cohort_b,
            check.cohort_label or "cohort A",
        )

    def _context(self, state: InvestigationState) -> dict[str, Any]:
        return {
            "question": state["question"],
            "approved_features": self.features,
            "evidence": state["evidence"],
        }

    # -- nodes ---------------------------------------------------------------------------------

    def gather(self, state: InvestigationState) -> InvestigationState:
        self._stage("gather", "start")
        evidence: dict[str, dict[str, Any]] = {}
        evidence = self._record(
            evidence,
            "overview",
            {},
            lambda: analyses.overview(self.labels, self.frame, self.features),
        )
        evidence = self._record(
            evidence,
            "rank_associations",
            {"features": self.features},
            lambda: analyses.rank_associations(self.frame, self.labels, self.features),
        )
        evidence = self._record(
            evidence,
            "model_summary",
            {"run_id": str(self.run.run_id)},
            lambda: model_summary(self.run),
        )
        return {"evidence": evidence}

    def plan(self, state: InvestigationState) -> InvestigationState:
        self._stage("plan", "start")
        prompt = load_prompt("investigator_plan")
        plan = self.gateway.structured(
            prompt.text,
            self._context(state),
            InvestigationPlan,
            max_tokens=2048,
            name="investigator:plan",
            prompt_label=prompt.label,
            deadline=self.deadline,
        )
        self._stage("plan", "end", hypotheses=[check.hypothesis for check in plan.checks])
        return {
            "plan": plan.model_dump(mode="json"),
            "pending": [check.model_dump(mode="json") for check in plan.checks],
        }

    def analyze(self, state: InvestigationState) -> InvestigationState:
        evidence = state["evidence"]
        done = {json.dumps(item["arguments"], sort_keys=True) for item in evidence.values()}
        for raw in state.get("pending", []):
            check = Check.model_validate(raw)
            arguments = check.model_dump(mode="json", exclude={"hypothesis"}, exclude_none=True)
            if json.dumps(arguments, sort_keys=True) in done:
                continue  # never run the same analysis twice
            done.add(json.dumps(arguments, sort_keys=True))
            evidence = self._record(
                evidence,
                check.tool,
                arguments,
                lambda check=check: self._execute(check),
                check.hypothesis,
            )
        return {"evidence": evidence, "pending": []}

    def follow_up(self, state: InvestigationState) -> InvestigationState:
        if not self._can_call():
            return {"followed_up": True, "pending": []}
        self._stage("follow_up", "start")
        prompt = load_prompt("investigator_followup")
        try:
            decision = self.gateway.structured(
                prompt.text,
                self._context(state),
                FollowUp,
                max_tokens=768,
                name="investigator:follow_up",
                prompt_label=prompt.label,
                deadline=self.deadline,
            )
        except WorkflowError as exc:
            # Optional step: the gathered evidence still supports a report.
            self._stage("follow_up", "skipped", reason=exc.code)
            return {"followed_up": True, "pending": []}
        checks = [] if decision.done else decision.checks
        self._stage(
            "follow_up",
            "end",
            rationale=decision.rationale,
            hypotheses=[check.hypothesis for check in checks],
        )
        return {
            "followed_up": True,
            "pending": [check.model_dump(mode="json") for check in checks],
        }

    def write(self, state: InvestigationState) -> InvestigationState:
        revising = "verification" in state
        self._stage("write", "start", revision=revising)
        prompt = load_prompt("investigator_write")
        context = self._context(state)
        if revising:
            context["previous_report"] = state["report"]
            context["verifier_problems"] = feedback(state["verification"])
        try:
            report = self.gateway.structured(
                prompt.text,
                context,
                InvestigationReport,
                name="investigator:revise" if revising else "investigator:write",
                prompt_label=prompt.label,
                deadline=self.deadline,
            )
        except WorkflowError as exc:
            if not revising:
                raise
            # A failed revision keeps the draft; finalize withholds what failed verification.
            self._stage("write", "skipped", reason=exc.code, revision=True)
            return {"report": state["report"]}
        return {"report": report.model_dump(mode="json")}

    def verify(self, state: InvestigationState) -> InvestigationState:
        report = InvestigationReport.model_validate(state["report"])
        verification = verify_report(report, state["evidence"])
        self._stage(
            "verify",
            "end",
            passed=verification["passed"],
            problems=feedback(verification),
        )
        return {"verification": verification, "revisions": state.get("revisions", 0)}

    def finish(self, state: InvestigationState) -> InvestigationState:
        report = InvestigationReport.model_validate(state["report"])
        result = finalize(report, state["verification"])
        self._stage("finalize", "end", outcome=result["status"])
        return {"result": result}

    def revise_counted(self, state: InvestigationState) -> InvestigationState:
        return {"revisions": state.get("revisions", 0) + 1}

    # -- routing -------------------------------------------------------------------------------

    def after_analyze(self, state: InvestigationState) -> Literal["follow_up", "write"]:
        return "write" if state.get("followed_up") else "follow_up"

    def after_follow_up(self, state: InvestigationState) -> Literal["analyze", "write"]:
        return "analyze" if state.get("pending") else "write"

    def after_verify(self, state: InvestigationState) -> Literal["revise", "finalize"]:
        if state["verification"]["passed"] or state.get("revisions", 0) >= 1:
            return "finalize"
        return "revise" if self._can_call() else "finalize"

    def graph(self) -> Any:
        builder = StateGraph(InvestigationState)
        builder.add_node("gather", self.gather)
        builder.add_node("plan", self.plan)
        builder.add_node("analyze", self.analyze)
        builder.add_node("follow_up", self.follow_up)
        builder.add_node("write", self.write)
        builder.add_node("verify", self.verify)
        builder.add_node("revise", self.revise_counted)
        builder.add_node("finalize", self.finish)
        builder.add_edge(START, "gather")
        builder.add_edge("gather", "plan")
        builder.add_edge("plan", "analyze")
        builder.add_conditional_edges("analyze", self.after_analyze)
        builder.add_conditional_edges("follow_up", self.after_follow_up)
        builder.add_edge("write", "verify")
        builder.add_conditional_edges("verify", self.after_verify)
        builder.add_edge("revise", "write")
        builder.add_edge("finalize", END)
        return builder.compile()

    def invoke(self, question: str) -> InvestigationState:
        state: InvestigationState = self.graph().invoke(
            {"question": question, "evidence": {}, "revisions": 0, "followed_up": False},
            config={"recursion_limit": 25},
        )
        return state
