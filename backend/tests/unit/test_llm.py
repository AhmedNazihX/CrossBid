"""The chat-model factory: role -> a `ChatOpenAI` pointed at OpenRouter (S0.3.2).

Nothing here opens a socket. `ChatOpenAI` performs no request when it is constructed, so
the whole factory is testable offline; the one function that *would* call OpenRouter --
the slug probe of ADR-0005 -- is exercised against a stubbed `invoke`.

Fixtures are module-local: `conftest.py` is shared ground and this story does not own it.
"""

from __future__ import annotations

import logging

import httpx
import openai
import pytest
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI

from crossbid.llm import (
    LANGCHAIN_RETRIES,
    MODEL_ROLE_METADATA_KEY,
    OPENROUTER_BASE_URL,
    PROBE_MAX_TOKENS,
    USAGE_ACCOUNTING_EXTRA_BODY,
    USAGE_CALLBACK,
    LlmError,
    chat_model,
    probe_chat_model,
    resilient,
    verify_configured_models,
)
from crossbid.settings import CHAT_MODEL_ROLES, ModelRole, Settings, load_settings

FAKE_OPENROUTER_KEY = "sk-or-v1-LEAKED-OPENROUTER-KEY"


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """A real `Settings` off the real defaults file, with a fake key and no dotenv layer."""
    for name in (
        "OPENROUTER_API_KEY",
        "APP_ENCRYPTION_KEY",
        "DATABASE_URL",
        "ENV",
        "AUTH_MODE",
        "VERIFY_MODEL_SLUGS",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_OPENROUTER_KEY)
    monkeypatch.setenv("APP_ENCRYPTION_KEY", "fake-encryption-key")
    return load_settings(env_file=None)


# --------------------------------------------------------------------- the factory


def test_chat_model_is_built_against_openrouter(settings: Settings) -> None:
    # Act
    model = chat_model(ModelRole.EXTRACT, settings)

    # Assert
    assert model.model_name == "openai/gpt-5.6-terra"
    assert model.openai_api_base == OPENROUTER_BASE_URL
    assert model.temperature == settings.runtime.temperature
    assert model.max_tokens == settings.runtime.max_tokens
    assert model.openai_api_key is not None
    assert model.openai_api_key.get_secret_value() == FAKE_OPENROUTER_KEY


def test_usage_accounting_is_requested(settings: Settings) -> None:
    """Per-response cost comes back only when `usage.include` is asked for (CLAUDE.md)."""
    # Act
    model = chat_model(ModelRole.CHEAP, settings)

    # Assert
    assert model.extra_body is not None
    assert dict(model.extra_body) == {"usage": {"include": True}}
    assert USAGE_ACCOUNTING_EXTRA_BODY == {"usage": {"include": True}}


@pytest.mark.parametrize("role", list(CHAT_MODEL_ROLES))
def test_every_model_built_for_a_role_captures_what_it_spends(
    settings: Settings, role: ModelRole
) -> None:
    """S5.2 attaches the capture in the factory because nothing above it can see the cost:
    `with_structured_output` consumes the message the token counts arrive on."""
    # Act
    model = chat_model(role, settings)

    # Assert
    assert model.callbacks == [USAGE_CALLBACK]


@pytest.mark.parametrize("role", list(CHAT_MODEL_ROLES))
def test_every_model_built_for_a_role_says_which_role_on_its_traces(
    settings: Settings, role: ModelRole
) -> None:
    """The LangSmith half of S5.2. `bid_run_config` puts the bid on the run and LangGraph
    names the node; the role is the one fact only this factory knows (ADR-0050)."""
    # Act
    model = chat_model(role, settings)

    # Assert
    assert model.metadata is not None
    assert model.metadata[MODEL_ROLE_METADATA_KEY] == role.value


