"""S4.6.2 — the `app_settings` row: layer 3 of the settings, read at startup and written by
the developer panel.

`migrations/0001_init.sql` declared the table and seeded its one row; `settings.py` has
carried the pure half of this story since S0.3.2 (`AppSettingsRow`, `apply_app_settings_row`)
and left the query behind a stub that raised `NotImplementedError`. This module is the query.
Three things about it are decisions rather than plumbing.

**There is one row and it belongs to nobody.** Every other module under `readmodel/` carries
`company_id` in every statement and a `SCOPED_STATEMENTS` tuple for the tenant-scope test to
walk, because the API connects as a `BYPASSRLS` role and that predicate is the only wall
between two companies (ADR-0009). The predicate test does not apply here, and that is worth
saying rather than leaving a reader to wonder whether a scope was forgotten: `app_settings`
has no `company_id` column at all. It is a property of the *process* — the same models,
temperature and prompt for every tenant — which is exactly why `GET /dev/settings` takes no
tenant either. What stands in for the scope is `id = 1`: the table's own check constraint
allows no other id, and both statements name it so a second row can never be read or written
by accident.

**The write is an upsert, not an update.** 0001 seeds the row, so an `update ... where id = 1`
would work on every database this project has ever had — and would silently affect zero rows
on one where somebody deleted it, leaving the panel to report a save that changed nothing.
`insert ... on conflict (id) do update` answers with the row either way, and `returning`
hands back what was actually stored so the caller re-applies *that*, never the request it
sent.

**Every column is replaced on every write.** The row's contract (`AppSettingsRow`) is that a
NULL column means "fall back to the YAML", so "clear this override" has to be expressible, and
the only way to express it without a sentinel is to send the whole row. A partial update that
skipped absent columns could never put a value back to its default. The panel therefore
sends all five columns each time, nulling the ones that equal the default.

The row is external data whatever wrote it — the panel, a migration, a hand in the Supabase
editor — so `fetch_app_settings_row` hands it through `AppSettingsRow.model_validate` and a
`models` object naming a role that does not exist fails here, at startup, rather than as a
`KeyError` inside the first bid. The connection protocol is `readmodel.bids.ConnectionSource`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, LiteralString

from psycopg.types.json import Jsonb

from crossbid.readmodel.bids import ConnectionSource
from crossbid.settings import AppSettingsRow

# ------------------------------------------------------------------------- statements

SELECT_APP_SETTINGS: Final[LiteralString] = """
select models, temperature, max_tokens, system_prompt, enabled_tools
from app_settings
where id = 1
"""
"""Layer 3, read once at startup. `updated_at` is deliberately not selected: nothing in the
process acts on when the row changed, only on what it says."""

UPSERT_APP_SETTINGS: Final[LiteralString] = """
insert into app_settings (id, models, temperature, max_tokens, system_prompt, enabled_tools)
values (1, %(models)s, %(temperature)s, %(max_tokens)s, %(system_prompt)s, %(enabled_tools)s)
on conflict (id) do update
    set models        = excluded.models,
        temperature   = excluded.temperature,
        max_tokens    = excluded.max_tokens,
        system_prompt = excluded.system_prompt,
        enabled_tools = excluded.enabled_tools,
        updated_at    = now()
returning models, temperature, max_tokens, system_prompt, enabled_tools
"""
"""The one write. See the module docstring for why it is an upsert and why every column is
set. The database's own check constraints (temperature 0 to 2, max_tokens > 0) are a second
line behind `apply_app_settings_row`, which the route runs *before* this statement so that a
row that would fail the next startup is never stored."""

ROW_STATEMENTS: Final[tuple[LiteralString, ...]] = (SELECT_APP_SETTINGS, UPSERT_APP_SETTINGS)
"""Both statements, so a test can assert each names the one row and nothing else."""

ROW_PREDICATE: Final = "id = 1"


# -------------------------------------------------------------------------- operations


async def fetch_app_settings_row(db: ConnectionSource) -> AppSettingsRow | None:
    """The stored row, re-validated, or `None` when the table holds no row.

    `None` rather than an error because 0001's seed is `on conflict do nothing`: a database
    that lost the row is one running on the YAML alone, which is a valid configuration and
    what `apply_app_settings_row(settings, None)` already means.
    """
    async with db.connection() as conn:
        record = await (await conn.execute(SELECT_APP_SETTINGS)).fetchone()
    return None if record is None else _row(record)


async def store_app_settings_row(db: ConnectionSource, row: AppSettingsRow) -> AppSettingsRow:
    """Replace the row with `row` and answer what was stored.

    The caller has already validated the merge (`apply_app_settings_row`) — this function
    does not, because a row refused here would be refused with a database error that names
    a constraint rather than a field. What comes back is read from `returning`, so a value
    the column changed on the way in — jsonb key order, a `text[]` — is what the process
    goes on to run with.
    """
    async with db.connection() as conn:
        record = await (await conn.execute(UPSERT_APP_SETTINGS, _params(row))).fetchone()
    assert record is not None, "an upsert with `returning` always yields its row"
    return _row(record)


def _params(row: AppSettingsRow) -> dict[str, Any]:
    """The row as bound parameters. `models` goes as `Jsonb`, because psycopg adapts a plain
    dict to nothing a `jsonb` column accepts; `enabled_tools` goes as a `list`, which psycopg
    adapts to a Postgres array — a tuple would be sent as a composite record (CLAUDE.md)."""
    return {
        "models": (
            None
            if row.models is None
            else Jsonb({role.value: slug for role, slug in row.models.items()})
        ),
        "temperature": row.temperature,
        "max_tokens": row.max_tokens,
        "system_prompt": row.system_prompt,
        "enabled_tools": None if row.enabled_tools is None else list(row.enabled_tools),
    }


def _row(record: Mapping[str, Any]) -> AppSettingsRow:
    """A record back into the contract, validated: the table is external data."""
    tools = record["enabled_tools"]
    return AppSettingsRow.model_validate(
        {
            "models": record["models"],
            "temperature": record["temperature"],
            "max_tokens": record["max_tokens"],
            "system_prompt": record["system_prompt"],
            "enabled_tools": None if tools is None else tuple(tools),
        }
    )
