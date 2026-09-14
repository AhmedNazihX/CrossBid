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
from crossbid.main import NO_DATABASE_MESSAGE, create_app, get_database, open_database
from crossbid.settings import Settings

GOOD_DSN = "postgresql://crossbid:pw@localhost:5432/crossbid"


class FakeDatabase:
    """What the lifespan needs of `Database`: `setup`, `close`, `max_size`."""

    max_size = 10

    def __init__(self) -> None:
        self.events: list[str] = []

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

    async def fake_resume(db: Any, settings: Settings) -> FakeRunner:
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
