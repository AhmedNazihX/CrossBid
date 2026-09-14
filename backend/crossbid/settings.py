"""One `Settings` object, and the startup guards that refuse a broken configuration.

Three layers, lowest first (S0.3.2):

1. **`settings.default.yaml`** -- behaviour an operator tunes: model slugs per role,
   temperature, max tokens, chunking, agent limits, enabled tools. Committed, reviewed,
   and the *only* place a model slug is written down (CLAUDE.md).
2. **The environment** -- secrets and deployment wiring, through `pydantic-settings`:
   `OPENROUTER_API_KEY`, `APP_ENCRYPTION_KEY`, `DATABASE_URL`, `AUTH_MODE`, `ENV`,
   `LANGSMITH_*`. Read from the process environment first and from the repository-root
   `.env` second, so `make dev-api` works without exporting anything by hand.
   Every variable is documented in `infra/.env.example`.
3. **The `app_settings` row** -- the same behavioural values, changed at run time from the
   developer panel (S4.6.2), overriding the YAML defaults per non-NULL column.

The two groups are disjoint by design: no key of `settings.default.yaml` is also an
environment variable, so "which wins" never has to be guessed. Secrets live only in the
environment; behaviour lives only in the YAML and the row.

Layers 1 and 2 are implemented here. Layer 3 is `apply_app_settings_row`, which is pure
and tested; the query that reads the row waits for the database (`fetch_app_settings_row`).

Two more guards live here because they are pure validation and need no database, even
though the stories that own them come later:

- **S0.2.2** -- `check_database_dsn` refuses Supabase's transaction pooler, which has no
  prepared statements and so breaks the LangGraph checkpointer.
- **S0.3.1** -- `AUTH_MODE=dev` is refused when `ENV=production`.

LangSmith tracing (S0.3.3) is at the bottom of the file rather than in an
`observability.py` of its own: turning tracing on is startup configuration like the
guards above, and the whole of it is one flag plus one config shape.

Secrets are `SecretStr` throughout, so neither a `repr`, a log line, a JSON dump nor an
exception message can carry a key value (security.md). Error messages name the *variable*,
never its value.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable, Mapping, MutableMapping
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any, Final
from urllib.parse import parse_qsl, urlsplit

import yaml
from langchain_core.runnables import RunnableConfig
from langsmith import utils as langsmith_utils
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR: Final = Path(__file__).resolve().parents[1]
DEFAULTS_FILE: Final = BACKEND_DIR / "settings.default.yaml"
DEFAULT_ENV_FILE: Final = BACKEND_DIR.parent / ".env"
"""The repository-root `.env` of `infra/.env.example`. Absent in the container, where
Compose passes the variables directly; a missing file is not an error."""

ENV_EXAMPLE_HINT: Final = (
    "Copy infra/.env.example to .env at the repository root and set every required variable."
)

POSTGRES_URL_SCHEMES: Final = frozenset({"postgres", "postgresql"})
SUPABASE_POOLER_HOST_SUFFIX: Final = ".pooler.supabase.com"
TRANSACTION_POOLER_PORT: Final = 6543
SESSION_POOLER_PORT: Final = 5432
TRUTHY: Final = frozenset({"true", "1"})
VALUE_ERROR_PREFIX: Final = "Value error, "

MAX_SIGNED_URL_TTL_SECONDS: Final = 600
"""Ten minutes, and both the cap and the default of `SIGNED_URL_TTL_SECONDS`.

