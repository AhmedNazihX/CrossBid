"""The one settings object: environment, YAML defaults, `app_settings` row (S0.3.2).

Also the two startup guards that need no database and so land with this story: the
transaction-pooler refusal from S0.2.2 and the dev-auth-in-production refusal from S0.3.1.

Every test is offline and every environment variable is set through `monkeypatch`. The
loader is always called with `env_file=None` so that no test can read the developer's real
`.env` -- a test that picked up a real `OPENROUTER_API_KEY` would pass on one machine and
fail on another. Fixtures are module-local on purpose: `conftest.py` is shared ground.
"""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Any

import pytest
import yaml
from langsmith import utils as langsmith_utils
from pydantic import ValidationError

from crossbid import settings as settings_module
from crossbid.settings import (
    MAX_SIGNED_URL_TTL_SECONDS,
    TRACING_FLAG_ENV_VARS,
    AppSettingsRow,
    AuthMode,
    Environment,
    EnvSettings,
    ModelRole,
    Settings,
    SettingsError,
    apply_app_settings_row,
    bid_run_config,
    check_database_dsn,
    configure_tracing,
    fetch_app_settings_row,
    get_settings,
    load_settings,
)

# Distinctive so that a leak into a repr, a dump or an exception is unmistakable.
FAKE_OPENROUTER_KEY = "sk-or-v1-LEAKED-OPENROUTER-KEY"
FAKE_ENCRYPTION_KEY = "LEAKED-FERNET-ENCRYPTION-KEY="
FAKE_DSN_PASSWORD = "LEAKED-DATABASE-PASSWORD"

FAKE_SERVICE_KEY = "sb_secret_LEAKED-SERVICE-ROLE-KEY"

MANAGED_ENV_VARS = (
    "OPENROUTER_API_KEY",
    "APP_ENCRYPTION_KEY",
    "DATABASE_URL",
    "AUTH_MODE",
    "ENV",
    "LANGSMITH_API_KEY",
    "LANGSMITH_PROJECT",
    "VERIFY_MODEL_SLUGS",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_STORAGE_BUCKET",
    "SIGNED_URL_TTL_SECONDS",
    "WEB_ORIGIN",
    "DEVELOPER_EMAILS",
)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """No variable this module cares about survives from the developer's shell."""
    for name in MANAGED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def valid_env(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """The smallest environment the API will start in: the two required secrets."""
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_OPENROUTER_KEY)
    monkeypatch.setenv("APP_ENCRYPTION_KEY", FAKE_ENCRYPTION_KEY)


def load(**kwargs: Any) -> Settings:
    """`load_settings` with the dotenv layer off, which is what every test wants."""
    kwargs.setdefault("env_file", None)
    return load_settings(**kwargs)


# ------------------------------------------------------------------- the YAML layer


def test_yaml_defaults_load(valid_env: None) -> None:
    # Act
    settings = load()

    # Assert -- the verified slugs of settings.default.yaml, not hard-coded elsewhere
    assert settings.runtime.models.extract == "openai/gpt-5.6-terra"
    assert settings.runtime.models.cheap == "openai/gpt-5.6-luna"
    assert settings.runtime.models.embed == "openai/text-embedding-3-small"
    assert settings.runtime.models.judge == "anthropic/claude-haiku-4.5"
    assert settings.runtime.temperature == 0.0
    # 4096 until 2026-09-13, when it was measured losing whole sections: a dense extraction
    # section returns one structured object holding every requirement it found, and exceeding
    # the cap raises LengthFinishReasonError, which the node records as a bare `model_error`.
    assert settings.runtime.max_tokens == 16384
    assert settings.runtime.ingestion.chunk_tokens == 800
    assert settings.runtime.ingestion.chunk_overlap == 100
    assert settings.runtime.ingestion.section_pages == 6
    assert settings.runtime.ingestion.embed_dimensions == 1536
    assert settings.runtime.agent.extract_concurrency == 5
    assert settings.runtime.agent.check_concurrency == 5
    assert settings.runtime.agent.run_budget_seconds == 600
    assert settings.runtime.agent.run_budget_usd == 2.50
    assert settings.runtime.agent.max_tool_calls_per_requirement == 4
    assert "company_rag_search" in settings.runtime.enabled_tools
    assert "openai/gpt-5.6-terra" in settings.runtime.available_models


