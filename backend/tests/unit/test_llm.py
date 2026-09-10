"""The chat-model factory: role -> a `ChatOpenAI` pointed at OpenRouter (S0.3.2).

Nothing here opens a socket. `ChatOpenAI` performs no request when it is constructed, so
the whole factory is testable offline; the one function that *would* call OpenRouter --
the slug probe of ADR-0005 -- is exercised against a stubbed `invoke`.

Fixtures are module-local: `conftest.py` is shared ground and this story does not own it.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI

from crossbid.llm import (
    CHAT_ROLES,
    OPENROUTER_BASE_URL,
    PROBE_MAX_TOKENS,
    USAGE_ACCOUNTING_EXTRA_BODY,
    LlmError,
    chat_model,
    probe_chat_model,
    verify_configured_models,
)
from crossbid.settings import ModelRole, Settings, load_settings

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


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        (ModelRole.EXTRACT, "openai/gpt-5.6-terra"),
        (ModelRole.CHEAP, "openai/gpt-5.6-luna"),
        (ModelRole.JUDGE, "anthropic/claude-haiku-4.5"),
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
    assert ModelRole.EMBED not in CHAT_ROLES
    assert set(CHAT_ROLES) == {ModelRole.EXTRACT, ModelRole.CHEAP, ModelRole.JUDGE}


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
    assert probed == [
        ("openai/gpt-5.6-terra", PROBE_MAX_TOKENS),
        ("openai/gpt-5.6-luna", PROBE_MAX_TOKENS),
        ("anthropic/claude-haiku-4.5", PROBE_MAX_TOKENS),
    ]


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