S2.2.2's acceptance criterion is "the signed URL expires within 10 minutes", so a longer
value is a configuration that breaks the story: it is refused here, at startup, rather
than granted to a caller at request time. `ingestion/storage.py` reads the number from
this one place, so the guard and the URL it protects cannot drift apart.
"""


class SettingsError(RuntimeError):
    """Startup refused. The message names the variable or file to fix, never its value."""


class Environment(StrEnum):
    """`ENV`. Closed on purpose: `ENV=prod` must fail, not quietly mean "not production"
    and so let dev auth mode through in a deployed environment."""

    DEVELOPMENT = "development"
    TEST = "test"  # what CI sets
    PRODUCTION = "production"


class AuthMode(StrEnum):
    """`AUTH_MODE`. `dev` accepts an `X-Dev-Company` header instead of a token (S0.3.1)."""

    DEV = "dev"
    SUPABASE = "supabase"


class ModelRole(StrEnum):
    """The roles `settings.default.yaml` maps to slugs. Code asks for a role, never a slug."""

    EXTRACT = "extract"
    CHEAP = "cheap"
    EMBED = "embed"
    JUDGE = "judge"
    FALLBACK = "fallback"
    """Where a role goes after a timed-out call and one retry (S3.4.4). A *different
    vendor* on purpose: the failure a fallback has to survive is the primary provider being
    slow or down, and a second OpenAI slug on the same route would be down with it."""


class _Frozen(BaseModel):
    """Immutable and strict: an unknown key is a typo, and a typo should fail at startup."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class ModelSlugs(_Frozen):
    """Role -> OpenRouter slug. Every slug was confirmed with a live call (ADR-0004/0005)."""

    extract: str
    cheap: str
    embed: str
    judge: str
    fallback: str

    def for_role(self, role: ModelRole) -> str:
        """The configured slug for `role`. Exhaustive by design: a new role must be mapped.

        pyright rejects a missing case (no return on that path), which is the point of the
        `match`; coverage cannot see that the enum is closed, hence `no branch`.
        """
        match role:
            case ModelRole.EXTRACT:
                return self.extract
            case ModelRole.CHEAP:
                return self.cheap
            case ModelRole.EMBED:
                return self.embed
            case ModelRole.JUDGE:
                return self.judge
            case ModelRole.FALLBACK:  # pragma: no branch -- the enum is closed
                return self.fallback


class IngestionSettings(_Frozen):
    """Chunking and embedding shape (F2.2). `embed_dimensions` must match the slug."""

    chunk_tokens: int = Field(gt=0)
    chunk_overlap: int = Field(ge=0)
    section_pages: int = Field(gt=0)
    embed_dimensions: int = Field(gt=0)


class AgentSettings(_Frozen):
    """Concurrency limits on the two fan-outs, each bounding calls to OpenRouter.

    `extract_concurrency` is the deterministic one -- sections of `extract_reqs` (S3.2.1), a
    fixed number of structured calls. `check_concurrency` is the agentic one -- per-requirement
    ReAct loops in `check_reqs` (F3.3), each up to `max_tool_calls_per_requirement` calls.
    Separate keys because the call shapes differ, so tuning one must not move the other.
    """

    extract_concurrency: int = Field(gt=0)
    check_concurrency: int = Field(gt=0)
    max_tool_calls_per_requirement: int = Field(gt=0)
    run_budget_seconds: float = Field(gt=0)
    """S3.1.1: the wall-clock a run may take before the live test fails it (600)."""
    run_budget_usd: float = Field(gt=0)
    """S3.1.1: the OpenRouter-reported cost one bid may incur (2.50)."""
    llm_timeout_seconds: float = Field(gt=0)
    """S3.4.4: how long one model call may take before it counts as timed out.

    A per-call bound, not a per-run one — `run_budget_seconds` is the latter. It has to be
    generous enough for a dense extraction section returning `max_tokens` of structured
    output and tight enough that a hung connection does not sit inside the run budget."""


class EvaluationSettings(_Frozen):
    """The offline quality gates. Read by `scripts/recall.py`, never by a request path.

    Separate from `AgentSettings` because the two answer different questions: `agent`
    bounds what one bid run may spend, `evaluation` says how good the result has to be
    before the story counts as delivered. Keeping the number here rather than in the
    script is what lets S3.2.3's threshold and S7.1's be the same number.
    """

    recall_threshold: float = Field(gt=0.0, le=1.0)
    """S3.2.1: recall on the golden mandatory requirements must reach this (0.9)."""


class RuntimeSettings(_Frozen):
    """What an operator may change without a deploy: YAML defaults, `app_settings` on top."""

    models: ModelSlugs
    available_models: tuple[str, ...] = Field(min_length=1)
    """The picker list of S4.6.2: the *verified* set, never OpenRouter's own catalogue
    (ADR-0005)."""
    temperature: float = Field(ge=0.0, le=2.0)
    max_tokens: int = Field(gt=0)
    system_prompt: str | None = None
    """Not in `settings.default.yaml` yet, so `None` until it is added (see the report)."""
    ingestion: IngestionSettings
    agent: AgentSettings
    evaluation: EvaluationSettings
    """Offline gates (S3.2.3). Deliberately *not* published by `GET /dev/settings`: it is
    a maintainer's scoring threshold, not a knob the developer panel changes."""
    enabled_tools: tuple[str, ...]


