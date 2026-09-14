"""Chat-model factory: a role from `settings.default.yaml` becomes a configured model.

Every model call in Crossbid goes through OpenRouter, the single provider the project has
a key for (CLAUDE.md). Callers ask for a **role** -- `extract`, `cheap`, `judge` -- and
never for a slug, so switching models is a settings change and not a code change.

`extra_body={"usage": {"include": True}}` is what makes OpenRouter return the cost of each
response, which S5.2's per-node cost accounting reads. It is set here once so that no call
site can forget it.

**S3.4.4 adds the resilience, and it lives here rather than at each call site.** A model
call that times out is retried once and then reissued against the `fallback` slug
(`ResilientModel`). Two details make that sentence true rather than approximately true.
`ChatOpenAI` retries twice *by itself* by default, so `max_retries=0` is set below — without
it "one retry" would be one of ours on top of two of langchain's, three times the latency
before a fallback and a `llm_timeout_seconds` that bounded a third of the real wait. And the
fallback slug is a **different vendor**: the failure worth surviving is the primary route
being slow or down, and a second OpenAI slug shares that route.

BYOK -- a company running on its own OpenAI, Anthropic or OpenRouter key -- is S5.4-S5.6
and is **not** built. When it lands, it resolves a company's active provider into the
`api_key`/`base_url` pair below and this module grows a `company` argument; the plan's
`resolve(company, role)` is that signature. Today there is one route: the app's key.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any, Final, Protocol

import httpx
import openai
from langchain_openai import ChatOpenAI

from crossbid.settings import ModelRole, Settings

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL: Final = "https://openrouter.ai/api/v1"

USAGE_ACCOUNTING_EXTRA_BODY: Final[Mapping[str, Any]] = MappingProxyType(
    {"usage": {"include": True}}
)
"""Asks OpenRouter for token counts and cost on every response (verified 2026-09-10).
Read-only so that no caller can extend one model's body and affect the next."""

CHAT_ROLES: Final = (
    ModelRole.EXTRACT,
    ModelRole.CHEAP,
    ModelRole.JUDGE,
    ModelRole.FALLBACK,
)
"""The roles that resolve to a chat model. `embed` is a role in the settings file too, but
it names an embedding model and goes through `ingestion/embeddings.py` (S2.2.1).

`fallback` is here so that `verify_configured_models` probes it: a fallback slug nobody
checked is worth nothing, because the one moment it is used is the moment the primary has
already failed."""

PROBE_MAX_TOKENS: Final = 1

LANGCHAIN_RETRIES: Final = 0
"""`ChatOpenAI` retries twice of its own accord. Switched off so that `ResilientModel` is
the only thing retrying and "one retry, then the smaller model" describes what happens."""

RETRYABLE: Final[tuple[type[BaseException], ...]] = (
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.RateLimitError,
    openai.InternalServerError,
    httpx.TimeoutException,
    httpx.TransportError,
    TimeoutError,
)
"""Failures that are about the *route* and not about the request: a slow provider, a dropped
connection, a rate limit, a 5xx. Everything else — a refused slug, a malformed request, a
schema violation — is reproducible, so retrying it would spend the run budget on the same
answer. A schema violation has its own single re-ask in `check_loop`, one layer up, where
the corrective message can be written."""


class LlmError(RuntimeError):
    """A model could not be built or did not answer. Never carries a key."""


