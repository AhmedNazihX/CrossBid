"""App factory and the startup that opens -- or deliberately skips -- the database.

Startup order, in `lifespan`:

1. Settings are loaded (or refused, S0.3.2) and tracing is switched on or off (S0.3.3).
2. If `VERIFY_MODEL_SLUGS` is set, every slug a role may run on is probed with a one-token
   call and a slug that does not answer fails the boot (ADR-0005, S5.1). Off by default:
   each call costs money and needs a real key, which CI has not.
3. If `DATABASE_URL` is set, the pool is opened and LangGraph's tables are created with
   `.setup()` (S0.2.2). If it is **unset**, the API starts without a database and says so
   once in the log: the `/health` route, the OpenAPI schema and `npm run gen:api` (which
   CI runs against a booted API with no Postgres) must work with nothing behind them. An
   unreachable database, by contrast, is a startup failure -- silently running without
   checkpoints would lose every paused bid.
4. The `app_settings` row is read and applied over the YAML (S4.6.2, layer 3 of
   `settings.py`). Both the pristine and the merged `Settings` are kept on `app.state`:
   requests read the merged one through `get_app_settings`, and `PUT /dev/settings` needs
   the pristine one to validate the *next* row against -- a row replaces the previous row,
   so merging it over already-merged settings would make an override impossible to clear.
   A row that does not validate stops the boot, exactly as a bad YAML would; the write
   route validates before it stores so that this can only happen to a hand-edited row.
5. Every bid a previous process left mid-run is resumed from its checkpoint (S3.1.1), on a
   runner whose graph factory reads the settings *in force* rather than a copy taken here,
   so a change made from the panel reaches the next run without a restart.

CORS allows exactly one origin -- the web app (`WEB_ORIGIN`) -- and the custom `X-Dev-Company`
header the dev auth bridge reads; a browser at `:3000` could otherwise not reach `:8000` at all.

Rate limiting (S2.3.3) is deliberately **not** here: it hangs off `POST /documents` and
`POST /bids` as a dependency, because those two are the routes that spend money and the
workspace's two-second poll must not be throttled with them. See `crossbid/rate_limit.py`.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Final

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from crossbid.agent.runner import BidRunner, SettingsProvider, resume_unfinished_runs
from crossbid.db import Database
from crossbid.deps import (
    settings_provider,
)
from crossbid.llm import verify_configured_models
from crossbid.readmodel.app_settings import fetch_app_settings_row
from crossbid.readmodel.documents import fail_interrupted_documents
from crossbid.settings import (
    AppSettingsRow,
    Settings,
    apply_app_settings_row,
    configure_tracing,
    get_settings,
)

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


async def apply_stored_settings(db: Database | None, settings: Settings) -> Settings:
    """Layer 3: the `app_settings` row over the YAML, or the YAML alone without a pool.

    Logs *which* columns override, never their values -- `system_prompt` is text an
    operator may not want in a log, and a slug or a number is a fact the panel shows anyway.
    The log line exists because an override is otherwise invisible: `settings.default.yaml`
    says one thing, the process does another, and nothing on disk explains why.
    """
    if db is None:
        return settings
    row = await fetch_app_settings_row(db)
    applied = apply_app_settings_row(settings, row)
    overriding = () if row is None else _overriding_columns(row)
    if overriding:
        logger.info("app_settings row overrides the YAML for: %s", ", ".join(overriding))
    else:
        logger.info("app_settings row holds no overrides; running on settings.default.yaml")
    return applied


def _overriding_columns(row: AppSettingsRow) -> tuple[str, ...]:
    return tuple(sorted(row.model_dump(exclude_none=True)))


async def start_runner(
    db: Database | None, current_settings: SettingsProvider
) -> BidRunner | None:
    """Resume every bid a previous process left mid-run (S3.1.1), or nothing without a pool.

    The checkpointer holds each run's state, so resuming is re-invoking the graph on the
    bid's thread; the runner also owns the tasks new `POST /bids` calls start.
    """
    if db is None:
        return None
    return await resume_unfinished_runs(db, current_settings)


async def sweep_interrupted_documents(db: Database | None) -> int:
    """Mark documents a previous process left mid-pipeline as failed, or do nothing.

    Failure here is logged and swallowed. A sweep that cannot run leaves rows exactly as
    they were, which is the state the API has always started in; refusing to boot over it
    would trade a stale row for an outage.
    """
    if db is None:
        return 0
    try:
        return await fail_interrupted_documents(db)
    except Exception:
        logger.exception("could not sweep documents left unfinished by a restart")
        return 0


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the API. `settings` is injectable so tests never read a developer's `.env`."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved = settings if settings is not None else get_settings()
        configure_tracing(resolved)
        # Before the pool, because a slug that does not answer should stop the boot rather
        # than be discovered by a bid. Returns immediately unless VERIFY_MODEL_SLUGS is set;
        # a plain call rather than a thread because nothing is being served yet.
        verify_configured_models(resolved)
        db = await open_database(resolved)
        # Settings are on `app.state` before the runner exists, because the runner's graph
        # factory reads them from there (step 5) and a resume at startup builds the graph.
        app.state.base_settings = resolved
        app.state.settings = await apply_stored_settings(db, resolved)
        app.state.db = db
        # Before the runner, and deliberately not part of it: a bid run is checkpointed and
        # can be resumed, an upload is not. A document this process's predecessor left in
        # `uploaded` or `parsed` will never move again, and the browser polls it every two
        # seconds regardless, so it is marked failed with a sentence saying to upload it
        # again. Never raises the boot: a sweep is a courtesy, not a precondition.
        await sweep_interrupted_documents(db)
        runner = await start_runner(db, settings_provider(app))
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
    # Imported here, not at module level: `auth` depends on this module's dependencies.
    from crossbid.auth import DEV_COMPANY_HEADER

    # Middleware is fixed at construction, so the origin is read from the settings passed
    # in (or the process settings when none were), not from the lifespan's resolved copy.
    origin = (settings if settings is not None else get_settings()).env.web_origin
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin],
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        # `If-None-Match` is not a CORS-safelisted *request* header, so it needs naming here
        # as well as in `expose_headers` below — the browser sends one and reads the other,
        # and only having half of the pair makes the conditional poll silently unconditional.
        allow_headers=["Authorization", "Content-Type", "If-None-Match", DEV_COMPANY_HEADER],
        allow_credentials=True,
        # `Retry-After` is not on the CORS safelist, so without this the browser at :3000
        # cannot read it off a 429 from :8000 and the ask panel falls back to the sentence
        # in `detail` instead of a clock time (S4.6.1, ADR-0058). `ETag` is not on it either,
        # and without it the workspace cannot echo the tag back as `If-None-Match`, so every
        # poll of a run would keep resending the whole matrix (M13, ADR-0093). Response
        # headers only: nothing here widens what a request may send.
        expose_headers=["Retry-After", "ETag"],
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
    from crossbid.routers.chat import router as chat_router
    from crossbid.routers.companies import router as companies_router
    from crossbid.routers.dev import router as dev_router
    from crossbid.routers.documents import router as documents_router
    from crossbid.routers.feedback import router as feedback_router
    from crossbid.routers.provider_keys import router as provider_keys_router
    from crossbid.routers.tenders import router as tenders_router

    # Appended, never inserted: a new router at the front would renumber every generated
    # component in `frontend/lib/api.ts` for no reason.
    return [
        documents_router,
        bids_router,
        companies_router,
        dev_router,
        tenders_router,
        feedback_router,
        chat_router,
        provider_keys_router,
    ]


# The five request-scoped providers live in `crossbid/deps.py` so that `auth`, `rate_limit`
# and the routers do not have to import this module, which imports them (M20). Re-exported
# here because they were `crossbid.main`'s for four increments: every override in the suite
# keys on the function object, and this keeps it the same object.


app = create_app()