class EnvSettings(BaseSettings):
    """Secrets and deployment wiring. Fields for auth and CORS arrive with the stories that
    read them (S0.3.1); unknown variables are ignored, not rejected, because one `.env`
    serves both apps."""

    model_config = SettingsConfigDict(
        frozen=True,
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
        # `OPENROUTER_API_KEY=` in a .env file means "not set", not "the empty key".
        env_ignore_empty=True,
    )

    openrouter_api_key: SecretStr
    app_encryption_key: SecretStr
    database_url: SecretStr | None = None
    """Unset means the Compose Postgres. Holds a password, hence `SecretStr`."""
    auth_mode: AuthMode = AuthMode.DEV
    environment: Environment = Field(default=Environment.DEVELOPMENT, validation_alias="ENV")
    supabase_url: str | None = None
    """The hosted project's API URL. Unset in tests and offline work: Storage is not
    mocked locally, so anything needing it takes a fake bucket instead (project-plan,
    Environments). `ingestion/storage.py` is the one place that refuses the absence."""
    supabase_service_role_key: SecretStr | None = Field(
        default=None, validation_alias="SUPABASE_SERVICE_KEY"
    )
    """The service-role key, which bypasses Storage's own policies and so is server-side
    only -- the browser gets the anon key, which the backend never reads. Named for what
    the key *is*; the alias is the variable name `infra/.env.example` and Compose already
    pass, and `populate_by_name` accepts `SUPABASE_SERVICE_ROLE_KEY` as well."""
    supabase_storage_bucket: str = "company-documents"
    """Private bucket holding every uploaded PDF under its `company_id` prefix (S2.2.2)."""
    signed_url_ttl_seconds: int = MAX_SIGNED_URL_TTL_SECONDS
    """How long a document's signed URL stays valid. The default is the cap."""
    langsmith_api_key: SecretStr | None = None
    langsmith_project: str = "crossbid"
    developer_emails: str = ""
    """Comma-separated list of the emails `/dev/*` is open to (S0.3.1).

    A plain string rather than a `tuple`, because pydantic-settings parses a complex type
    out of the environment as **JSON** and would reject `a@b.de,c@d.de` before any
    validator ran. `is_developer_email` below is the one reader, so the split happens in
    exactly one place. Unset means nobody: an empty list must close the door, not open it."""
    web_origin: str = "http://localhost:3000"
    """The one browser origin allowed by CORS: the web app. Custom headers such as
    `X-Dev-Company` need an explicit allow-list, so the middleware is built from settings."""
    verify_model_slugs: bool = False
    """Opt-in live check of every configured chat slug at startup (ADR-0005). Off by
    default: CI has no real key and unit tests must not open a socket."""

    def is_developer_email(self, email: str | None) -> bool:
        """Whether `email` is on `DEVELOPER_EMAILS`, trimmed and case-folded on both sides.

        A token with no email is never a developer: Supabase omits the claim for phone and
        anonymous sign-ins, and an absent identity must not match an absent list.
        """
        if email is None or not email.strip():
            return False
        listed = {
            entry.strip().casefold()
            for entry in self.developer_emails.split(",")
            if entry.strip()
        }
        return email.strip().casefold() in listed

    @field_validator("openrouter_api_key", "app_encryption_key", mode="after")
    @classmethod
    def _reject_blank(cls, value: SecretStr) -> SecretStr:
        """`mode="after"`, so the value pydantic reports on failure is already masked."""
        if not value.get_secret_value().strip():
            raise ValueError("is set but blank")
        return value

    @field_validator("signed_url_ttl_seconds", mode="after")
    @classmethod
    def _cap_signed_url_ttl(cls, value: int) -> int:
        """S2.2.2 promises a document URL that expires within ten minutes, so an expiry
        that breaks the promise is refused while starting up rather than handed out."""
        if not 0 < value <= MAX_SIGNED_URL_TTL_SECONDS:
            raise ValueError(
                f"must be between 1 and {MAX_SIGNED_URL_TTL_SECONDS} seconds: a document's "
                "signed URL has to expire within ten minutes (S2.2.2)"
            )
        return value


