"""Create the one `companies` row the Increment-1 demo needs. Developer tool, not a story.

    uv run python scripts/seed_dev_company.py            # insert (or find) the dev company
    uv run python scripts/seed_dev_company.py --dry-run  # print the row, connect to nothing

Every API route scopes by `company_id`, `POST /bids` answers 404 when the company row is
missing, and the web app names its tenant through the build-time `NEXT_PUBLIC_DEV_COMPANY_ID`.
Nothing creates that row before the company form (S2.4.1) and the demo seed (Increment 3),
so this fills the gap: one row, once, with placeholder facts. The real company profile is the
form's job; `profile` is deliberately left empty here.

Two properties make this safe to run casually:

* **Deterministic.** The id is a `uuid5` of a fixed name under a fixed namespace, so every
  developer, every database and every re-run gets the same id. That is what lets the id be
  pasted into `.env` once and survive a `make down`/`make dev` cycle that rebuilds the schema.
* **Idempotent.** `insert ... on conflict (id) do nothing`: the second run inserts nothing,
  says so, and still prints the id and the line to paste.

It refuses to run when `ENV=production`: a dev tenant must never appear in a deployed
database. Like `migrate.py`, it imports nothing from `crossbid` so it runs before the app is
importable and without every application secret being present.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from collections.abc import Mapping
from typing import Final

import migrate  # sibling script, not a package: on sys.path under `python scripts/<name>.py`
import psycopg

# Fixed so that the derived ids never change. Rotating it would orphan every `.env` that
# already carries NEXT_PUBLIC_DEV_COMPANY_ID.
SEED_NAMESPACE: Final = uuid.UUID("7f0b7d0e-4e6a-5a6c-9e1a-2c3d4e5f6a7b")
DEV_COMPANY_NAME: Final = "dev-company"
DEV_OWNER_NAME: Final = "dev-company-owner"

DEV_COMPANY_ID: Final = uuid.uuid5(SEED_NAMESPACE, DEV_COMPANY_NAME)
DEV_OWNER_USER_ID: Final = uuid.uuid5(SEED_NAMESPACE, DEV_OWNER_NAME)

# Placeholder facts only. Every value must satisfy the check constraints in
# migrations/0001_init.sql; tests/unit/test_seed_dev_company.py reads that file and asserts it.
DEV_COMPANY_ROW: Final[Mapping[str, str | uuid.UUID]] = {
    "id": DEV_COMPANY_ID,
    "owner_user_id": DEV_OWNER_USER_ID,
    "name": "Beispiel IT Services GmbH",
    "country": "de",
    "legal_form": "gmbh",
    "language": "de",
    "tone": "plain",
    "active_provider": "openrouter",
    "profile": "{}",
}

INSERT_SQL: Final = """
insert into companies
    (id, owner_user_id, name, country, legal_form, language, tone, active_provider, profile)
values
    (%(id)s, %(owner_user_id)s, %(name)s, %(country)s, %(legal_form)s, %(language)s,
     %(tone)s, %(active_provider)s, %(profile)s::jsonb)
on conflict (id) do nothing
returning id
"""

ENV_VAR: Final = "ENV"
PRODUCTION: Final = "production"
PASTE_VAR: Final = "NEXT_PUBLIC_DEV_COMPANY_ID"


class SeedError(RuntimeError):
    """The seed must not run here, or its inputs are missing."""


def read_env_var(name: str) -> str | None:
    """Environment first, repository-root `.env` second — the same order `resolve_dsn` uses.

    Duplicated rather than borrowed because `migrate.resolve_dsn` is specific to
    `DATABASE_URL` and this script must not edit it.
    """
    import os

    value = os.getenv(name)
    if value:
        return value
    env_file = migrate.BACKEND.parent / ".env"
    if not env_file.is_file():
        return None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        key, _, raw = line.partition("=")
        if key.strip() == name:
            candidate = raw.strip().strip("'\"")
            if candidate:
                return candidate
    return None


def refuse_in_production() -> None:
    """A dev tenant in a deployed database would be a real tenant nobody owns."""
    if read_env_var(ENV_VAR) == PRODUCTION:
        raise SeedError(
            f"{ENV_VAR}={PRODUCTION}: refusing to seed a dev company into a production "
            "database. Run this only against a local or development database."
        )


def insert_dev_company(conn: psycopg.Connection) -> bool:
    """Insert the row if absent. Returns True when this call created it."""
    with conn.cursor() as cur:
        cur.execute(INSERT_SQL, dict(DEV_COMPANY_ROW))
        return cur.fetchone() is not None


def paste_line(company_id: uuid.UUID = DEV_COMPANY_ID) -> str:
    """The exact line for `.env`; build-time in the web app, so `make build` follows."""
    return f"{PASTE_VAR}={company_id}"


def print_dry_run() -> None:
    print("would insert into companies (on conflict (id) do nothing):")
    for column, value in DEV_COMPANY_ROW.items():
        print(f"  {column:<16} {value}")
    print(paste_line())


def run(dsn: str) -> bool:
    """Seed against `dsn`, report the row's state, print the line to paste."""
    with psycopg.connect(dsn, autocommit=True) as conn:
        created = insert_dev_company(conn)
    state = "created" if created else "already present"
    print(f"dev company {state}: {DEV_COMPANY_ID}")
    print(paste_line())
    return created


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the row that would be inserted, connect to nothing",
    )
    parser.add_argument("--dsn", help="override DATABASE_URL")
    args = parser.parse_args()

    try:
        refuse_in_production()
        if args.dry_run:
            print_dry_run()
            return 0
        dsn = args.dsn or migrate.resolve_dsn()
        run(dsn)
        return 0
    except (SeedError, migrate.MigrationError) as exc:
        print(f"seed error: {exc}", file=sys.stderr)
        return 1
    except psycopg.Error as exc:
        print(
            f"database error: {exc}. Is the database up and migrated (`make migrate`)?",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
