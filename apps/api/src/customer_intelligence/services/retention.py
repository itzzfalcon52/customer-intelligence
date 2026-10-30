"""Retention actions reuse scoped datasets/runs; all evaluation stays on development rows."""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from hashlib import sha256
from uuid import NAMESPACE_URL, UUID, uuid5

import numpy as np
import pandas as pd
from openai import OpenAI
from sqlalchemy import text
from sqlmodel import Session

from customer_intelligence.agent.provider import structured
from customer_intelligence.core.config import Settings
from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.ml.evaluation import evaluate_binary, positive_scores
from customer_intelligence.ml.schema_checks import obvious_leakage
from customer_intelligence.models.conversation import AssistantLease
from customer_intelligence.models.dataset import Dataset
from customer_intelligence.models.task import Task
from customer_intelligence.schemas.retention import (
    AIRequest,
    ApplySchemaRequest,
    BriefingRequest,
    CampaignDrafts,
    CampaignRequest,
    ExecutiveBriefing,
    ROIRequest,
    RuleProposal,
    RuleRequest,
    SchemaReasoning,
    SchemaReviewRequest,
)
from customer_intelligence.schemas.task import TaskCreateRequest, TaskResponse
from customer_intelligence.services.analysis import run_frame
from customer_intelligence.services.artifacts import publish_json, read_json
from customer_intelligence.services.profiling import load_dataset_frame, profile_dataset
from customer_intelligence.services.runs import load_pipeline, read_training_run
from customer_intelligence.services.scoring import read_customers, read_score
from customer_intelligence.services.tasks import create_task


@contextmanager
def action_lock(
    session: Session, key: UUID, dataset_id: UUID, related_dataset_id: UUID | None = None
) -> Iterator[None]:
    """Protect every source from deletion and serialize identical action retries."""
    session.rollback()
    session.exec(text("BEGIN IMMEDIATE"))  # type: ignore[call-overload]
    resources = list(
        dict.fromkeys([dataset_id, *([related_dataset_id] if related_dataset_id else [])])
    )
    owned = []
    for index, resource in enumerate(resources):
        lease_key = str(key if index == 0 else uuid5(NAMESPACE_URL, f"{key}:dependency:{resource}"))
        lease = session.get(AssistantLease, lease_key)
        if (
            lease
            and (datetime.now(UTC) - lease.created_at.replace(tzinfo=UTC)).total_seconds() < 300
        ):
            session.rollback()
            raise WorkflowError("This action is already being processed.", 409)
        if lease:
            session.delete(lease)
            session.flush()
        lease = AssistantLease(idempotency_key=lease_key, dataset_id=resource)
        owned.append((lease_key, lease.owner_id))
        session.add(lease)
    session.commit()
    try:
        yield
    finally:
        session.rollback()
        for lease_key, owner in owned:
            current = session.get(AssistantLease, lease_key)
            if current and current.owner_id == owner:
                session.delete(current)
        session.commit()


def action_id(kind: str, key: UUID) -> UUID:
    return uuid5(NAMESPACE_URL, f"retention:{kind}:{key}")


def saved_action(
    settings: Settings, kind: str, request: AIRequest
) -> tuple[UUID, str, dict | None]:
    uid = action_id(kind, request.idempotency_key)
    digest = sha256(request.model_dump_json().encode()).hexdigest()
    path = settings.data_directory / "analyses" / str(uid) / "manifest.json"
    if path.exists():
        previous = read_json(path)
        if not isinstance(previous, dict) or previous.get("request_sha256") != digest:
            raise WorkflowError("This action key was used for different inputs.", 409)
        return uid, digest, previous
    return uid, digest, None


def save_action(settings: Settings, kind: str, uid: UUID, digest: str, payload: dict) -> dict:
    result = {
        "id": str(uid),
        "kind": kind,
        "created_at": datetime.now(UTC).isoformat(),
        "request_sha256": digest,
        **payload,
    }
    publish_json(settings.data_directory / "analyses", {"manifest.json": result}, uid)
    return result