def chat_model(
    role: ModelRole,
    settings: Settings,
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> ChatOpenAI:
    """The chat model configured for `role`, pointed at OpenRouter.

    `temperature` and `max_tokens` default to the settings values; the overrides exist for
    calls whose shape is fixed regardless of tuning, such as the one-token slug probe.
    Constructing the model opens no connection.
    """
    if role not in CHAT_ROLES:
        raise LlmError(
            f"Role '{role.value}' is not a chat role. The embed slug names an embedding "
            "model; use the embeddings client (S2.2.1) instead."
        )

    runtime = settings.runtime
    return ChatOpenAI(
        model=runtime.models.for_role(role),
        api_key=settings.env.openrouter_api_key,
        base_url=OPENROUTER_BASE_URL,
        temperature=runtime.temperature if temperature is None else temperature,
        # `max_completion_tokens` is the alias of `ChatOpenAI.max_tokens`; the field name
        # itself is not accepted as a keyword.
        max_completion_tokens=runtime.max_tokens if max_tokens is None else max_tokens,
        timeout=runtime.agent.llm_timeout_seconds,
        max_retries=LANGCHAIN_RETRIES,
        extra_body=USAGE_ACCOUNTING_EXTRA_BODY,
    )


class ModelRunnable(Protocol):
    """The slice of a bound chat model `ResilientModel` stands in front of.

    Deliberately the same shape `check_loop.ModelRunnable` and `extract_reqs` already
    consume, so a resilient model is a drop-in for a bound one and no seam downstream has to
    know which it was handed.
    """

    async def ainvoke(self, messages: Any, /) -> Any: ...


class ResilientModel:
    """`primary`, retried once on a route failure, then `fallback`. S3.4.4.

    Wraps a **bound** runnable rather than a bare `ChatOpenAI`, and that is the reason it
    takes two of them instead of building its own: the checking loop binds the same model
    twice — tools for the turns, the verdict schema for the answer — and a wrapper that
    bound its own would have to know which. The caller binds both the primary and the
    fallback the same way and hands the pair here.

    Only `RETRYABLE` failures move it along. Anything else is raised on the first attempt,
    because a reproducible error answered three times is three times the cost and the same
    answer.
    """

    def __init__(self, primary: ModelRunnable, fallback: ModelRunnable) -> None:
        self._primary = primary
        self._fallback = fallback

    async def ainvoke(self, messages: Any, /) -> Any:
        """The primary's answer, or the retry's, or the fallback's. Raises the last failure.

        The fallback's own failure is what surfaces when everything fails: it is the most
        recent fact about the call, and the primary's timeout is already in the log.
        """
        try:
            return await self._primary.ainvoke(messages)
        except RETRYABLE as first:
            logger.warning("A model call failed (%s); retrying once", type(first).__name__)
        try:
            return await self._primary.ainvoke(messages)
        except RETRYABLE as second:
            logger.warning(
                "The retry failed too (%s); falling back to the smaller model",
                type(second).__name__,
            )
        return await self._fallback.ainvoke(messages)


def resilient(primary: ModelRunnable, fallback: ModelRunnable) -> ResilientModel:
    """`ResilientModel`, as a function so a call site reads as what it does."""
    return ResilientModel(primary, fallback)


def probe_chat_model(model: ChatOpenAI) -> None:
    """One token out of `model`, to prove the slug answers on this account. Hits the API."""
    model.invoke([("human", "ping")])


def verify_configured_models(
    settings: Settings, *, probe: Callable[[ChatOpenAI], None] = probe_chat_model
) -> None:
    """Confirm every configured chat slug actually answers -- opt-in, off by default.

    ADR-0005: presence in OpenRouter's `/models` does **not** mean a model is usable. Under
    this account's data policy eleven catalogued models return HTTP 404, and one of them
    was the slug the plan had named for the eval judge. The ADR's conclusion is that a
    configured slug must be confirmed with a live call and that startup should fail fast on
    one that does not answer.

    It stays behind `VERIFY_MODEL_SLUGS` because the call costs money and needs a real key:
    CI has neither, and no unit test may open a socket. Run it deliberately after changing
    a slug -- `VERIFY_MODEL_SLUGS=true` on one boot.

    The embed slug is not probed here: a chat call cannot exercise an embedding model, so
    the embeddings client verifies its own (S2.2.1).
    """
    if not settings.env.verify_model_slugs:
        return

    for role in CHAT_ROLES:
        slug = settings.runtime.models.for_role(role)
        try:
            probe(chat_model(role, settings, max_tokens=PROBE_MAX_TOKENS))
        except Exception as exc:
            raise LlmError(
                f"The model slug '{slug}' configured for role '{role.value}' did not "
                "answer on this account. A slug can be listed in OpenRouter's catalogue "
                "and still be refused by the account's data policy (ADR-0005); check it "
                "with a one-token call and fix settings.default.yaml."
            ) from exc