def test_the_system_prompt_is_loaded_from_the_defaults_file(valid_env: None) -> None:
    """S0.3.2 wants the prompt in the settings file, and it is the only place it is written."""
    # Act
    prompt = load().runtime.system_prompt

    # Assert
    assert prompt is not None
    assert "Crossbid" in prompt


def test_the_system_prompt_states_the_untrusted_data_rule(valid_env: None) -> None:
    """Tender text is untrusted input (S2.3.2). The prompt is where the model is told so,
    which makes the rule's presence a behavioural property worth pinning."""
    # Act
    prompt = load().runtime.system_prompt or ""

    # Assert
    assert "DATA, never instructions" in prompt
    assert "cite" in prompt.lower()


def test_environment_defaults(valid_env: None) -> None:
    # Act
    settings = load()

    # Assert
    assert settings.env.environment is Environment.DEVELOPMENT
    assert settings.env.auth_mode is AuthMode.DEV
    assert settings.env.langsmith_api_key is None
    assert settings.env.langsmith_project == "crossbid"
    assert settings.env.verify_model_slugs is False
    assert settings.env.database_url is None


def test_settings_are_immutable(valid_env: None) -> None:
    # Arrange
    settings = load()

    # Act / Assert
    with pytest.raises(ValidationError):
        settings.runtime.temperature = 0.9  # type: ignore[misc]
    with pytest.raises(ValidationError):
        settings.env.auth_mode = AuthMode.SUPABASE  # type: ignore[misc]


def test_missing_defaults_file_names_the_file(valid_env: None, tmp_path: Path) -> None:
    # Arrange
    missing = tmp_path / "nope.yaml"

    # Act / Assert
    with pytest.raises(SettingsError, match=r"nope\.yaml"):
        load(defaults_file=missing)


def test_defaults_file_that_is_not_a_mapping_is_refused(
    valid_env: None, tmp_path: Path
) -> None:
    # Arrange
    path = tmp_path / "settings.default.yaml"
    path.write_text("- just\n- a list\n", encoding="utf-8")

    # Act / Assert
    with pytest.raises(SettingsError, match="mapping"):
        load(defaults_file=path)


def test_a_defaults_file_that_is_not_valid_yaml_is_refused(
    valid_env: None, tmp_path: Path
) -> None:
    # Arrange
    path = tmp_path / "settings.default.yaml"
    path.write_text("models: [unclosed\n", encoding="utf-8")

    # Act / Assert
    with pytest.raises(SettingsError, match="not valid YAML"):
        load(defaults_file=path)


def test_unknown_key_in_the_defaults_file_is_refused(valid_env: None, tmp_path: Path) -> None:
    """A typo must fail fast rather than silently do nothing."""
    # Arrange
    path = tmp_path / "settings.default.yaml"
    path.write_text(
        (settings_module.DEFAULTS_FILE).read_text(encoding="utf-8") + "\ntemprature: 0.7\n",
        encoding="utf-8",
    )

    # Act / Assert
    with pytest.raises(SettingsError, match="temprature"):
        load(defaults_file=path)


# --------------------------------------------------------- required variables, fail fast


