"""Chat-model factory: a role from `settings.default.yaml` becomes a configured model.

Every model call in Crossbid goes through OpenRouter, the single provider the project has
a key for (CLAUDE.md). Callers ask for a **role** -- `extract`, `cheap`, `judge` -- and
never for a slug, so switching models is a settings change and not a code change.

`extra_body={"usage": {"include": True}}` is what makes OpenRouter return the cost of each
response, which S5.2's per-node cost accounting reads. It is set here once so that no call
site can forget it.

BYOK -- a company running on its own OpenAI, Anthropic or OpenRouter key -- is S5.4-S5.6
and is **not** built. When it lands, it resolves a company's active provider into the
`api_key`/`base_url` pair below and this module grows a `company` argument; the plan's
`resolve(company, role)` is that signature. Today there is one route: the app's key.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any, Final

from langchain_openai import ChatOpenAI

from crossbid.settings import ModelRole, Settings

OPENROUTER_BASE_URL: Final = "https://openrouter.ai/api/v1"

USAGE_ACCOUNTING_EXTRA_BODY: Final[Mapping[str, Any]] = MappingProxyType(
    {"usage": {"include": True}}
)
"""Asks OpenRouter for token counts and cost on every response (verified 2026-09-10).
Read-only so that no caller can extend one model's body and affect the next."""

CHAT_ROLES: Final = (ModelRole.EXTRACT, ModelRole.CHEAP, ModelRole.JUDGE)
"""The roles that resolve to a chat model. `embed` is a role in the settings file too, but
it names an embedding model and goes through `ingestion/embeddings.py` (S2.2.1)."""

PROBE_MAX_TOKENS: Final = 1


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
        extra_body=USAGE_ACCOUNTING_EXTRA_BODY,
    )


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
