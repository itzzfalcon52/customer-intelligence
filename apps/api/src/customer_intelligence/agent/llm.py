"""The single gateway for every model call: routing, bounded retries, repair, usage and tracing."""

import json
import random
import time
from typing import Any, Literal, cast

from openai import APIConnectionError, APIError, APIStatusError, APITimeoutError, OpenAI
from openai.types.chat import ChatCompletion
from pydantic import BaseModel

from customer_intelligence.agent import provider
from customer_intelligence.agent.prompts import inline_label, load_prompt
from customer_intelligence.agent.tracing import current_tracer
from customer_intelligence.core.config import Settings
from customer_intelligence.core.errors import WorkflowError

Tier = Literal["primary", "fast"]
_sleep = time.sleep  # replaced in tests


def _retryable(exc: APIError) -> bool:
    if isinstance(exc, APITimeoutError | APIConnectionError):
        return True
    return isinstance(exc, APIStatusError) and (exc.status_code == 429 or exc.status_code >= 500)


class LLMGateway:
    def __init__(self, settings: Settings, client: OpenAI | None = None) -> None:
        self.settings = settings
        self._client = client
        self._owned = client is None

    def __enter__(self) -> "LLMGateway":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            # Resolved through the module so tests can substitute the provider adapter.
            self._client = provider.provider_client(self.settings)
        return self._client

    def close(self) -> None:
        if self._owned and self._client is not None:
            self._client.close()
            self._client = None

    def model_for(self, tier: Tier) -> str:
        if tier == "fast" and self.settings.nebius_fast_model:
            return self.settings.nebius_fast_model
        return self.settings.nebius_model or "test-model"

    @property
    def routes_by_tier(self) -> bool:
        return self.model_for("fast") != self.model_for("primary")

    def cost(self, model: str, input_tokens: int | None, output_tokens: int | None) -> float | None:
        price = self.settings.model_prices.get(model)
        if price is None or input_tokens is None or output_tokens is None:
            return None
        return round((input_tokens * price[0] + output_tokens * price[1]) / 1_000_000, 8)

    def complete(
        self,
        *,
        name: str,
        messages: list[dict[str, Any]],
        max_tokens: int,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: Any = None,
        tier: Tier = "primary",
        deadline: float | None = None,
        prompt_version: str | None = None,
    ) -> ChatCompletion:
        model = self.model_for(tier)
        tracer = current_tracer()
        if tracer:
            tracer.model_started(name, model)
        options: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "extra_body": provider.completion_options(self.settings, model),
        }
        if tools is not None:
            options["tools"] = tools
        if tool_choice is not None:
            options["tool_choice"] = tool_choice
        started = time.monotonic()
        attempts = 0
        response: ChatCompletion | None = None
        error_code: str | None = None
        try:
            while True:
                attempts += 1
                timeout: float = self.settings.nebius_timeout_seconds
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise WorkflowError(
                            "Assistant time budget exceeded.", 502, "time_budget_exceeded"
                        )
                    timeout = min(timeout, remaining)
                try:
                    response = self.client.with_options(timeout=timeout).chat.completions.create(
                        **options
                    )
                    return response
                except APIError as exc:
                    delay = min(0.5 * 2 ** (attempts - 1), 4.0) + random.uniform(0, 0.25)
                    out_of_time = deadline is not None and deadline - time.monotonic() < delay + 1
                    if (
                        not _retryable(exc)
                        or attempts > self.settings.nebius_max_retries
                        or out_of_time
                    ):
                        raise provider.provider_error(exc) from None
                    _sleep(delay)
        except WorkflowError as exc:
            error_code = exc.code
            raise
        finally:
            if tracer:
                usage = response.usage if response is not None else None
                input_tokens = usage.prompt_tokens if usage else None
                output_tokens = usage.completion_tokens if usage else None
                choice = response.choices[0] if response is not None and response.choices else None
                tracer.record_model(
                    name=name,
                    model=response.model if response is not None else model,
                    prompt_version=prompt_version,
                    status="succeeded" if response is not None else "failed",
                    error_code=error_code,
                    attempts=attempts,
                    finish_reason=choice.finish_reason if choice else None,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=self.cost(model, input_tokens, output_tokens),
                    duration_ms=round((time.monotonic() - started) * 1000),
                )

    def structured[T: BaseModel](
        self,
        instruction: str,
        evidence: dict[str, Any],
        schema: type[T],
        max_tokens: int = 3072,
        *,
        name: str | None = None,
        prompt_label: str | None = None,
        deadline: float | None = None,
    ) -> T:
        """Force one typed function result; allow one repair attempt after validation fails."""
        encoded = json.dumps(evidence, allow_nan=False)
        if len(encoded.encode("utf-8")) > 60_000:
            raise WorkflowError(
                "AI context is too large. Narrow the selected features or experiment.",
                400,
                "context_too_large",
            )
        guard = load_prompt("structured_guard")
        system = instruction + " " + guard.text
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": encoded},
        ]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "deliver_result",
                    "description": "Return the typed result grounded in evidence.",
                    "parameters": schema.model_json_schema(),
                },
            }
        ]
        for attempt in (1, 2):
            response = self.complete(
                name=(name or f"structured:{schema.__name__}")
                + (":repair" if attempt == 2 else ""),
                messages=messages,
                tools=tools,
                tool_choice={"type": "function", "function": {"name": "deliver_result"}},
                max_tokens=max_tokens,
                deadline=deadline,
                prompt_version=(prompt_label or inline_label(instruction)) + "|" + guard.label,
            )
            calls = response.choices[0].message.tool_calls if response.choices else None
            try:
                if (
                    calls
                    and len(calls) == 1
                    and calls[0].type == "function"
                    and calls[0].function.name == "deliver_result"
                ):
                    return schema.model_validate_json(calls[0].function.arguments)
                # Some compatible hosts return a JSON message despite a forced function choice.
                # Accept only the same strictly validated schema, never free-form prose or code.
                if not calls and response.choices and response.choices[0].message.content:
                    return schema.model_validate_json(response.choices[0].message.content)
                problem = "No deliver_result function call was returned."
            except ValueError as exc:
                problem = describe_validation_error(exc)
            if response.choices and response.choices[0].finish_reason == "length":
                # Truncation explains any parse failure; say so instead of the parse error.
                problem = (
                    "The previous response was cut off at the token limit; return a shorter "
                    "result through deliver_result."
                )
            if attempt == 2:
                raise WorkflowError(
                    "Nemotron returned an invalid result. Nothing was applied.",
                    502,
                    "provider_invalid_result",
                )
            # Only validation locations/messages are fed back; the rejected values are not.
            messages.append(
                {
                    "role": "user",
                    "content": "The previous result was rejected: "
                    + problem
                    + " Call deliver_result again with a result that satisfies the schema.",
                }
            )
        raise AssertionError("unreachable")


def describe_validation_error(exc: ValueError) -> str:
    """Locations and messages only; rejected input values are never echoed back."""
    errors = getattr(exc, "errors", None)
    if not callable(errors):
        return "The result was not valid JSON for the schema."
    details = cast(list[dict[str, Any]], errors(include_input=False, include_url=False))
    return "; ".join(
        f"{'.'.join(str(part) for part in item['loc']) or 'result'}: {item['msg']}"
        for item in details[:5]
    )
