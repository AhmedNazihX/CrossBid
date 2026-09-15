"""Startup: settings, tracing, and the database that is opened or deliberately skipped.

Offline throughout. `create_app` takes its `Settings`, and `open_database` is the seam the
lifespan calls, so a fake `Database` proves the hook without a pool ever being built.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from crossbid import main as main_module
from crossbid.db import Database, DatabaseError
from crossbid.llm import LlmError
from crossbid.main import (
    NO_DATABASE_MESSAGE,
    create_app,
    get_database,
    open_database,
    replace_app_settings,
    settings_provider,
)
from crossbid.readmodel.app_settings import SELECT_APP_SETTINGS
from crossbid.settings import AppSettingsRowError, Settings
from tests.conftest import FakeConnectionSource

GOOD_DSN = "postgresql://crossbid:pw@localhost:5432/crossbid"

NO_ROW: list[dict[str, Any]] = []
"""The table with its seeded row missing -- a valid database that runs on the YAML alone."""


def app_settings_record(**columns: Any) -> list[dict[str, Any]]:
    """The one `app_settings` row as the pool hands it back, every column NULL unless set."""
    record: dict[str, Any] = {
        "models": None,
        "temperature": None,
        "max_tokens": None,
        "system_prompt": None,
        "enabled_tools": None,
    }
    return [record | columns]


class FakeDatabase:
    """What the lifespan needs of `Database`: `setup`, `close`, `max_size`, and since
    S4.6.2 one borrowed connection, which answers the `app_settings` read with `rows`."""

    max_size = 10

    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.events: list[str] = []
        self.source = FakeConnectionSource(NO_ROW if rows is None else rows)

    def connection(self) -> Any:
        return self.source.connection()

    async def setup(self) -> None:
        self.events.append("setup")

    async def close(self) -> None:
        self.events.append("close")


class FakeRunner:
    """What the lifespan needs of `BidRunner`: `shutdown`."""

    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def shutdown(self) -> None:
        self.events.append("runner.shutdown")


def with_database_url(settings: Settings, dsn: str) -> Settings:
    """A new `Settings` whose env layer carries `dsn`; the original is untouched."""
    env = settings.env.model_copy(update={"database_url": SecretStr(dsn)})
    return Settings(env=env, runtime=settings.runtime)


# ---------------------------------------------------------------- no DATABASE_URL


def test_the_api_starts_without_a_database_and_says_so_once(
    offline_settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    # Act
    with (
        caplog.at_level("WARNING", logger="crossbid.main"),
        TestClient(create_app(offline_settings)) as client,
    ):
        response = client.get("/health")

    # Assert
    assert response.status_code == 200
    assert client.app.state.db is None  # type: ignore[attr-defined]
    assert client.app.state.bid_runner is None  # type: ignore[attr-defined]
    assert client.app.state.settings is offline_settings  # type: ignore[attr-defined]
    assert client.app.state.base_settings is offline_settings  # type: ignore[attr-defined]
    assert [r.getMessage() for r in caplog.records].count(NO_DATABASE_MESSAGE) == 1


def test_a_route_that_needs_the_database_answers_503_without_one(
    offline_settings: Settings,
) -> None:
    # Arrange -- a throwaway route wired to the dependency, as the routers will be
    app = create_app(offline_settings)

    @app.get("/needs-db")
    async def needs_db(db: Database = Depends(get_database)) -> dict[str, int]:
        return {"max_size": db.max_size}

    # Act
    with TestClient(app) as client:
        response = client.get("/needs-db")

    # Assert
    assert response.status_code == 503
    assert "DATABASE_URL" in response.json()["detail"]


# ------------------------------------------------------------- model slugs (S5.1)


def test_startup_probes_the_model_slugs_before_opening_the_pool(
    offline_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-0005's "fail fast on a slug that does not answer" needs a caller to be true.

    The function guarded itself on `VERIFY_MODEL_SLUGS` and nothing invoked it, so the
    setting documented a check that never ran. Ordering matters as much as the call: a
    slug that 404s should stop the boot before a pool is built for it.
    """
    # Arrange
    order: list[str] = []
    monkeypatch.setattr(
        main_module, "verify_configured_models", lambda _settings: order.append("verify")
    )

    async def fake_open(settings: Settings) -> None:
        order.append("open_database")
        return None

    monkeypatch.setattr(main_module, "open_database", fake_open)

    # Act
    with TestClient(create_app(offline_settings)):
        pass

    # Assert
    assert order == ["verify", "open_database"]


