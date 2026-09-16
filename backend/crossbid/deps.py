"""The five things a request needs from the app, so nothing below has to import the app.

`auth.py`, `rate_limit.py` and six routers all took these from `crossbid.main` — the module
that builds the application and imports every one of them back. The plan's rule is that
dependencies point one way (`routers/eval → agent/ingestion/readmodel →
tools/reference/memory/guards → models/db/settings`, `docs/project-plan.md`), and eight
upward imports into the app module broke it. Only a deferred import inside `create_app` kept
the cycle from exploding at import time, which is a fact about import order rather than a
design (audit M20).

Nothing here knows how the app is built. Each provider reads one attribute of
`request.app.state` (or of a `FastAPI` handed to it), which is a contract the app fills at
startup, and that is the whole of the coupling. `main.py` re-exports all five, so a test
that overrides `crossbid.main.get_database` still overrides the same object.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request, status

from crossbid.db import Database
from crossbid.settings import Settings, SettingsProvider


def get_app_settings(request: Request) -> Settings:
    """FastAPI dependency: the `Settings` in force -- the YAML with the row applied.

    Routers take this rather than `get_settings()` so that a test's injected settings reach
    every dependency, and so the `app_settings` row override (S4.6.2) has one place to land:
    `PUT /dev/settings` replaces `app.state.settings`, and the next request sees it.
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


def get_base_settings(request: Request) -> Settings:
    """FastAPI dependency: the `Settings` *before* the row -- YAML and environment only.

    What `PUT /dev/settings` validates a new row against. The row it receives is the whole
    row, replacing whatever was stored, so the base it merges over must be the one the
    startup merged over; merging over `get_app_settings` would keep every old override
    alive under the new row, and "back to the default" would be unreachable.
    """
    settings: Settings = request.app.state.base_settings
    return settings


def settings_provider(app: FastAPI) -> SettingsProvider:
    """A callable answering the settings in force at the moment it is called.

    Handed to the runner instead of a `Settings` value (`agent/runner.py`, point 4): a
    graph built from a captured copy would run new bids on the configuration the process
    booted with, however many times the panel had changed it since.
    """

    def current() -> Settings:
        settings: Settings = app.state.settings
        return settings

    return current


def replace_app_settings(app: FastAPI, settings: Settings) -> None:
    """Swap the settings requests and new runs see, **in this process**.

    The one writer of `app.state.settings` after startup, so that "who changes the
    configuration at run time" has one answer.

    *This process* is the whole of the scope and it is deliberate (M25, ADR-0059). The row is
    stored in Postgres and read at startup, so a second API process picks the change up when
    it next starts — not when the panel is saved. Crossbid deploys as one container and this
    is the same bound `rate_limit.py` accepts for the same reason; the two API processes
    `db.py` sizes the pool for are a *local* Compose-plus-host pair, not a scaled deployment.
    Making a save reach every process needs a re-read on some clock, and putting a database
    round trip on the request path to serve a configuration one developer changes by hand
    would be a real cost for an imaginary deployment.
    """
    app.state.settings = settings