def analyze_schema_semantics(
    request: SchemaReviewRequest, session: Session, settings: Settings, client: OpenAI | None = None
) -> dict:
    task = session.get(Task, request.task_id)
    if task is None:
        raise WorkflowError("Task not found.", 404)
    dataset = session.get(Dataset, task.dataset_id)
    if dataset is None:
        raise WorkflowError("Dataset not found.", 404)
    with action_lock(session, request.idempotency_key, dataset.id):
        uid, digest, previous = saved_action(settings, "schema_review", request)
        if previous:
            return previous
        load_dataset_frame(dataset, settings, expected_sha256=task.dataset_sha256)
        from customer_intelligence.services.privacy import ai_profile

        profile = profile_dataset(dataset, settings)
        evidence = {
            "target": task.target_column,
            "positive_label": task.positive_label,
            "selected_features": task.feature_columns,
            "id_column": task.id_column,
            "columns": ai_profile(session, profile)["columns"],
        }
        result = structured(
            settings,
            (
                "Review each selected feature for pre-outcome availability, "
                "identifiers, high-cardinality text, and semantic leakage. A "
                "cancellation reason/date is post-outcome. Ambiguous timing is review, "
                "not proven leakage. Do not infer causation or assume labels have a "
                "time horizon. Produce findings for selected features only. No raw "
                "customer values are supplied."
            ),
            evidence,
            SchemaReasoning,
            client,
        )
        names = [f.column for f in result.findings]
        if len(names) != len(set(names)) or set(names) != set(task.feature_columns):
            raise WorkflowError(
                "Schema reasoning must cover each selected feature exactly once.", 502
            )
        findings = [f.model_dump() for f in result.findings]
        for finding in findings:
            if obvious_leakage(finding["column"]):
                finding.update(
                    decision="exclude",
                    reason=(
                        "Column name denotes an outcome date or reason; "
                        "excluded from the proposed task."
                    ),
                )
        safe = [f["column"] for f in findings if f["decision"] == "keep"]
        return save_action(
            settings,
            "schema_review",
            uid,
            digest,
            {
                "task_id": str(task.id),
                "dataset_id": str(dataset.id),
                "summary": result.summary,
                "findings": findings,
                "questions": result.questions,
                "proposed_features": safe,
                "requires_confirmation": True,
                "provider_model": settings.nebius_model,
                "warning": (
                    "Semantic suggestions are not proof of feature timing. The "
                    "saved task is unchanged; confirm to create a revised task. No raw "
                    "sample rows were sent."
                ),
            },
        )


def apply_schema(request: ApplySchemaRequest, session: Session, settings: Settings) -> TaskResponse:
    review = read_json(
        settings.data_directory / "analyses" / str(request.review_id) / "manifest.json"
    )
    if (
        not isinstance(review, dict)
        or review.get("id") != str(request.review_id)
        or review.get("kind") != "schema_review"
    ):
        raise WorkflowError("Schema review not found.", 404)
    task = session.get(Task, UUID(review["task_id"]))
    if task is None or str(task.dataset_id) != review["dataset_id"]:
        raise WorkflowError("Original task not found.", 404)
    if (settings.data_directory / "finalized_tasks" / f"{task.id}.json").exists():
        raise WorkflowError(
            "Final test was already revealed; this review cannot revise a frozen task.", 409
        )
    dataset = session.get(Dataset, task.dataset_id)
    if dataset is None or not review["proposed_features"]:
        raise WorkflowError("No safe features remain. Review the source data before training.")
    load_dataset_frame(dataset, settings, expected_sha256=task.dataset_sha256)
    confirmed = TaskCreateRequest(
        target_column=task.target_column,
        positive_label=task.positive_label,
        id_column=task.id_column,
        feature_columns=review["proposed_features"],
        features_available_at_prediction=True,
    )
    # Repeated confirmation returns the same equivalent task instead of duplicating it.
    from sqlmodel import select

    for existing in session.exec(select(Task).where(Task.dataset_id == dataset.id)).all():
        if (
            existing.target_column == task.target_column
            and existing.positive_label == task.positive_label
            and existing.id_column == task.id_column
            and existing.feature_columns == confirmed.feature_columns
            and existing.dataset_sha256 == task.dataset_sha256
        ):
            return TaskResponse.model_validate(existing)
    return TaskResponse.model_validate(create_task(dataset, confirmed, settings, session))