def test_the_startup_probe_is_attributed_to_nobody_and_traced_as_nothing(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """A one-token probe runs before any request: there is no tenant to charge and no bid
    to attribute it to, so warning about it on every boot would drown the signal that a
    node is missing its instrumentation."""
    # Arrange
    probed: list[ChatOpenAI] = []
    monkeypatch.setenv("VERIFY_MODEL_SLUGS", "true")
    verified = load_settings(env_file=None)

    # Act
    verify_configured_models(verified, probe=probed.append)

    # Assert
    assert probed, "the walk must have probed something"
    assert all(model.callbacks is None for model in probed)
    assert all(MODEL_ROLE_METADATA_KEY not in (model.metadata or {}) for model in probed)


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        (ModelRole.EXTRACT, "openai/gpt-5.6-terra"),
        (ModelRole.CHEAP, "openai/gpt-5.6-luna"),
        (ModelRole.JUDGE, "google/gemini-2.5-flash-lite"),
    ],
)
def test_every_chat_role_resolves_to_its_configured_slug(
    settings: Settings, role: ModelRole, expected: str
) -> None:
    # Act / Assert -- no slug is hard-coded in llm.py; they come from the YAML
    assert chat_model(role, settings).model_name == expected


def test_the_embed_role_is_refused(settings: Settings) -> None:
    """`embed` is a role in the settings file, but not a chat model."""
    # Act / Assert
    with pytest.raises(LlmError, match="embed"):
        chat_model(ModelRole.EMBED, settings)


def test_temperature_and_max_tokens_can_be_overridden_per_call(settings: Settings) -> None:
    # Act
    model = chat_model(ModelRole.CHEAP, settings, temperature=0.7, max_tokens=16)

    # Assert
    assert model.temperature == 0.7
    assert model.max_tokens == 16


def test_the_key_does_not_leak_into_the_model_repr(settings: Settings) -> None:
    # Act
    rendered = repr(chat_model(ModelRole.EXTRACT, settings))

    # Assert
    assert FAKE_OPENROUTER_KEY not in rendered


def test_chat_roles_excludes_the_embedding_role() -> None:
    # Assert
    assert ModelRole.EMBED not in CHAT_MODEL_ROLES
    assert set(CHAT_MODEL_ROLES) == {
        ModelRole.EXTRACT,
        ModelRole.CHEAP,
        ModelRole.JUDGE,
        ModelRole.FALLBACK,
    }


# ------------------------------------------- ADR-0005: a configured slug may still 404


def test_verification_is_off_by_default(settings: Settings) -> None:
    """CI has no real key, so startup must not probe unless asked to."""
    # Arrange
    probed: list[str] = []

    # Act
    verify_configured_models(settings, probe=lambda model: probed.append(model.model_name))

    # Assert
    assert settings.env.verify_model_slugs is False
    assert probed == []


