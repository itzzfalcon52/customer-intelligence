"""Provider adapter: client construction, model options and typed failures.

All model calls go through agent/llm.py (LLMGateway), which adds retries, routing and tracing.
"""

import httpx
from openai import APIConnectionError, APIError, APIStatusError, APITimeoutError, OpenAI
from pydantic import BaseModel

from customer_intelligence.core.config import Settings
from customer_intelligence.core.errors import WorkflowError


def provider_client(settings: Settings, transport: httpx.BaseTransport | None = None) -> OpenAI:
    """Configured client; `transport` lets the eval harness record live HTTP exchanges."""
    if not settings.nebius_api_key or not settings.nebius_base_url or not settings.nebius_model:
        raise WorkflowError(
            "Configure Nebius API key, endpoint and model in apps/api/.env.",
            503,
            "provider_unconfigured",
        )
    return OpenAI(
        api_key=settings.nebius_api_key.get_secret_value(),
        base_url=str(settings.nebius_base_url),
        timeout=httpx.Timeout(settings.nebius_timeout_seconds, connect=20),
        max_retries=0,
        http_client=httpx.Client(
            trust_env=settings.nebius_trust_env,
            follow_redirects=False,
            transport=transport
            or httpx.HTTPTransport(retries=1, trust_env=settings.nebius_trust_env),
        ),
    )


def completion_options(settings: Settings, model: str | None = None) -> dict:
    # Verified for this model; do not send model-specific options to arbitrary replacements.
    if (model or settings.nebius_model) == "nvidia/Nemotron-3_5-Lightning":
        return {"chat_template_kwargs": {"enable_thinking": settings.nebius_enable_thinking}}
    return {}


def provider_error(exc: APIError) -> WorkflowError:
    if isinstance(exc, APITimeoutError):
        return WorkflowError(
            "Nemotron took too long to respond. Retry this request; your saved results are safe.",
            504,
            "provider_timeout",
        )
    if isinstance(exc, APIConnectionError):
        return WorkflowError(
            (
                "Cannot connect to Nebius. Check the API server’s internet, DNS and "
                "proxy settings, then retry."
            ),
            503,
            "provider_connection",
        )
    status = exc.status_code if isinstance(exc, APIStatusError) else None
    if status in {401, 403}:
        return WorkflowError(
            "Nebius rejected the API credentials or model access. Check the server configuration.",
            503,
            "provider_credentials",
        )
    if status == 429:
        return WorkflowError(
            "Nebius is rate-limiting this account. Check its credits and limits, then retry.",
            503,
            "provider_rate_limit",
        )
    return WorkflowError(
        "Nebius could not complete this request. Check model availability and retry.",
        502,
        "provider_failed",
    )


def structured[T: BaseModel](
    settings: Settings,
    instruction: str,
    evidence: dict,
    schema: type[T],
    client: OpenAI | None = None,
) -> T:
    """Typed single-result call; see LLMGateway.structured for retries and repair."""
    from customer_intelligence.agent.llm import LLMGateway

    with LLMGateway(settings, client) as gateway:
        return gateway.structured(instruction, evidence, schema)