def generate_retention_campaign(
    request: CampaignRequest, session: Session, settings: Settings, client: OpenAI | None = None
) -> dict:
    score = read_score(request.score_id, settings.data_directory)
    run = read_training_run(score.run_id, settings.data_directory)
    with action_lock(session, request.idempotency_key, run.task.dataset_id, score.dataset_id):
        uid, digest, previous = saved_action(settings, "campaign", request)
        if previous:
            return previous
        if len(request.permitted_features) != len(set(request.permitted_features)) or not set(
            request.permitted_features
        ) <= set(run.task.feature_columns):
            raise WorkflowError("Choose distinct model features for personalization.")
        # Direct identifiers and sensitive/demographic features never cross the provider boundary.
        from customer_intelligence.services.privacy import withheld

        if withheld(session, list(request.permitted_features)):
            raise WorkflowError(
                "Direct identifiers or sensitive/demographic fields cannot be sent for "
                "outreach personalization."
            )
        customers = sorted(
            (c for c in read_customers(score, settings.data_directory) if c.group != "holdout"),
            key=lambda c: c.rank,
        )[:5]
        dataset = session.get(Dataset, score.dataset_id)
        if dataset is None:
            raise WorkflowError("Scoring dataset not found.", 404)
        frame = load_dataset_frame(dataset, settings, expected_sha256=score.dataset_sha256)
        pipeline = load_pipeline(run, settings.data_directory)
        training = run_frame(session, settings, run).iloc[run.split.row_assignments["train"]]
        schema = pipeline.named_steps["preprocessing"].named_steps["schema"]
        facts = []
        for customer in customers:
            row = frame.iloc[[customer.row_reference - 1]].loc[:, run.task.feature_columns]
            values: dict[str, str | float | None] = {}
            sensitivity: list[dict] = []
            for feature in request.permitted_features:
                value = row[feature].iloc[0]
                # Only finite numeric or low-cardinality categorical facts; no free text or emails.
                if pd.isna(value):
                    values[feature] = None
                elif feature in schema.numeric_columns_:
                    values[feature] = float(value)
                elif (
                    training[feature].nunique() <= 30
                    and len(str(value)) <= 60
                    and not re.search(r"@|https?://|\\n", str(value))
                ):
                    values[feature] = str(value)
                else:
                    raise WorkflowError(
                        f"{feature}: unsuitable free-text or high-cardinality personalization "
                        f"field."
                    )
                source = training[feature].dropna()
                reference = (
                    str(pd.to_numeric(source).median())
                    if feature in schema.numeric_columns_
                    else str(source.mode().iloc[0])
                )
                alternate = row.copy()
                alternate[feature] = reference
                sensitivity.append(
                    {
                        "feature": feature,
                        "reference": reference,
                        "score_change_if_replaced": positive_scores(pipeline, alternate)[0]
                        - customer.risk_score,
                    }
                )
            facts.append(
                {
                    "row_reference": customer.row_reference,
                    "features": values,
                    "model_sensitivity": sensitivity,
                }
            )
        drafts = structured(
            settings,
            (
                "Write one retention draft per supplied row, using only supplied "
                "product/approved offer and permitted facts. Never claim a feature "
                "caused churn, mention internal risk scores, reveal demographic "
                "assumptions, fabricate a support history, promise unapproved "
                "discounts, or invent a recipient name. Use a neutral greeting. Model "
                "sensitivity is association, not causality. Do not put numeric account "
                "data in the message unless useful and supplied. Return "
                "evidence_features listing only supplied fields actually used. "
                "Reflect at least one relevant supplied fact in the wording when possible. "
                "If facts are identical, similar wording is acceptable; never invent differences. "
                "Drafts require human review; nothing is sent."
            ),
            {
                "channel": request.channel,
                "product_name": request.product_name,
                "approved_offer": request.approved_offer,
                "customers": facts,
            },
            CampaignDrafts,
            client,
        )
        refs = [d.row_reference for d in drafts.drafts]
        if (
            len(set(refs)) != len(refs)
            or set(refs) != {c.row_reference for c in customers}
            or any(
                not set(d.evidence_features) <= set(request.permitted_features)
                for d in drafts.drafts
            )
        ):
            raise WorkflowError(
                "Generated drafts do not match the permitted customers or evidence.", 502
            )
        local_ids = {c.row_reference: c.customer_id for c in customers}
        return save_action(
            settings,
            "campaign",
            uid,
            digest,
            {
                "run_id": str(run.run_id),
                "dataset_id": str(run.task.dataset_id),
                "score_id": str(score.id),
                "channel": request.channel,
                "product_name": request.product_name,
                "approved_offer": request.approved_offer,
                "permitted_features": request.permitted_features,
                "drafts": [
                    {**d.model_dump(), "customer_id": local_ids[d.row_reference]}
                    for d in drafts.drafts
                ],
                "evidence": facts,
                "status": "draft_only",
                "provider_model": settings.nebius_model,
                "warning": (
                    "AI-written drafts need review. No messages have been sent. "
                    "Sensitivity is not a causal explanation or evidence the offer will "
                    "work."
                ),
            },
        )