class Settings(_Frozen):
    """The one object the API, the graph and the tools read their configuration from."""

    env: EnvSettings
    runtime: RuntimeSettings


# ------------------------------------------------------------------- error messages


def _describe(error: Mapping[str, Any], rename: Callable[[str], str]) -> str:
    """One validation error as a sentence built from its location, never from its input."""
    name = rename(".".join(str(part) for part in error["loc"]))
    if error["type"] == "missing":
        return f"{name} is not set"
    # Our own validators already read as sentences, so pydantic's prefix is dropped and
    # the name runs straight into the message: "OPENROUTER_API_KEY is set but blank".
    message = str(error["msg"]).removeprefix(VALUE_ERROR_PREFIX)
    separator = " " if error["type"] == "value_error" else ": "
    return f"{name}{separator}{message}"


def _format_errors(exc: ValidationError, rename: Callable[[str], str]) -> str:
    return "; ".join(_describe(error, rename) for error in exc.errors())


# -------------------------------------------------------- guards that need no database


def check_database_dsn(dsn: str) -> None:
    """Refuse a DSN the LangGraph checkpointer cannot work over (S0.2.2).

    Supabase offers three connection strings. The **direct** connection
    (`db.<ref>.supabase.co:5432`) and the **session pooler**
    (`<region>.pooler.supabase.com:5432`) both keep a real Postgres session, so prepared
    statements work. The **transaction pooler** is the same pooler host on port **6543**
    and hands out a connection per transaction: no prepared statements, and
    `PostgresSaver` fails at run time with an error that says nothing about pooling.

    The rule is deliberately narrow -- a pooler *host* on the transaction *port*, or an
    explicit `pgbouncer=true` -- so that the DSNs local development and CI use
    (`@db:5432`, `@localhost:5432`) are never touched. A false positive here would stop
    all local work, which is worse than missing an exotic pooler URL.
    """
    try:
        parts = urlsplit(dsn)
        port = parts.port
    except ValueError as exc:
        raise SettingsError(f"DATABASE_URL is not a valid URL: {exc}") from exc

    if parts.scheme not in POSTGRES_URL_SCHEMES:
        raise SettingsError(
            "DATABASE_URL must be a postgresql:// or postgres:// URL, as "
            "infra/.env.example documents (the libpq `key=value` form is not accepted)."
        )

    host = (parts.hostname or "").lower()
    if host.endswith(SUPABASE_POOLER_HOST_SUFFIX) and port == TRANSACTION_POOLER_PORT:
        raise SettingsError(
            f"DATABASE_URL points at Supabase's transaction pooler ({host}:{port}). It has "
            "no prepared statements, so the LangGraph checkpointer cannot use it. Use the "
            f"session pooler -- the same host on port {SESSION_POOLER_PORT} -- in "
            "deployment, or the direct connection db.<project-ref>.supabase.co:"
            f"{SESSION_POOLER_PORT} locally."
        )

    if dict(parse_qsl(parts.query)).get("pgbouncer", "").lower() in TRUTHY:
        raise SettingsError(
            "DATABASE_URL carries pgbouncer=true, which marks a transaction-pooling "
            "connection: no prepared statements, so the LangGraph checkpointer fails. Use "
            f"the session pooler (port {SESSION_POOLER_PORT}) or the direct connection."
        )


def _require_supabase_url_for_supabase_auth(env: EnvSettings) -> None:
    """S0.3.1: the JWKS URL is derived from `SUPABASE_URL`, so there is nothing to verify
    tokens against without it. Refused at startup rather than 500ing on the first request."""
    if env.auth_mode is AuthMode.SUPABASE and env.supabase_url is None:
        raise SettingsError(
            "AUTH_MODE=supabase needs SUPABASE_URL: the signing keys are read from "
            "{SUPABASE_URL}/auth/v1/.well-known/jwks.json (S0.3.1). Set SUPABASE_URL, or "
            "run with AUTH_MODE=dev outside production."
        )


