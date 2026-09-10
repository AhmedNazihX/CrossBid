"""Apply numbered SQL migrations. Story S0.2.1.

    uv run python scripts/migrate.py            # apply everything pending
    uv run python scripts/migrate.py --status    # show what is applied and what is pending
    uv run python scripts/migrate.py --dry-run   # name the files that would run, change nothing

Plain SQL files in `migrations/`, named `NNNN_description.sql`, applied in numeric order. No
migration framework: the schema is small, the files are readable, and a framework would add a
dependency and a second source of truth about what the database looks like.

Three properties worth stating, because they are what make this safe to run repeatedly:

* **Idempotent.** Applied versions are recorded in `schema_migrations`; a second run applies
  nothing. Each file also uses `if not exists` throughout, so it survives being replayed
  against a database that already has the objects.
* **Tamper-evident.** The SHA-256 of every applied file is stored. Editing a migration that has
  already run is refused, because the database no longer matches the file and no amount of
  re-running will fix that. Write a new migration instead.
* **Safe under concurrency.** A session-level advisory lock means two runners (say a developer
  and a deploy hook) cannot interleave. The second waits, then finds nothing to do.

LangGraph's own tables are not managed here — `PostgresSaver.setup()` and
`PostgresStore.setup()` create those at API startup (S0.2.2).
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import psycopg

BACKEND = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = BACKEND / "migrations"
FILENAME_PATTERN = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")

# Arbitrary but fixed: any process using this key serialises with us.
ADVISORY_LOCK_KEY = 0x43524F53_53424944  # "CROSSBID"

BOOTSTRAP_SQL = """
create table if not exists schema_migrations (
    version     text primary key,
    name        text not null,
    checksum    text not null,
    applied_at  timestamptz not null default now()
);
"""


class MigrationError(RuntimeError):
    """A migration could not be applied, or the recorded history is inconsistent."""


@dataclass(frozen=True)
class Migration:
    """One migration file on disk."""

    version: str
    name: str
    path: Path
    sql: str

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.sql.encode("utf-8")).hexdigest()


def discover(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    """Every well-named migration, in numeric order.

    A file that does not match `NNNN_description.sql` is an error rather than a warning: a
    typo'd name would otherwise be skipped silently and the schema would quietly diverge.
    """
    if not directory.is_dir():
        raise MigrationError(f"no migrations directory at {directory}")

    found: list[Migration] = []
    seen_versions: dict[str, str] = {}
    for path in sorted(directory.glob("*.sql")):
        match = FILENAME_PATTERN.match(path.name)
        if not match:
            raise MigrationError(
                f"{path.name} does not match NNNN_description.sql "
                "(four digits, then lowercase words separated by underscores)"
            )
        version, name = match.group(1), match.group(2)
        if version in seen_versions:
            raise MigrationError(
                f"duplicate migration version {version}: "
                f"{seen_versions[version]} and {path.name}"
            )
        seen_versions[version] = path.name
        found.append(
            Migration(
                version=version,
                name=name,
                path=path,
                sql=path.read_text(encoding="utf-8"),
            )
        )
    return found


def applied_migrations(conn: psycopg.Connection) -> dict[str, str]:
    """Version -> checksum for everything already applied."""
    with conn.cursor() as cur:
        cur.execute("select version, checksum from schema_migrations order by version")
        return {row[0]: row[1] for row in cur.fetchall()}


def check_for_tampering(migrations: list[Migration], applied: dict[str, str]) -> None:
    """Refuse to continue if an already-applied file has been edited.

    The database reflects what the file said *when it ran*. Re-running an edited file would
    not reconcile the two, so failing loudly is the only honest option.
    """
    changed = [
        m.path.name
        for m in migrations
        if m.version in applied and applied[m.version] != m.checksum
    ]
    if changed:
        raise MigrationError(
            "these migrations have already been applied but their contents have changed: "
            + ", ".join(changed)
            + ". Migrations are immutable once applied — add a new numbered file instead of "
            "editing one."
        )

    orphaned = sorted(set(applied) - {m.version for m in migrations})
    if orphaned:
        raise MigrationError(
            f"the database records migrations that no longer exist on disk: {orphaned}. "
            "This usually means the wrong database, or a deleted migration file."
        )


def apply_one(conn: psycopg.Connection, migration: Migration) -> None:
    """Run one migration and record it, atomically.

    The file contains its own `begin`/`commit`, so this runs it with autocommit on and lets
    the file own its transaction — that is what lets a migration use statements that cannot
    run inside an outer transaction block if one is ever needed. The bookkeeping insert then
    follows in its own statement.
    """
    with conn.cursor() as cur:
        cur.execute(migration.sql)
        cur.execute(
            "insert into schema_migrations (version, name, checksum) values (%s, %s, %s)",
            (migration.version, migration.name, migration.checksum),
        )


def run(dsn: str, *, dry_run: bool = False, directory: Path = MIGRATIONS_DIR) -> int:
    """Apply every pending migration. Returns the number applied."""
    migrations = discover(directory)
    if not migrations:
        print("no migrations found")
        return 0

    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("select pg_advisory_lock(%s)", (ADVISORY_LOCK_KEY,))
        try:
            with conn.cursor() as cur:
                cur.execute(BOOTSTRAP_SQL)

            applied = applied_migrations(conn)
            check_for_tampering(migrations, applied)

            pending = [m for m in migrations if m.version not in applied]
            if not pending:
                print(f"up to date: {len(applied)} migration(s) already applied")
                return 0

            if dry_run:
                for migration in pending:
                    print(f"would apply {migration.path.name}")
                return 0

            for migration in pending:
                print(f"applying {migration.path.name} ...", end=" ", flush=True)
                try:
                    apply_one(conn, migration)
                except psycopg.Error as exc:
                    print("FAILED")
                    raise MigrationError(f"{migration.path.name} failed: {exc}") from exc
                print("ok")
            return len(pending)
        finally:
            with conn.cursor() as cur:
                cur.execute("select pg_advisory_unlock(%s)", (ADVISORY_LOCK_KEY,))


def show_status(dsn: str, *, directory: Path = MIGRATIONS_DIR) -> None:
    """Print what is applied and what is pending."""
    migrations = discover(directory)
    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(BOOTSTRAP_SQL)
        applied = applied_migrations(conn)
        with conn.cursor() as cur:
            cur.execute("select version, applied_at from schema_migrations order by version")
            timestamps = dict(cur.fetchall())

    for migration in migrations:
        if migration.version in applied:
            when = timestamps.get(migration.version)
            unchanged = applied[migration.version] == migration.checksum
            marker = "applied" if unchanged else "CHANGED"
            print(f"  {migration.version}  {marker:<8} {migration.name}  {when}")
        else:
            print(f"  {migration.version}  pending  {migration.name}")


def resolve_dsn() -> str:
    """DATABASE_URL from the environment or the repository-root .env.

    Deliberately does not import `crossbid.settings`: migrations must run before the app is
    importable and without requiring every application secret to be present.
    """
    import os

    dsn = os.getenv("DATABASE_URL")
    if dsn:
        return dsn
    env_file = BACKEND.parent / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            if name.strip() == "DATABASE_URL":
                value = value.strip().strip("'\"")
                if value:
                    return value
    raise MigrationError(
        "DATABASE_URL is not set. Copy infra/.env.example to .env at the repository root and "
        "set it to the Supabase DIRECT connection string (not the transaction pooler)."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--status", action="store_true", help="show applied and pending, apply nothing"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="name pending migrations, apply nothing"
    )
    parser.add_argument("--dsn", help="override DATABASE_URL")
    args = parser.parse_args()

    try:
        dsn = args.dsn or resolve_dsn()
        if args.status:
            show_status(dsn)
            return 0
        count = run(dsn, dry_run=args.dry_run)
        if count:
            print(f"applied {count} migration(s)")
        return 0
    except MigrationError as exc:
        print(f"migration error: {exc}", file=sys.stderr)
        return 1
    except psycopg.Error as exc:
        print(f"database error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
