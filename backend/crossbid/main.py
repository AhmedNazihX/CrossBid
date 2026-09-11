"""App factory and the startup that opens -- or deliberately skips -- the database.

Startup order, in `lifespan`:

1. Settings are loaded (or refused, S0.3.2) and tracing is switched on or off (S0.3.3).
2. If `DATABASE_URL` is set, the pool is opened and LangGraph's tables are created with
   `.setup()` (S0.2.2), then every bid a previous process left mid-run is resumed from its
   checkpoint (S3.1.1). If it is **unset**, the API starts without a database and says so
   once in the log: the `/health` route, the OpenAPI schema and `npm run gen:api` (which
   CI runs against a booted API with no Postgres) must work with nothing behind them. An
   unreachable database, by contrast, is a startup failure -- silently running without
   checkpoints would lose every paused bid.

CORS, rate limiting and the routers arrive with the stories that need them (S0.3.1, S2.3.3,
S3.1.1); see docs/project-plan.md.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Final

from fastapi import APIRouter, FastAPI, HTTPException, Request, status
from pydantic import BaseModel

from crossbid.agent.runner import BidRunner, resume_unfinished_runs
from crossbid.db import Database
from crossbid.settings import Settings, configure_tracing, get_settings

logger = logging.getLogger(__name__)

NO_DATABASE_MESSAGE: Final = (
    "DATABASE_URL is not set: starting without a database. Checkpoints, the Store and every "
    "read-model route are unavailable; /health and /openapi.json work."
)


class Health(BaseModel):
    status: str
    service: str


async def open_database(settings: Settings) -> Database | None:
    """The pool for this process, or `None` when no `DATABASE_URL` is configured."""
    if settings.env.database_url is None:
        logger.warning(NO_DATABASE_MESSAGE)
        return None
    db = await Database.connect(settings.env.database_url.get_secret_value())
    await db.setup()
    logger.info("database pool open (max_size=%d); LangGraph tables ready", db.max_size)
    return db


async def start_runner(db: Database | None, settings: Settings) -> BidRunner | None:
    """Resume every bid a previous process left mid-run (S3.1.1), or nothing without a pool.

    The checkpointer holds each run's state, so resuming is re-invoking the graph on the
    bid's thread; the runner also owns the tasks new `POST /bids` calls start.
    """
    if db is None:
        return None
    return await resume_unfinished_runs(db, settings)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the API. `settings` is injectable so tests never read a developer's `.env`."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved = settings if settings is not None else get_settings()
        configure_tracing(resolved)
        db = await open_database(resolved)
        runner = await start_runner(db, resolved)
        app.state.settings = resolved
        app.state.db = db
        app.state.bid_runner = runner
        try:
            yield
        finally:
            # Runs are awaited or cancelled before the pool they borrow from closes.
            if runner is not None:
                await runner.shutdown()
            if db is not None:
                await db.close()

    app = FastAPI(
        title="Crossbid API",
        version="0.1.0",
        description="Cross-border EU tender go/no-go qualification agent.",
        lifespan=lifespan,
    )

    @app.get("/health", response_model=Health, tags=["meta"])
    async def health() -> Health:
        """Liveness probe. Used by Compose and by the smoke test."""
        return Health(status="ok", service="crossbid-api")

    for router in _routers():
        app.include_router(router)
    return app


def _routers() -> list[APIRouter]:
    """The routers, imported here because they depend on this module's dependencies.

    `routers/*.py` import `get_database` and `get_app_settings` from `crossbid.main`, so a
    top-of-module import here would be circular. Registration order is also the order
    `openapi-typescript` emits components in (ADR-0009), so keep it stable.
    """
    from crossbid.routers.bids import router as bids_router
    from crossbid.routers.documents import router as documents_router

    return [documents_router, bids_router]


def get_app_settings(request: Request) -> Settings:
    """FastAPI dependency: the `Settings` this app was created with.

    Routers take this rather than `get_settings()` so that a test's injected settings reach
    every dependency, and so the `app_settings` row override (S4.6.2) has one place to land.
    """
    settings: Settings = request.app.state.settings
    return settings


def get_database(request: Request) -> Database:
    """FastAPI dependency: the process pool, for routers that need a connection.

    Answers 503 rather than crashing when the API was started without `DATABASE_URL`, so
    the failure names the variable instead of surfacing as an `AttributeError`.
    """
    db: Database | None = request.app.state.db
    if db is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The API was started without DATABASE_URL; this route needs a database.",
        )
    return db


app = create_app()