def test_missing_openrouter_key_names_the_variable(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.setenv("APP_ENCRYPTION_KEY", FAKE_ENCRYPTION_KEY)

    # Act / Assert
    with pytest.raises(SettingsError, match="OPENROUTER_API_KEY") as caught:
        load()
    assert "not set" in str(caught.value)


def test_missing_encryption_key_names_the_variable(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_OPENROUTER_KEY)

    # Act / Assert
    with pytest.raises(SettingsError, match="APP_ENCRYPTION_KEY"):
        load()


def test_both_missing_variables_are_named(clean_env: None) -> None:
    # Act / Assert
    with pytest.raises(SettingsError) as caught:
        load()

    # Assert
    message = str(caught.value)
    assert "OPENROUTER_API_KEY" in message
    assert "APP_ENCRYPTION_KEY" in message
    assert "infra/.env.example" in message


@pytest.mark.parametrize(
    ("blank", "expected"),
    [
        pytest.param("", "OPENROUTER_API_KEY is not set", id="empty"),
        pytest.param("   ", "OPENROUTER_API_KEY is set but blank", id="whitespace"),
    ],
)
def test_blank_required_variable_counts_as_missing(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, blank: str, expected: str
) -> None:
    """`OPENROUTER_API_KEY=` in a .env file must not pass an empty key to OpenRouter."""
    # Arrange
    monkeypatch.setenv("OPENROUTER_API_KEY", blank)
    monkeypatch.setenv("APP_ENCRYPTION_KEY", FAKE_ENCRYPTION_KEY)

    # Act / Assert
    with pytest.raises(SettingsError, match=expected):
        load()


def test_invalid_environment_value_names_env(
    valid_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.setenv("ENV", "prod")

    # Act / Assert
    with pytest.raises(SettingsError, match="ENV") as caught:
        load()
    assert "production" in str(caught.value)


def test_invalid_auth_mode_names_auth_mode(
    valid_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.setenv("AUTH_MODE", "none")

    # Act / Assert
    with pytest.raises(SettingsError, match="AUTH_MODE"):
        load()


# ------------------------------------------------------------------ secrets stay secret


def test_secrets_never_appear_in_a_repr_a_str_or_a_dump(
    valid_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """security.md: a key must not reach a log line, an exception, or a settings dump."""
    # Arrange
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2-LEAKED-LANGSMITH-KEY")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", FAKE_SERVICE_KEY)
    monkeypatch.setenv(
        "DATABASE_URL", f"postgresql://postgres:{FAKE_DSN_PASSWORD}@localhost:5432/crossbid"
    )
    settings = load()
    renderings = [
        repr(settings),
        str(settings),
        repr(settings.env),
        str(settings.env),
        settings.model_dump_json(),
        str(settings.model_dump()),
    ]

    # Assert
    for rendering in renderings:
        assert FAKE_OPENROUTER_KEY not in rendering
        assert FAKE_ENCRYPTION_KEY not in rendering
        assert FAKE_DSN_PASSWORD not in rendering
        assert FAKE_SERVICE_KEY not in rendering
        assert "LEAKED-LANGSMITH-KEY" not in rendering

    # The values are still reachable deliberately, which is the only way to use them.
    assert settings.env.openrouter_api_key.get_secret_value() == FAKE_OPENROUTER_KEY


def test_a_bad_secret_does_not_leak_through_the_validation_error(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange -- a key present but blank: the error must name it, not print it
    monkeypatch.setenv("OPENROUTER_API_KEY", " ")
    monkeypatch.setenv("APP_ENCRYPTION_KEY", FAKE_ENCRYPTION_KEY)

    # Act / Assert
    with pytest.raises(SettingsError) as caught:
        load()
    assert FAKE_ENCRYPTION_KEY not in str(caught.value)


# --------------------------------------------------------------------- the dotenv layer


def test_env_file_is_read_when_it_exists(clean_env: None, tmp_path: Path) -> None:
    """`make dev-api` runs uvicorn on the host, where only the root .env holds the keys."""
    # Arrange
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"OPENROUTER_API_KEY={FAKE_OPENROUTER_KEY}\nAPP_ENCRYPTION_KEY={FAKE_ENCRYPTION_KEY}\n",
        encoding="utf-8",
    )

    # Act
    settings = load_settings(env_file=env_file)

    # Assert
    assert settings.env.openrouter_api_key.get_secret_value() == FAKE_OPENROUTER_KEY


def test_a_missing_env_file_is_not_an_error(valid_env: None, tmp_path: Path) -> None:
    # Act / Assert -- Docker ships no .env; the environment carries the values
    assert load_settings(env_file=tmp_path / ".env").env.auth_mode is AuthMode.DEV


def test_the_environment_wins_over_the_env_file(
    clean_env: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"OPENROUTER_API_KEY=from-the-file\nAPP_ENCRYPTION_KEY={FAKE_ENCRYPTION_KEY}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_OPENROUTER_KEY)

    # Act
    settings = load_settings(env_file=env_file)

    # Assert
    assert settings.env.openrouter_api_key.get_secret_value() == FAKE_OPENROUTER_KEY


# --------------------------------------------- S2.2.2 Storage wiring and the URL cap


def test_the_storage_wiring_defaults(valid_env: None) -> None:
    """Nothing about Storage is required to start: it is not mocked locally, so the
    offline stories and `make test` run with none of it set (project-plan, Environments)."""
    # Act
    env = load().env

    # Assert
    assert env.supabase_url is None
    assert env.supabase_service_role_key is None
    assert env.supabase_storage_bucket == "company-documents"
    assert env.signed_url_ttl_seconds == MAX_SIGNED_URL_TTL_SECONDS


def test_the_service_role_key_is_read_from_the_documented_variable(
    valid_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`SUPABASE_SERVICE_KEY` is the name `infra/.env.example` and Compose already pass."""
    # Arrange
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", FAKE_SERVICE_KEY)

    # Act
    key = load().env.supabase_service_role_key

    # Assert
    assert key is not None
    assert key.get_secret_value() == FAKE_SERVICE_KEY


def test_the_service_role_key_is_also_read_from_the_field_name(
    valid_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`populate_by_name` accepts the fuller name too, so neither spelling silently
    leaves the backend without a key."""
    # Arrange
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", FAKE_SERVICE_KEY)

    # Act
    key = load().env.supabase_service_role_key

    # Assert
    assert key is not None
    assert key.get_secret_value() == FAKE_SERVICE_KEY


@pytest.mark.parametrize("ttl", ["1", "60", "600"])
def test_a_signed_url_ttl_within_ten_minutes_is_accepted(
    valid_env: None, monkeypatch: pytest.MonkeyPatch, ttl: str
) -> None:
    # Arrange
    monkeypatch.setenv("SIGNED_URL_TTL_SECONDS", ttl)

    # Act / Assert
    assert load().env.signed_url_ttl_seconds == int(ttl)


@pytest.mark.parametrize(
    "ttl",
    [
        pytest.param("0", id="zero"),
        pytest.param("-1", id="negative"),
        pytest.param("601", id="one-second-over-ten-minutes"),
        pytest.param("86400", id="a-day"),
    ],
)
def test_a_signed_url_ttl_outside_the_cap_is_refused_at_startup(
    valid_env: None, monkeypatch: pytest.MonkeyPatch, ttl: str
) -> None:
    """S2.2.2 caps a document URL at ten minutes, so a configuration that breaks the
    story fails while starting rather than handing out a long-lived URL at request time."""
    # Arrange
    monkeypatch.setenv("SIGNED_URL_TTL_SECONDS", ttl)

    # Act / Assert
    with pytest.raises(SettingsError, match="SIGNED_URL_TTL_SECONDS") as caught:
        load()
    assert "ten minutes" in str(caught.value)


def test_a_signed_url_ttl_that_is_not_a_number_names_the_variable(
    valid_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.setenv("SIGNED_URL_TTL_SECONDS", "ten minutes")

    # Act / Assert
    with pytest.raises(SettingsError, match="SIGNED_URL_TTL_SECONDS"):
        load()


# ------------------------------------------------- the two layers stay disjoint (S0.3.2)


def test_no_environment_variable_is_also_a_key_of_the_defaults_file() -> None:
    """The invariant the module docstring promises: secrets and deployment wiring live
    only in the environment, behaviour only in the YAML, so "which wins" never has to be
    guessed. A field added to both layers at once would make that a lie."""
    # Arrange
    defaults = yaml.safe_load(settings_module.DEFAULTS_FILE.read_text(encoding="utf-8"))
    env_names: set[str] = set()
    for name, field in EnvSettings.model_fields.items():
        env_names.add(name)
        if isinstance(field.validation_alias, str):
            env_names.add(field.validation_alias.lower())

    # Assert -- and the guard is not vacuous: the newest fields are in the set
    assert {"supabase_storage_bucket", "signed_url_ttl_seconds", "env"} <= env_names
    assert env_names.isdisjoint(set(defaults))


# ------------------------------------------------------- S0.3.1 guard: dev auth mode


@pytest.mark.parametrize("environment", ["development", "test"])
def test_dev_auth_mode_is_allowed_outside_production(
    valid_env: None, monkeypatch: pytest.MonkeyPatch, environment: str
) -> None:
    # Arrange
    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.setenv("ENV", environment)

    # Act / Assert
    assert load().env.auth_mode is AuthMode.DEV


def test_dev_auth_mode_is_refused_in_production(
    valid_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.setenv("ENV", "production")

    # Act / Assert
    with pytest.raises(SettingsError) as caught:
        load()

    # Assert
    message = str(caught.value)
    assert "AUTH_MODE" in message
    assert "ENV=production" in message


def test_supabase_auth_mode_is_allowed_in_production(
    valid_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.setenv("AUTH_MODE", "supabase")
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")

    # Act / Assert
    assert load().env.environment is Environment.PRODUCTION


def test_supabase_auth_mode_without_a_project_url_is_refused(
    valid_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S0.3.1: the JWKS URL is derived from SUPABASE_URL, so there is nothing to verify
    tokens against without it, and the first request is a worse place to find that out."""
    # Arrange
    monkeypatch.setenv("AUTH_MODE", "supabase")
    monkeypatch.delenv("SUPABASE_URL", raising=False)

    # Act
    with pytest.raises(SettingsError) as raised:
        load()

    # Assert
    assert "SUPABASE_URL" in str(raised.value)


@pytest.mark.parametrize(
    ("listed", "email", "expected"),
    [
        ("a@example.de,b@example.de", "b@example.de", True),
        ("  A@Example.DE , b@example.de ", "a@example.de", True),
        ("a@example.de", "b@example.de", False),
        ("", "a@example.de", False),
        ("a@example.de", None, False),
        ("a@example.de", "   ", False),
    ],
)
def test_the_developer_list_decides_who_reaches_a_dev_route(
    valid_env: None,
    monkeypatch: pytest.MonkeyPatch,
    listed: str,
    email: str | None,
    expected: bool,
) -> None:
    """S0.3.1's third criterion. Every failure direction here is the closed one."""
    monkeypatch.setenv("DEVELOPER_EMAILS", listed)

    assert load().env.is_developer_email(email) is expected


def test_an_unset_developer_list_admits_nobody(
    valid_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DEVELOPER_EMAILS", raising=False)

    assert load().env.is_developer_email("anyone@example.de") is False


# ------------------------------------------------- S0.2.2 guard: the pooler DSN rule

ACCEPTED_DSNS = [
    pytest.param("postgresql://crossbid:crossbid@db:5432/crossbid", id="compose-service-host"),
    pytest.param(
        "postgresql://crossbid:crossbid@localhost:5432/crossbid_test", id="ci-localhost"
    ),
    pytest.param(
        "postgresql://postgres:pw@db.abcdefghijklmnopqrst.supabase.co:5432/postgres",
        id="supabase-direct-connection",
    ),
    pytest.param(
        "postgresql://postgres.abcdefghijklmnopqrst:pw"
        "@aws-0-eu-central-1.pooler.supabase.com:5432/postgres",
        id="supabase-session-pooler",
    ),
    pytest.param(
        "postgresql://postgres.abcdefghijklmnopqrst:pw"
        "@aws-0-eu-central-1.pooler.supabase.com:5432/postgres?sslmode=require",
        id="session-pooler-with-sslmode",
    ),
    pytest.param("postgres://crossbid@db/crossbid", id="no-port-postgres-scheme"),
    pytest.param(
        "postgresql://crossbid:crossbid@localhost:6543/crossbid",
        id="local-port-6543-is-not-a-pooler",
    ),
]

REFUSED_DSNS = [
    pytest.param(
        "postgresql://postgres.abcdefghijklmnopqrst:pw"
        "@aws-0-eu-central-1.pooler.supabase.com:6543/postgres",
        id="eu-transaction-pooler",
    ),
    pytest.param(
        "postgresql://postgres.abcdefghijklmnopqrst:pw"
        "@aws-1-us-east-1.POOLER.supabase.com:6543/postgres?sslmode=require",
        id="transaction-pooler-mixed-case",
    ),
]


@pytest.mark.parametrize("dsn", ACCEPTED_DSNS)
def test_accepted_database_dsns(dsn: str) -> None:
    # Act / Assert -- a false positive here would block all local development
    check_database_dsn(dsn)


@pytest.mark.parametrize("dsn", REFUSED_DSNS)
def test_transaction_pooler_dsn_is_refused(dsn: str) -> None:
    # Act / Assert
    with pytest.raises(SettingsError) as caught:
        check_database_dsn(dsn)

    # Assert -- the message must name the fix and never echo the credentials
    message = str(caught.value)
    assert "session pooler" in message.lower()
    assert "5432" in message
    assert "pw@" not in message


def test_pgbouncer_flag_is_refused() -> None:
    """The other documented marker of a transaction-pooling connection."""
    # Act / Assert
    with pytest.raises(SettingsError, match="pgbouncer"):
        check_database_dsn("postgresql://u:p@some-host:5432/db?pgbouncer=true")


@pytest.mark.parametrize(
    "dsn",
    [
        pytest.param("mysql://u:p@localhost:3306/db", id="wrong-scheme"),
        pytest.param("host=db port=5432 dbname=crossbid", id="libpq-key-value-form"),
        pytest.param("", id="empty"),
    ],
)
def test_dsn_that_is_not_a_postgres_url_is_refused(dsn: str) -> None:
    # Act / Assert
    with pytest.raises(SettingsError, match="DATABASE_URL"):
        check_database_dsn(dsn)


def test_dsn_with_an_unparsable_port_is_refused() -> None:
    # Act / Assert
    with pytest.raises(SettingsError, match="DATABASE_URL"):
        check_database_dsn("postgresql://u:p@localhost:not-a-port/db")


def test_the_dsn_guard_runs_at_startup(
    valid_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.setenv(
        "DATABASE_URL",
        f"postgresql://postgres.ref:{FAKE_DSN_PASSWORD}"
        "@aws-0-eu-central-1.pooler.supabase.com:6543/postgres",
    )

    # Act / Assert
    with pytest.raises(SettingsError) as caught:
        load()

    # Assert
    assert "session pooler" in str(caught.value).lower()
    assert FAKE_DSN_PASSWORD not in str(caught.value)


def test_a_good_dsn_passes_startup(valid_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    dsn = "postgresql://crossbid:crossbid@db:5432/crossbid"
    monkeypatch.setenv("DATABASE_URL", dsn)

    # Act
    settings = load()

    # Assert
    assert settings.env.database_url is not None
    assert settings.env.database_url.get_secret_value() == dsn


# --------------------------------------------------- the app_settings override seam


def test_app_settings_row_overrides_the_yaml_defaults(valid_env: None) -> None:
    # Arrange
    settings = load()
    row = AppSettingsRow(
        models={ModelRole.JUDGE: "google/gemini-2.5-flash"},
        temperature=0.4,
        max_tokens=2048,
        system_prompt="You are Crossbid.",
        enabled_tools=("company_rag_search",),
    )

    # Act
    overridden = apply_app_settings_row(settings, row)

    # Assert
    assert overridden.runtime.models.judge == "google/gemini-2.5-flash"
    assert overridden.runtime.models.extract == "openai/gpt-5.6-terra"  # untouched column
    assert overridden.runtime.temperature == 0.4
    assert overridden.runtime.max_tokens == 2048
    assert overridden.runtime.system_prompt == "You are Crossbid."
    assert overridden.runtime.enabled_tools == ("company_rag_search",)
    assert overridden.env is settings.env


def test_applying_a_row_returns_a_new_object_and_mutates_nothing(valid_env: None) -> None:
    # Arrange
    settings = load()

    # Act
    overridden = apply_app_settings_row(settings, AppSettingsRow(temperature=1.0))

    # Assert
    assert overridden is not settings
    assert settings.runtime.temperature == 0.0
    assert overridden.runtime.temperature == 1.0


def test_an_absent_row_leaves_the_defaults_alone(valid_env: None) -> None:
    # Arrange
    settings = load()

    # Act / Assert -- no row yet (the table lands with S0.2.3)
    assert apply_app_settings_row(settings, None) is settings


def test_an_all_null_row_leaves_the_defaults_alone(valid_env: None) -> None:
    # Arrange
    settings = load()

    # Act
    overridden = apply_app_settings_row(settings, AppSettingsRow())

    # Assert
    assert overridden.runtime == settings.runtime


def test_a_row_holding_a_bad_value_is_refused(valid_env: None) -> None:
    """The row is external data: validated, not trusted."""
    # Arrange
    settings = load()
    row = AppSettingsRow(temperature=7.0)

    # Act / Assert
    with pytest.raises(SettingsError, match="app_settings"):
        apply_app_settings_row(settings, row)


def test_a_row_naming_an_unknown_role_is_refused() -> None:
    # Act / Assert
    with pytest.raises(ValidationError):
        AppSettingsRow.model_validate({"models": {"summarise": "openai/gpt-5.6-luna"}})


def test_fetching_the_row_is_the_seam_that_waits_for_the_database() -> None:
    # Act / Assert -- S0.2.1 is blocked on a Supabase project; nothing is faked here
    with pytest.raises(NotImplementedError, match=r"S0\.2\.3"):
        fetch_app_settings_row()


# ------------------------------------------------------------------- role resolution


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        (ModelRole.EXTRACT, "openai/gpt-5.6-terra"),
        (ModelRole.CHEAP, "openai/gpt-5.6-luna"),
        (ModelRole.EMBED, "openai/text-embedding-3-small"),
        (ModelRole.JUDGE, "anthropic/claude-haiku-4.5"),
    ],
)
def test_every_role_resolves_to_its_configured_slug(
    valid_env: None, role: ModelRole, expected: str
) -> None:
    # Act / Assert
    assert load().runtime.models.for_role(role) == expected


# --------------------------------------------------------------- the cached accessor


def test_get_settings_loads_once(monkeypatch: pytest.MonkeyPatch, valid_env: None) -> None:
    """FastAPI resolves the dependency per request; the YAML is read once."""
    # Arrange
    calls: list[int] = []

    def counting_load(**_kwargs: Any) -> Settings:
        calls.append(1)
        return load()

    monkeypatch.setattr(settings_module, "load_settings", counting_load)
    get_settings.cache_clear()

    # Act
    first = get_settings()
    second = get_settings()
    get_settings.cache_clear()

    # Assert
    assert first is second
    assert len(calls) == 1


# ------------------------------------------------------- S0.3.3 tracing (LangSmith)


def test_tracing_is_enabled_when_a_key_is_configured(
    valid_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2-test-key")
    monkeypatch.setenv("LANGSMITH_PROJECT", "crossbid-test")
    settings = load()
    environ: dict[str, str] = {}

    # Act
    is_tracing = configure_tracing(settings, environ=environ)

    # Assert
    assert is_tracing is True
    assert environ["LANGSMITH_API_KEY"] == "lsv2-test-key"
    assert environ["LANGSMITH_PROJECT"] == "crossbid-test"
    assert all(environ[name] == "true" for name in TRACING_FLAG_ENV_VARS)


def test_tracing_stays_silent_without_a_key(
    valid_env: None, caplog: pytest.LogCaptureFixture, recwarn: pytest.WarningsRecorder
) -> None:
    """S0.3.3: no key means no tracing, no warning, no exception, no degraded run."""
    # Arrange
    settings = load()
    environ: dict[str, str] = {}

    # Act
    with caplog.at_level(logging.DEBUG):
        is_tracing = configure_tracing(settings, environ=environ)

    # Assert
    assert is_tracing is False
    assert all(environ[name] == "false" for name in TRACING_FLAG_ENV_VARS)
    assert "LANGSMITH_API_KEY" not in environ
    assert caplog.records == []
    assert len(recwarn) == 0


@pytest.mark.parametrize("blank", ["", "   "])
def test_a_blank_langsmith_key_disables_tracing(
    valid_env: None, monkeypatch: pytest.MonkeyPatch, blank: str
) -> None:
    """`.env.example` ships `LANGSMITH_API_KEY=`, which must mean "off", not "empty key"."""
    # Arrange
    monkeypatch.setenv("LANGSMITH_API_KEY", blank)
    environ: dict[str, str] = {}

    # Act / Assert
    assert configure_tracing(load(), environ=environ) is False
    assert "LANGSMITH_API_KEY" not in environ


def test_a_stale_tracing_flag_is_turned_off(valid_env: None) -> None:
    """A developer's exported LANGCHAIN_TRACING_V2 must not make a keyless run trace."""
    # Arrange
    environ = {"LANGCHAIN_TRACING_V2": "true", "LANGSMITH_TRACING": "true"}

    # Act
    configure_tracing(load(), environ=environ)

    # Assert
    assert all(environ[name] == "false" for name in TRACING_FLAG_ENV_VARS)


def test_langsmith_itself_reports_tracing_disabled(
    valid_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Proof the no-key path is silent at the library level, not just in our own flags."""
    # Arrange -- setenv, not a raw write, so monkeypatch restores the process afterwards
    for name in TRACING_FLAG_ENV_VARS:
        monkeypatch.setenv(name, "true")

    # Act
    configure_tracing(load(), environ=os.environ)

    # Assert
    assert langsmith_utils.tracing_is_enabled() is False


def test_bid_run_config_carries_the_bid_id_as_metadata() -> None:
    # Act
    config = bid_run_config("bid-42")

    # Assert -- the acceptance criterion of S0.3.3
    assert config["metadata"] == {"bid_id": "bid-42"}


def test_bid_run_config_accepts_a_uuid() -> None:
    # Arrange
    bid_id = uuid.UUID("11111111-2222-3333-4444-555555555555")

    # Act / Assert
    assert bid_run_config(bid_id)["metadata"] == {"bid_id": str(bid_id)}


def test_bid_run_config_carries_the_thread_id_and_run_name() -> None:
    # Act
    config = bid_run_config("bid-42", thread_id="bid:42", run_name="check_reqs")

    # Assert
    assert config["configurable"] == {"thread_id": "bid:42"}
    assert config["run_name"] == "check_reqs"
    assert config["metadata"] == {"bid_id": "bid-42"}


def test_bid_run_config_omits_what_it_was_not_given() -> None:
    # Act
    config = bid_run_config("bid-42")

    # Assert
    assert "configurable" not in config
    assert "run_name" not in config


def test_bid_run_config_merges_extra_metadata_without_mutating_it() -> None:
    # Arrange
    extra = {"source_language": "de"}

    # Act
    config = bid_run_config("bid-42", metadata=extra)

    # Assert
    assert config["metadata"] == {"source_language": "de", "bid_id": "bid-42"}
    assert extra == {"source_language": "de"}


def test_extra_metadata_cannot_shadow_the_bid_id() -> None:
    # Act
    config = bid_run_config("bid-42", metadata={"bid_id": "wrong"})

    # Assert
    assert config["metadata"]["bid_id"] == "bid-42"


@pytest.mark.parametrize("bid_id", ["", "   "])
def test_bid_run_config_refuses_a_blank_bid_id(bid_id: str) -> None:
    # Act / Assert -- a trace without a bid id cannot be found again
    with pytest.raises(ValueError, match="bid_id"):
        bid_run_config(bid_id)
