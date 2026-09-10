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

    monkeypatch.setattr(Database, "connect", staticmethod(fake_connect))
    settings = with_database_url(offline_settings, GOOD_DSN)
    app = create_app(settings)

    @app.get("/needs-db")
    async def needs_db(db: Database = Depends(get_database)) -> dict[str, int]:
        return {"max_size": db.max_size}

    # Act
    with TestClient(app) as client:
        response = client.get("/needs-db")
        assert fake.events == ["setup"], "the pool is ready before the first request"

    # Assert
    assert seen == [GOOD_DSN]
    assert response.json() == {"max_size": 10}
    assert fake.events == ["setup", "close"]


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