def _refuse_dev_auth_in_production(env: EnvSettings) -> None:
    """S0.3.1: dev auth mode trusts an `X-Dev-Company` header, so it may never be deployed."""
    if env.auth_mode is AuthMode.DEV and env.environment is Environment.PRODUCTION:
        raise SettingsError(
            "AUTH_MODE=dev is refused when ENV=production: dev auth mode accepts an "
            "X-Dev-Company header instead of a Supabase token (S0.3.1). Set "
            "AUTH_MODE=supabase, or run with ENV=development."
        )


# --------------------------------------------------------------------------- loading


def load_runtime_settings(defaults_file: Path = DEFAULTS_FILE) -> RuntimeSettings:
    """Layer 1: the committed YAML defaults."""
    try:
        raw = yaml.safe_load(defaults_file.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SettingsError(
            f"Cannot read the settings defaults at {defaults_file}: {exc}"
        ) from exc
    except yaml.YAMLError as exc:
        raise SettingsError(f"{defaults_file} is not valid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise SettingsError(
            f"{defaults_file} must contain a mapping of settings, not a {type(raw).__name__}."
        )

    try:
        return RuntimeSettings.model_validate(raw)
    except ValidationError as exc:
        raise SettingsError(f"{defaults_file} is invalid: {_format_errors(exc, str)}") from exc


def _load_env_settings(env_file: Path | None) -> EnvSettings:
    """Layer 2: the environment, with the root `.env` as a fallback for host runs."""
    try:
        return EnvSettings(_env_file=env_file)  # type: ignore[call-arg]
    except ValidationError as exc:
        raise SettingsError(
            f"Invalid configuration: {_format_errors(exc, str.upper)}. {ENV_EXAMPLE_HINT}"
        ) from exc


def load_settings(
    *, env_file: Path | None = DEFAULT_ENV_FILE, defaults_file: Path = DEFAULTS_FILE
) -> Settings:
    """Build the settings object, or refuse to start.

    Pass `env_file=None` to read the process environment only -- which every test does, so
    that no test depends on a developer's real `.env`.
    """
    env = _load_env_settings(env_file)
    _refuse_dev_auth_in_production(env)
    _require_supabase_url_for_supabase_auth(env)
    if env.database_url is not None:
        check_database_dsn(env.database_url.get_secret_value())
    return Settings(env=env, runtime=load_runtime_settings(defaults_file))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The process-wide settings, for `Depends(get_settings)` and for the graph.

    Cached: FastAPI resolves the dependency on every request, and the YAML is read once.
    `get_settings.cache_clear()` exists for tests and for the developer panel, which
    changes the `app_settings` row and then needs the next read to see it (S4.6.2).
    """
    return load_settings()


# ------------------------------------------------- layer 3: the `app_settings` override


class AppSettingsRow(_Frozen):
    """The single `app_settings` row (`id=1`) of the read model (S0.2.3).

    Every column is optional and a NULL one means "keep the YAML default", so the
    developer panel can change one value without restating the rest. `models` mirrors the
    `jsonb` column and may be partial: `{"judge": "..."}` replaces only the judge slug.

    Defined here rather than in `models/` because it is a settings concern that nothing
    above the settings layer ever sees; `models/` holds the domain objects the API and the
    frontend share.
    """

    models: Mapping[ModelRole, str] | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    system_prompt: str | None = None
    enabled_tools: tuple[str, ...] | None = None


def apply_app_settings_row(settings: Settings, row: AppSettingsRow | None) -> Settings:
    """Return a **new** `Settings` with the row's non-NULL columns over the YAML defaults.

    Nothing is mutated: `settings` is still valid and unchanged afterwards. The merged
    values are re-validated, because a database row is external input like any other --
    a `temperature` of 7 in the table must be refused, not sent to OpenRouter.
    """
    if row is None:
        return settings

    overrides = row.model_dump(exclude_none=True, exclude={"models"})
    merged: dict[str, Any] = settings.runtime.model_dump() | overrides
    if row.models:
        merged["models"] = settings.runtime.models.model_dump() | {
            role.value: slug for role, slug in row.models.items()
        }

    try:
        runtime = RuntimeSettings.model_validate(merged)
    except ValidationError as exc:
        raise SettingsError(
            f"The app_settings row (id=1) is invalid: {_format_errors(exc, str)}"
        ) from exc
    return Settings(env=settings.env, runtime=runtime)


def fetch_app_settings_row() -> AppSettingsRow | None:
    """Read the `app_settings` row, or `None` when the table holds no row yet.

    **Not implemented, deliberately.** There is no database: S0.2.1 (the Supabase project)
    is blocked, S0.2.3 writes the migration that creates this table, and S0.2.2 opens the
    psycopg pool this query would borrow a connection from. Faking the read would hide
    that. The `SELECT` goes here, and the wiring goes in `main.py`'s startup hook:

        settings = apply_app_settings_row(load_settings(), fetch_app_settings_row())
    """
    raise NotImplementedError(
        "The app_settings override needs the database: table in S0.2.3, pool in S0.2.2."
    )


# ------------------------------------------------------------- tracing (S0.3.3)

TRACING_FLAG_ENV_VARS: Final = (
    "LANGSMITH_TRACING",
    "LANGSMITH_TRACING_V2",
    "LANGCHAIN_TRACING",
    "LANGCHAIN_TRACING_V2",
)
"""All four names LangSmith and LangChain read, written together.

`langsmith.utils.tracing_is_enabled` prefers `*_TRACING_V2` over `*_TRACING` and the
`LANGSMITH_` namespace over `LANGCHAIN_`. Writing one name would let a stale value of
another win, so all four always carry the same answer.
"""

LANGSMITH_API_KEY_ENV_VAR: Final = "LANGSMITH_API_KEY"
LANGSMITH_PROJECT_ENV_VAR: Final = "LANGSMITH_PROJECT"
BID_ID_METADATA_KEY: Final = "bid_id"


def _tracing_key(settings: Settings) -> str | None:
    """The LangSmith key if there is a usable one. `LANGSMITH_API_KEY=` counts as absent."""
    key = settings.env.langsmith_api_key
    if key is None:
        return None
    return key.get_secret_value().strip() or None


def configure_tracing(
    settings: Settings, *, environ: MutableMapping[str, str] = os.environ
) -> bool:
    """Turn LangSmith tracing on when a key is configured, and off when there is none.

    Returns whether tracing is on. Called once at startup.

    With no key the application must run *normally and silently* (S0.3.3): no warning, no
    exception, no slower path. That is why the flags are set to `"false"` rather than left
    alone -- an exported `LANGCHAIN_TRACING_V2=true` in a developer's shell would otherwise
    have LangChain try to trace with no credentials.

    This is the one function in the package that writes to the process environment, which
    is how LangChain's tracing switch is documented; `environ` is injectable so that tests
    do not have to.
    """
    key = _tracing_key(settings)
    is_tracing = key is not None

    for name in TRACING_FLAG_ENV_VARS:
        environ[name] = "true" if is_tracing else "false"
    if key is not None:
        environ[LANGSMITH_API_KEY_ENV_VAR] = key
        environ[LANGSMITH_PROJECT_ENV_VAR] = settings.env.langsmith_project

    # LangSmith caches environment lookups, so a value read before this call would stick.
    langsmith_utils.get_env_var.cache_clear()  # type: ignore[attr-defined]
    return is_tracing


def bid_run_config(
    bid_id: str | uuid.UUID,
    *,
    thread_id: str | None = None,
    run_name: str | None = None,
    metadata: Mapping[str, str] | None = None,
) -> RunnableConfig:
    """The config a bid's graph runs are invoked with, so every trace carries `bid_id`.

    The graph itself lands in S3.1.1; this is the shape it invokes with, and the reason
    S0.3.3's acceptance criterion ("a trace appears with `bid_id` metadata") is a property
    of one function rather than of every call site. `thread_id` is the checkpointer's
    conversation key, which the same call has to carry (S0.2.2).

    The mapping passed in is copied, never extended, and `bid_id` always wins.
    """
    identifier = str(bid_id).strip()
    if not identifier:
        raise ValueError("bid_id must not be blank: a trace without one cannot be found again.")

    config: RunnableConfig = {"metadata": {**(metadata or {}), BID_ID_METADATA_KEY: identifier}}
    if thread_id is not None:
        config["configurable"] = {"thread_id": thread_id}
    if run_name is not None:
        config["run_name"] = run_name
    return config