def calculate_intervention_roi(request: ROIRequest, session: Session, settings: Settings) -> dict:
    run = read_training_run(request.run_id, settings.data_directory)
    pipeline = load_pipeline(run, settings.data_directory)
    validation = run_frame(session, settings, run).iloc[run.split.row_assignments["validation"]]
    labels = np.asarray(
        [run.task.label_mapping[str(v)] for v in validation[run.task.target_column]]
    )
    scores = np.asarray(positive_scores(pipeline, validation.loc[:, run.task.feature_columns]))
    order = np.argsort(-scores, kind="stable")
    cumulative = np.cumsum(labels[order])
    population = request.population_size
    current_rows = None
    if request.score_id:
        score = read_score(request.score_id, settings.data_directory)
        if score.run_id != run.run_id:
            raise WorkflowError("Scoring batch belongs to another experiment.")
        current_rows = sorted(read_customers(score, settings.data_directory), key=lambda c: c.rank)
        population = len(current_rows)
    # Reserve the full discount for every contact: never exceed budget even if everyone redeems.
    unit_cost = request.contact_cost + request.offer_cost
    maximum = min(population, int(request.budget // unit_cost))
    ks = np.arange(1, maximum + 1)
    validation_ks = np.maximum(1, np.ceil(ks / population * len(labels)).astype(int))
    precisions = cumulative[validation_ks - 1] / validation_ks if maximum else np.array([])
    benefit = ks * precisions * request.assumed_save_rate * request.retained_value
    net = benefit - ks * unit_cost
    # Zero contacts is a real option when all modeled interventions lose money.
    chosen = int(np.argmax(net)) if len(net) and float(net.max()) > 0 else None
    k = int(ks[chosen]) if chosen is not None else 0
    points = sorted(
        set(
            [
                0,
                *np.linspace(0, max(maximum - 1, 0), min(50, maximum), dtype=int).tolist(),
                *([chosen] if chosen is not None else []),
            ]
        )
    )
    curve = [
        {
            "contacts": int(ks[i]),
            "validation_precision_at_fraction": float(precisions[i]),
            "scenario_net_value": float(net[i]),
            "reserved_cost": float(ks[i] * unit_cost),
        }
        for i in points
        if i < maximum
    ]
    from customer_intelligence.ml.diagnostics import wilson_interval

    evidence_count = int(validation_ks[chosen]) if chosen is not None else 0
    evidence_tp = int(cumulative[evidence_count - 1]) if evidence_count else 0
    return {
        "validation_evidence_count": evidence_count,
        "validation_precision_interval": wilson_interval(evidence_tp, evidence_count)
        if evidence_count
        else None,
        "small_sample_warning": (
            "The selected contact fraction has fewer than 30 validation customers; "
            "its precision estimate is unstable."
        )
        if 0 < evidence_count < 30
        else None,
        "run_id": str(run.run_id),
        "score_id": str(request.score_id) if request.score_id else None,
        "recommended_contacts": k,
        "maximum_affordable_contacts": maximum,
        "population_size": population,
        "reserved_cost": k * unit_cost,
        "budget_remaining": request.budget - k * unit_cost,
        "scenario_gross_value": float(benefit[chosen]) if chosen is not None else 0,
        "scenario_net_value": float(net[chosen]) if chosen is not None else 0,
        "validation_precision_at_fraction": float(precisions[chosen])
        if chosen is not None
        else None,
        "assumptions": request.model_dump(mode="json"),
        "curve": curve,
        "shortlist": [c.model_dump(mode="json") for c in current_rows[: min(k, 100)]]
        if current_rows
        else [],
        "warning": (
            "Scenario, not measured ROI: assumes validation ranking "
            "transfers to current customers, a constant user-supplied intervention "
            "effect, and retained value. Raw risk scores are not treated as "
            "calibrated probabilities. Costs reserve contact + offer for every "
            "contact; no causal uplift has been measured."
        ),
    }


def challenge_business_rule(
    request: RuleRequest, session: Session, settings: Settings, client: OpenAI | None = None
) -> dict:
    run = read_training_run(request.run_id, settings.data_directory)
    with action_lock(session, request.idempotency_key, run.task.dataset_id):
        uid, digest, previous = saved_action(settings, "rule_challenger", request)
        if previous:
            return previous
        frame = run_frame(session, settings, run)
        training = frame.iloc[run.split.row_assignments["train"]]
        validation = frame.iloc[run.split.row_assignments["validation"]]
        dataset = session.get(Dataset, run.task.dataset_id)
        assert dataset is not None
        from customer_intelligence.services.profiling import build_profile

        profile = build_profile(training.loc[:, run.task.feature_columns], dataset)
        proposal = structured(
            settings,
            (
                "Propose a simple AND business rule of at most three conditions on "
                "supplied model features using column names and TRAINING-only "
                "summaries. Operators lt/le/gt/ge require numeric values; eq/ne "
                "support categorical. Do not write Python, invent an activity history, "
                "or claim any measured performance. The server will evaluate the rule "
                "on validation rows after proposal."
            ),
            {
                "target": run.task.target_column,
                "columns": [c.model_dump(mode="json") for c in profile.columns],
            },
            RuleProposal,
            client,
        )
        mask = np.ones(len(validation), dtype=bool)
        numeric = (
            load_pipeline(run, settings.data_directory)
            .named_steps["preprocessing"]
            .named_steps["schema"]
            .numeric_columns_
        )
        for condition in proposal.conditions:
            if condition.column not in run.task.feature_columns:
                raise WorkflowError("Rule referenced an unapproved feature.", 502)
            series = validation[condition.column]
            value: str | float = condition.value
            if condition.column in numeric:
                try:
                    value = float(value)
                except ValueError:
                    raise WorkflowError("Rule contains a nonnumeric threshold.", 502) from None
                if not np.isfinite(value):
                    raise WorkflowError("Rule threshold must be finite.", 502)
                series = pd.to_numeric(series, errors="coerce")
            elif condition.operator not in {"eq", "ne"}:
                raise WorkflowError("Text rule comparisons only support equality.", 502)
            comparison = {
                "lt": "__lt__",
                "le": "__le__",
                "gt": "__gt__",
                "ge": "__ge__",
                "eq": "__eq__",
                "ne": "__ne__",
            }[condition.operator]
            mask &= getattr(series, comparison)(value).fillna(False).to_numpy(dtype=bool)
        labels = [run.task.label_mapping[str(v)] for v in validation[run.task.target_column]]
        metrics = evaluate_binary(labels, mask.astype(float).tolist())
        return save_action(
            settings,
            "rule_challenger",
            uid,
            digest,
            {
                "run_id": str(run.run_id),
                "proposal": proposal.model_dump(),
                "partition": "validation",
                "metrics": metrics.model_dump(),
                "warning": (
                    "Rule proposed from training summaries, evaluated on "
                    "validation. Repeated proposals overfit validation. This binary rule "
                    "has only two ranking levels; AP is not directly equivalent to a "
                    "continuous score curve. No arbitrary code was executed."
                ),
            },
        )


def executive_briefing(
    request: BriefingRequest, session: Session, settings: Settings, client: OpenAI | None = None
) -> dict:
    run = read_training_run(request.run_id, settings.data_directory)
    with action_lock(session, request.idempotency_key, run.task.dataset_id):
        uid, digest, previous = saved_action(settings, "executive_briefing", request)
        if previous:
            return previous
        result = structured(
            settings,
            (
                "Write three concise executive paragraphs: comparison and baseline, "
                "precision/recall implications, next action and limitations. Use only "
                "supplied results. Never invent measured revenue, causal drivers, "
                "future horizons or intervention success. Validation is development "
                "evidence, not final test performance."
            ),
            {"comparison": run.report.model_dump(mode="json"), "calibration": run.calibration},
            ExecutiveBriefing,
            client,
        )
        return save_action(
            settings,
            "executive_briefing",
            uid,
            digest,
            {
                "run_id": str(run.run_id),
                "paragraphs": result.paragraphs,
                "provider_model": settings.nebius_model,
                "warning": (
                    "AI narrative; refer to the saved measured results for authoritative numbers."
                ),
            },
        )