def test_verification_probes_every_chat_slug_when_switched_on(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    # Arrange
    monkeypatch.setenv("VERIFY_MODEL_SLUGS", "true")
    opted_in = load_settings(env_file=None)
    probed: list[tuple[str, int | None]] = []

    # Act
    verify_configured_models(
        opted_in, probe=lambda model: probed.append((model.model_name, model.max_tokens))
    )

    # Assert -- one token per slug, and the embedding slug is not probed with a chat call
    assert probed == [(slug, PROBE_MAX_TOKENS) for slug in opted_in.runtime.available_models]
    # Every configured chat slug is on that list, the fallback included: a fallback nobody
    # checked is worth nothing, because the one moment it is used is the moment the primary
    # has already failed. So is `google/gemini-2.5-flash`, which no role runs on today and
    # which S5.1 nonetheless lets an operator switch a role to.
    slugs = [slug for slug, _ in probed]
    assert slugs == [
        "openai/gpt-5.6-terra",
        "openai/gpt-5.6-luna",
        "anthropic/claude-haiku-4.5",
        "google/gemini-2.5-flash",
        "google/gemini-2.5-flash-lite",
    ]
    assert opted_in.runtime.models.embed not in slugs


def test_verification_fails_fast_and_names_the_slug_that_did_not_answer(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """ADR-0005: eleven catalogued models 404 under this account's data policy."""
    # Arrange
    monkeypatch.setenv("VERIFY_MODEL_SLUGS", "true")
    opted_in = load_settings(env_file=None)

    def refuse(_model: ChatOpenAI) -> None:
        raise RuntimeError("Error code: 404 - 0 endpoints available")

    # Act / Assert
    with pytest.raises(LlmError) as caught:
        verify_configured_models(opted_in, probe=refuse)

    # Assert
    message = str(caught.value)
    assert "openai/gpt-5.6-terra" in message
    assert "extract" in message
    assert "ADR-0005" in message


def test_a_slug_only_the_picker_offers_is_probed_and_named_as_such(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """S5.1's own hazard: a slug no role runs on today is one an operator may switch to
    tomorrow, and a 404 found out then is found out at the worst possible moment."""
    # Arrange
    monkeypatch.setenv("VERIFY_MODEL_SLUGS", "true")
    opted_in = load_settings(env_file=None)
    offered_only = "google/gemini-2.5-flash"
    configured = set(opted_in.runtime.models.model_dump().values())
    assert offered_only in opted_in.runtime.available_models
    assert offered_only not in configured

    def refuse_that_one(model: ChatOpenAI) -> None:
        if model.model_name == offered_only:
            raise RuntimeError("Error code: 404 - 0 endpoints available")

    # Act / Assert
    with pytest.raises(LlmError) as caught:
        verify_configured_models(opted_in, probe=refuse_that_one)

    # Assert -- the message separates "in use" from "offered", because the cost differs
    message = str(caught.value)
    assert offered_only in message
    assert "model picker" in message
    assert "configured for role" not in message


def test_the_probe_sends_a_single_token(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    # Arrange -- `invoke` is the only thing that would reach the network
    calls: list[object] = []

    def fake_invoke(
        self: ChatOpenAI, input_: object, *_args: object, **_kwargs: object
    ) -> AIMessage:
        calls.append(input_)
        return AIMessage(content="ok")

    monkeypatch.setattr(ChatOpenAI, "invoke", fake_invoke)

    # Act
    probe_chat_model(chat_model(ModelRole.CHEAP, settings, max_tokens=PROBE_MAX_TOKENS))

    # Assert
    assert len(calls) == 1


# ------------------------------------------------------- S3.4.4: one retry, then the spare


class ScriptedRunnable:
    """A bound runnable, scripted. An `Exception` in the script is raised, not returned."""

    def __init__(self, *script: object) -> None:
        self.script = list(script)
        self.calls = 0

    async def ainvoke(self, messages: object, /) -> object:
        self.calls += 1
        answer = self.script.pop(0) if self.script else "exhausted"
        if isinstance(answer, Exception):
            raise answer
        return answer


TIMEOUT = openai.APITimeoutError(request=httpx.Request("POST", "https://openrouter.ai"))


@pytest.mark.anyio
async def test_a_call_that_works_first_time_never_touches_the_fallback() -> None:
    # Arrange
    primary, fallback = ScriptedRunnable("answered"), ScriptedRunnable()

    # Act
    answer = await resilient(primary, fallback).ainvoke([])

    # Assert
    assert answer == "answered"
    assert (primary.calls, fallback.calls) == (1, 0)


@pytest.mark.anyio
async def test_a_timeout_is_retried_once_on_the_same_model() -> None:
    # Arrange
    primary, fallback = ScriptedRunnable(TIMEOUT, "answered"), ScriptedRunnable()

    # Act
    answer = await resilient(primary, fallback).ainvoke([])

    # Assert
    assert answer == "answered"
    assert (primary.calls, fallback.calls) == (2, 0)


@pytest.mark.anyio
async def test_a_second_timeout_falls_back_to_the_smaller_model() -> None:
    """The story's criterion, end to end: one retry, then the smaller model."""
    # Arrange
    primary = ScriptedRunnable(TIMEOUT, TIMEOUT)
    fallback = ScriptedRunnable("answered by the spare")

    # Act
    answer = await resilient(primary, fallback).ainvoke([])

    # Assert
    assert answer == "answered by the spare"
    assert (primary.calls, fallback.calls) == (2, 1)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "failure",
    [
        TIMEOUT,
        openai.APIConnectionError(request=httpx.Request("POST", "https://openrouter.ai")),
        httpx.ConnectTimeout("too slow"),
        httpx.ReadError("the connection went away"),
        TimeoutError(),
    ],
)
async def test_every_route_failure_moves_the_call_along(failure: Exception) -> None:
    # Arrange
    primary = ScriptedRunnable(failure, failure)
    fallback = ScriptedRunnable("answered by the spare")

    # Act / Assert
    assert await resilient(primary, fallback).ainvoke([]) == "answered by the spare"


@pytest.mark.anyio
async def test_a_reproducible_failure_is_raised_at_once_and_never_retried() -> None:
    """A refused slug or a malformed request answers the same way three times; retrying it
    spends the run budget to learn nothing."""
    # Arrange
    primary = ScriptedRunnable(ValueError("that model is not available on this account"))
    fallback = ScriptedRunnable("answered by the spare")

    # Act / Assert
    with pytest.raises(ValueError, match="not available"):
        await resilient(primary, fallback).ainvoke([])
    assert (primary.calls, fallback.calls) == (1, 0)


@pytest.mark.anyio
async def test_the_fallbacks_own_failure_is_what_surfaces() -> None:
    """It is the most recent fact about the call; the primary's timeout is in the log."""
    # Arrange
    primary = ScriptedRunnable(TIMEOUT, TIMEOUT)
    fallback = ScriptedRunnable(RuntimeError("the spare is down too"))

    # Act / Assert
    with pytest.raises(RuntimeError, match="the spare is down too"):
        await resilient(primary, fallback).ainvoke([])


@pytest.mark.anyio
async def test_each_attempt_is_logged_by_type_and_never_by_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """ADR-0008: a provider's message can quote the request, which carries tender text."""
    # Arrange
    primary = ScriptedRunnable(TIMEOUT, TIMEOUT)

    # Act
    with caplog.at_level(logging.WARNING, logger="crossbid.llm"):
        await resilient(primary, ScriptedRunnable("ok")).ainvoke([])

    # Assert
    assert "APITimeoutError" in caplog.text
    assert "retrying once" in caplog.text
    assert "falling back to the smaller model" in caplog.text


def test_the_model_carries_the_configured_timeout_and_does_not_retry_itself(
    settings: Settings,
) -> None:
    """`ChatOpenAI` retries twice by default. Left on, "one retry" would be one of ours on
    top of two of langchain's, and `llm_timeout_seconds` would bound a third of the wait."""
    # Act
    model = chat_model(ModelRole.EXTRACT, settings)

    # Assert
    assert model.request_timeout == settings.runtime.agent.llm_timeout_seconds
    assert model.max_retries == LANGCHAIN_RETRIES == 0


def test_the_fallback_role_resolves_to_a_different_vendor(settings: Settings) -> None:
    """The failure a fallback exists to survive is the primary route being slow or down; a
    second OpenAI slug shares that route."""
    # Arrange
    slugs = settings.runtime.models

    # Act / Assert
    assert slugs.for_role(ModelRole.FALLBACK).split("/")[0] not in {
        slugs.for_role(ModelRole.EXTRACT).split("/")[0],
        slugs.for_role(ModelRole.CHEAP).split("/")[0],
    }


def test_the_fallback_slug_is_one_of_the_verified_models(settings: Settings) -> None:
    """ADR-0005: presence in OpenRouter's catalogue does not mean usable on this account."""
    assert settings.runtime.models.fallback in settings.runtime.available_models