def test_a_slug_that_does_not_answer_stops_the_boot(
    offline_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Discovering it mid-bid would be after the upload and the parse were paid for."""

    # Arrange
    def refuse(_settings: Settings) -> None:
        raise LlmError("The model slug 'x' did not answer on this account.")

    monkeypatch.setattr(main_module, "verify_configured_models", refuse)

    # Act & Assert
    with (
        pytest.raises(LlmError, match="did not answer"),
        TestClient(create_app(offline_settings)),
    ):
        pass  # pragma: no cover - the context manager never opens


# ------------------------------------------------------------------- DATABASE_URL


def test_the_lifespan_opens_sets_up_and_closes_the_database(
    offline_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    fake = FakeDatabase()
    seen: list[str] = []

    async def fake_connect(dsn: str, **_kwargs: Any) -> FakeDatabase:
        seen.append(dsn)
        return fake

    async def fake_resume(db: Any, current_settings: Any) -> FakeRunner:
        assert db is fake, "runs resume on the pool that was just opened"
        fake.events.append("resume")
        return FakeRunner(fake.events)

    monkeypatch.setattr(Database, "connect", staticmethod(fake_connect))
    monkeypatch.setattr(main_module, "resume_unfinished_runs", fake_resume)
    settings = with_database_url(offline_settings, GOOD_DSN)
    app = create_app(settings)

    @app.get("/needs-db")
    async def needs_db(db: Database = Depends(get_database)) -> dict[str, int]:
        return {"max_size": db.max_size}

    # Act
    with TestClient(app) as client:
        response = client.get("/needs-db")
        assert fake.events == ["setup", "resume"], "pool and runner are ready before requests"
        assert isinstance(client.app.state.bid_runner, FakeRunner)  # type: ignore[attr-defined]

    # Assert -- runs stop before the pool they borrow from closes
    assert seen == [GOOD_DSN]
    assert response.json() == {"max_size": 10}
    assert fake.events == ["setup", "resume", "runner.shutdown", "close"]
    assert fake.source.only.sql == SELECT_APP_SETTINGS, "the row is read once, at startup"


# --------------------------------------------------- the app_settings row (S4.6.2)


def booted(
    settings: Settings, fake: FakeDatabase, monkeypatch: pytest.MonkeyPatch
) -> tuple[FastAPI, dict[str, Any]]:
    """An app started over `fake`, with the resume replaced by one that keeps the provider
    it was handed, so a test can ask what the runner would build its graph from."""
    handed: dict[str, Any] = {}

    async def fake_connect(dsn: str, **_kwargs: Any) -> FakeDatabase:
        return fake

    async def fake_resume(db: Any, current_settings: Any) -> FakeRunner:
        handed["provider"] = current_settings
        return FakeRunner(fake.events)

    monkeypatch.setattr(Database, "connect", staticmethod(fake_connect))
    monkeypatch.setattr(main_module, "resume_unfinished_runs", fake_resume)
    return create_app(with_database_url(settings, GOOD_DSN)), handed


def test_the_stored_row_is_applied_over_the_yaml_at_startup(
    offline_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Layer 3 becomes real: the panel's own edits would otherwise vanish on restart."""
    # Arrange
    fake = FakeDatabase(app_settings_record(temperature=0.7, max_tokens=512))
    app, _handed = booted(offline_settings, fake, monkeypatch)

    # Act
    with (
        caplog.at_level("INFO", logger="crossbid.main"),
        TestClient(app) as client,
    ):
        settings: Settings = client.app.state.settings  # type: ignore[attr-defined]
        base: Settings = client.app.state.base_settings  # type: ignore[attr-defined]

    # Assert
    assert settings.runtime.temperature == 0.7
    assert settings.runtime.max_tokens == 512
    assert settings.runtime.models == offline_settings.runtime.models, "NULL keeps the YAML"
    assert base.runtime is offline_settings.runtime, (
        "the pristine settings stay beside the merged"
    )
    assert base is not settings
    messages = [r.getMessage() for r in caplog.records]
    assert "app_settings row overrides the YAML for: max_tokens, temperature" in messages


def test_a_row_without_overrides_says_so_and_changes_nothing(
    offline_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    app, _handed = booted(offline_settings, FakeDatabase(app_settings_record()), monkeypatch)

    with (
        caplog.at_level("INFO", logger="crossbid.main"),
        TestClient(app) as client,
    ):
        settings: Settings = client.app.state.settings  # type: ignore[attr-defined]

    assert settings.runtime == offline_settings.runtime
    assert "app_settings row holds no overrides" in " ".join(
        r.getMessage() for r in caplog.records
    )


def test_the_log_names_the_overriding_columns_never_their_values(
    offline_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The prompt is text an operator may not want in a log; a column name is not."""
    prompt = "Secret standing instructions nobody should see in a log line."
    fake = FakeDatabase(app_settings_record(system_prompt=prompt))
    app, _handed = booted(offline_settings, fake, monkeypatch)

    with caplog.at_level("INFO", logger="crossbid.main"), TestClient(app):
        pass

    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "system_prompt" in joined
    assert prompt not in joined


def test_a_row_that_would_not_validate_stops_the_boot(
    offline_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exactly as a bad YAML would. The write route validates before it stores, so this
    can only happen to a row edited by hand -- and then the boot must say so, not run on
    half a configuration."""
    fake = FakeDatabase(app_settings_record(temperature=7.0))
    app, _handed = booted(offline_settings, fake, monkeypatch)

    with pytest.raises(AppSettingsRowError, match="temperature"), TestClient(app):
        pass  # pragma: no cover - the context manager never opens


def test_a_missing_row_runs_on_the_yaml_alone(
    offline_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, _handed = booted(offline_settings, FakeDatabase(NO_ROW), monkeypatch)

    with TestClient(app) as client:
        settings: Settings = client.app.state.settings  # type: ignore[attr-defined]
        base: Settings = client.app.state.base_settings  # type: ignore[attr-defined]

    assert settings is base, "no row: the merged settings are the pristine object itself"


def test_the_runner_is_handed_the_settings_in_force_not_a_copy(
    offline_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The hot-swap seam (agent/runner.py, point 4): what the provider answers is the merged
    settings at boot and whatever the panel put on `app.state` afterwards."""
    fake = FakeDatabase(app_settings_record(temperature=0.7))
    app, handed = booted(offline_settings, fake, monkeypatch)

    with TestClient(app) as client:
        provider = handed["provider"]
        assert provider() is client.app.state.settings  # type: ignore[attr-defined]
        assert provider().runtime.temperature == 0.7
        replace_app_settings(app, offline_settings)
        assert provider() is offline_settings


def test_settings_provider_reads_app_state_live(offline_settings: Settings) -> None:
    app = FastAPI()
    app.state.settings = offline_settings
    current = settings_provider(app)
    later = with_database_url(offline_settings, GOOD_DSN)

    assert current() is offline_settings
    replace_app_settings(app, later)
    assert current() is later


@pytest.mark.anyio
async def test_open_database_returns_none_without_a_url(offline_settings: Settings) -> None:
    assert await open_database(offline_settings) is None


@pytest.mark.anyio
async def test_an_unreachable_database_fails_startup(
    offline_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Running on without checkpoints would lose every paused bid; refusing is the point."""

    async def refuse(_dsn: str, **_kwargs: Any) -> FakeDatabase:
        raise DatabaseError("Could not open the database pool")

    monkeypatch.setattr(Database, "connect", staticmethod(refuse))
    settings = with_database_url(offline_settings, GOOD_DSN)

    with pytest.raises(DatabaseError):
        await open_database(settings)


def test_the_module_level_app_is_built_lazily_enough_to_import(
    offline_settings: Settings,
) -> None:
    """`uvicorn crossbid.main:app` imports the module; nothing may connect at import time."""
    assert isinstance(main_module.app, FastAPI)
    assert "db" not in vars(main_module.app.state)


def test_the_documents_routes_are_registered(client: TestClient) -> None:
    """S2.2.3 is wired; the OpenAPI schema is what `frontend/lib/api.ts` is generated from."""
    paths = client.get("/openapi.json").json()["paths"]
    assert "/documents" in paths
    assert "/documents/{document_id}" in paths


def test_the_bids_routes_are_registered(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/bids" in paths
    assert "/bids/{bid_id}" in paths


def test_cors_allows_the_web_origin_and_the_dev_company_header(client: TestClient) -> None:
    """A browser preflight from the web app must pass, custom header included; the shell at
    :3000 could otherwise not call :8000 at all."""
    response = client.options(
        "/documents",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-dev-company,content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "x-dev-company" in response.headers["access-control-allow-headers"].lower()
    assert response.headers["access-control-allow-credentials"] == "true"


def test_cors_refuses_another_origin(client: TestClient) -> None:
    response = client.options(
        "/documents",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_the_web_origin_comes_from_settings(offline_settings: Settings) -> None:
    env = offline_settings.env.model_copy(update={"web_origin": "https://app.crossbid.example"})
    with TestClient(create_app(Settings(env=env, runtime=offline_settings.runtime))) as client:
        response = client.options(
            "/health",
            headers={
                "Origin": "https://app.crossbid.example",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert response.headers["access-control-allow-origin"] == "https://app.crossbid.example"
