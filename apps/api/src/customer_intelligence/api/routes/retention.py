from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session

from customer_intelligence.agent.llm import LLMGateway
from customer_intelligence.agent.tracing import traced
from customer_intelligence.core.config import Settings, get_settings
from customer_intelligence.core.database import get_session
from customer_intelligence.schemas.retention import (
    ApplySchemaRequest,
    BriefingRequest,
    CampaignRequest,
    ROIRequest,
    RuleRequest,
    SchemaReviewRequest,
)
from customer_intelligence.schemas.task import TaskResponse
from customer_intelligence.schemas.workspace import BusinessAssumptions
from customer_intelligence.services import retention
from customer_intelligence.services.workspace import remember_assumptions

router = APIRouter(prefix="/retention", tags=["Retention actions"])
DB = Annotated[Session, Depends(get_session)]
Config = Annotated[Settings, Depends(get_settings)]


@router.post("/schema-review")
def schema_review(request: SchemaReviewRequest, session: DB, settings: Config) -> dict:
    with traced(session, "action.schema_review"):
        return retention.analyze_schema_semantics(request, session, settings)


@router.post("/apply-schema")
def apply_schema(request: ApplySchemaRequest, session: DB, settings: Config) -> TaskResponse:
    return retention.apply_schema(request, session, settings)


@router.post("/campaign")
def campaign(request: CampaignRequest, session: DB, settings: Config) -> dict:
    with traced(session, "action.campaign"):
        return retention.generate_retention_campaign(request, session, settings)


@router.post("/roi")
def roi(request: ROIRequest, session: DB, settings: Config) -> dict:
    result = retention.calculate_intervention_roi(request, session, settings)
    # The person typed these; keep them so the next plan and the assistant start from them.
    remember_assumptions(
        session,
        BusinessAssumptions.model_validate(
            request.model_dump(
                include={
                    "budget",
                    "contact_cost",
                    "offer_cost",
                    "assumed_save_rate",
                    "retained_value",
                    "currency",
                }
            )
        ),
        source="budget_planner",
    )
    return result


@router.post("/rule-challenger")
def rule(request: RuleRequest, session: DB, settings: Config) -> dict:
    with traced(session, "action.rule_challenger"):
        return retention.challenge_business_rule(request, session, settings)


@router.post("/briefing")
def briefing(request: BriefingRequest, session: DB, settings: Config) -> dict:
    with traced(session, "action.executive_briefing"):
        return retention.executive_briefing(request, session, settings)


@router.post("/provider-check")
def provider_check(session: DB, settings: Config) -> dict:
    with traced(session, "provider_check"), LLMGateway(settings) as gateway:
        result = gateway.complete(
            name="provider_check",
            messages=[{"role": "user", "content": "Reply OK."}],
            max_tokens=64,
        )
        return {"reachable": bool(result.choices), "model": settings.nebius_model}
