"""`scripts/seed_dev_company.py` — the dev tenant seed. Developer tool, not a story.

Every test here is offline. The script is loaded by path, as `conftest.ecertis_generator`
does for the cache builder, and the database is a recording fake: no test opens a socket. The
parity test reads `migrations/0001_init.sql` as text, in the style of `test_migrations.py`,
so a seed value the schema would reject fails here rather than as an `IntegrityError` on a
developer's first `make seed-dev`.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import psycopg
import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = BACKEND_DIR / "scripts"
SCRIPT_PATH = SCRIPTS_DIR / "seed_dev_company.py"
INIT_SQL = BACKEND_DIR / "migrations" / "0001_init.sql"
ENV_EXAMPLE = BACKEND_DIR.parent / "infra" / ".env.example"

# Pinned literally, like `ADVISORY_LOCK_KEY`: this value is pasted into developers' `.env`
# files, so a well-meaning change to the namespace or the name must fail a test.
EXPECTED_DEV_COMPANY_ID = uuid.UUID("91d42546-c9ba-5815-bbb7-8831a728271d")


@pytest.fixture(scope="module")
def seed() -> Iterator[ModuleType]:
    """The script as a module; `scripts/` goes on `sys.path` so `import migrate` resolves."""
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        spec = importlib.util.spec_from_file_location("seed_dev_company", SCRIPT_PATH)
        assert spec is not None and spec.loader is not None, SCRIPT_PATH
        module = importlib.util.module_from_spec(spec)
        sys.modules["seed_dev_company"] = module
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.path.remove(str(SCRIPTS_DIR))
        sys.modules.pop("seed_dev_company", None)


class FakeCursor:
    """Records every `execute` and answers `fetchone` with what the test configured."""

    def __init__(self, row: tuple[Any, ...] | None) -> None:
        self._row = row
        self.executed: list[tuple[str, dict[str, Any]]] = []

    def execute(self, sql: str, params: dict[str, Any]) -> None:
        self.executed.append((sql, params))

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._row

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


class FakeConnection:
    """Enough of `psycopg.Connection` for the seed: one cursor, context-managed."""

    def __init__(self, row: tuple[Any, ...] | None) -> None:
        self.cursor_ = FakeCursor(row)

    def cursor(self) -> FakeCursor:
        return self.cursor_

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


@pytest.fixture
def not_production(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, seed: ModuleType) -> None:
    """No `ENV` anywhere: the environment is cleared and the root `.env` is a missing file."""
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(seed.migrate, "BACKEND", tmp_path / "backend")


def _constraint_values(sql: str, constraint: str) -> set[str]:
    """The quoted values inside `constraint <name> check (... in (...))`."""
    pattern = re.compile(
        rf"constraint\s+{re.escape(constraint)}\s+check\s*\((.*?)\)\s*\)",
        re.IGNORECASE | re.DOTALL,
    )
    matches = pattern.findall(sql)
    assert matches, f"constraint {constraint} not found in {INIT_SQL.name}"
    return set(re.findall(r"'([^']+)'", matches[-1]))


# --------------------------------------------------------------- determinism


def test_company_id_is_the_uuid5_of_the_fixed_name(seed: ModuleType) -> None:
    """Every developer and every re-run must derive the same id, or `.env` files rot."""
    # Act
    recomputed = uuid.uuid5(seed.SEED_NAMESPACE, "dev-company")

    # Assert
    assert recomputed == seed.DEV_COMPANY_ID
    assert seed.DEV_COMPANY_ID == EXPECTED_DEV_COMPANY_ID
    assert seed.DEV_COMPANY_ID.version == 5


def test_owner_user_id_is_deterministic_and_distinct_from_the_company_id(
    seed: ModuleType,
) -> None:
    """`companies_owner_user_id_key` is unique, so the owner id must be stable too."""
    assert uuid.uuid5(seed.SEED_NAMESPACE, "dev-company-owner") == seed.DEV_OWNER_USER_ID
    assert seed.DEV_OWNER_USER_ID != seed.DEV_COMPANY_ID


# --------------------------------------------------------------- the SQL


def test_insert_is_a_no_op_on_a_second_run(seed: ModuleType) -> None:
    """Idempotence lives in the statement itself, not in a select-then-insert race."""
    sql = " ".join(seed.INSERT_SQL.split())
    assert "on conflict (id) do nothing" in sql
    assert sql.endswith("returning id")


def test_insert_is_fully_parameterised(seed: ModuleType) -> None:
    """No row value is spliced into the SQL; every column is bound by name."""
    # Act
    placeholders = set(re.findall(r"%\((\w+)\)s", seed.INSERT_SQL))

    # Assert
    assert placeholders == set(seed.DEV_COMPANY_ROW)
    assert "'" not in seed.INSERT_SQL, "a quoted literal would be a value spliced into the SQL"


def test_insert_reports_created_when_the_row_comes_back(seed: ModuleType) -> None:
    # Arrange
    conn = FakeConnection(row=(seed.DEV_COMPANY_ID,))

    # Act
    created = seed.insert_dev_company(conn)

    # Assert
    assert created is True
    (sql, params), *rest = conn.cursor_.executed
    assert not rest, "exactly one statement"
    assert sql == seed.INSERT_SQL
    assert params == dict(seed.DEV_COMPANY_ROW)


def test_insert_reports_already_present_when_nothing_comes_back(seed: ModuleType) -> None:
    """`on conflict do nothing` returns no row, which is how the second run is detected."""
    # Arrange
    conn = FakeConnection(row=None)

    # Act / Assert
    assert seed.insert_dev_company(conn) is False


# --------------------------------------------------------------- constraint parity


def test_every_seed_value_satisfies_the_companies_check_constraints(seed: ModuleType) -> None:
    """A value the schema rejects would surface as an IntegrityError on the first run."""
    # Arrange
    sql = INIT_SQL.read_text(encoding="utf-8")
    row = seed.DEV_COMPANY_ROW
    enum_constraints = {
        "legal_form": "companies_legal_form_check",
        "tone": "companies_tone_check",
        "active_provider": "companies_active_provider_check",
    }

    # Act / Assert
    for column, constraint in enum_constraints.items():
        allowed = _constraint_values(sql, constraint)
        assert row[column] in allowed, f"{column}={row[column]!r} not in {sorted(allowed)}"
    country_pattern = re.search(r"country\s+text not null check \(country ~ '([^']+)'\)", sql)
    assert country_pattern is not None
    assert re.fullmatch(country_pattern.group(1).strip("^$"), str(row["country"]))


def test_every_inserted_column_exists_on_the_companies_table(seed: ModuleType) -> None:
    # Arrange
    sql = INIT_SQL.read_text(encoding="utf-8")
    body = re.search(r"create table if not exists companies \((.*?)\n\);", sql, re.DOTALL)
    assert body is not None
    declared = set(
        re.findall(r"^\s+(\w+)\s+(?:uuid|text|jsonb|timestamptz)", body.group(1), re.M)
    )

    # Assert
    assert set(seed.DEV_COMPANY_ROW) <= declared
    assert "name" in seed.DEV_COMPANY_ROW
    assert seed.DEV_COMPANY_ROW["profile"] == "{}", "the facts belong to S2.4.1's form"


# --------------------------------------------------------------- production refusal


def test_refuses_when_env_is_production_in_the_environment(
    seed: ModuleType, not_production: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.setenv("ENV", "production")

    # Act / Assert
    with pytest.raises(seed.SeedError, match="production"):
        seed.refuse_in_production()


def test_refuses_when_env_is_production_in_the_root_dotenv(
    seed: ModuleType, not_production: None, tmp_path: Path
) -> None:
    """The root `.env` is where a deploy usually sets `ENV`; the environment may be silent."""
    # Arrange
    (tmp_path / ".env").write_text("# comment\nENV='production'\n", encoding="utf-8")

    # Act / Assert
    with pytest.raises(seed.SeedError, match="production"):
        seed.refuse_in_production()


def test_the_environment_wins_over_the_root_dotenv(
    seed: ModuleType, not_production: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same precedence as `resolve_dsn`, so a shell override behaves as developers expect."""
    # Arrange
    (tmp_path / ".env").write_text("ENV=production\n", encoding="utf-8")
    monkeypatch.setenv("ENV", "development")

    # Act / Assert -- no exception
    seed.refuse_in_production()


def test_main_exits_one_in_production_without_connecting(
    seed: ModuleType,
    not_production: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Arrange
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setattr(sys, "argv", ["seed_dev_company.py", "--dsn", "postgresql://x"])
    monkeypatch.setattr(seed.psycopg, "connect", _refuse_to_connect)

    # Act
    code = seed.main()

    # Assert
    assert code == 1
    assert "seed error" in capsys.readouterr().err


# --------------------------------------------------------------- dry run and output


def test_dry_run_prints_the_row_and_connects_to_nothing(
    seed: ModuleType,
    not_production: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No DATABASE_URL anywhere, so a connection attempt would also fail on the DSN lookup."""
    # Arrange
    monkeypatch.setattr(sys, "argv", ["seed_dev_company.py", "--dry-run"])
    monkeypatch.setattr(seed.psycopg, "connect", _refuse_to_connect)

    # Act
    code = seed.main()

    # Assert
    out = capsys.readouterr().out
    assert code == 0
    assert "would insert" in out
    assert "Beispiel IT Services GmbH" in out
    assert f"NEXT_PUBLIC_DEV_COMPANY_ID={EXPECTED_DEV_COMPANY_ID}" in out


def test_run_prints_created_and_the_pasteable_line(
    seed: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Arrange
    monkeypatch.setattr(
        seed.psycopg,
        "connect",
        lambda *_a, **_kw: FakeConnection(row=(EXPECTED_DEV_COMPANY_ID,)),
    )

    # Act
    created = seed.run("postgresql://fake")

    # Assert
    lines = capsys.readouterr().out.splitlines()
    assert created is True
    assert lines == [
        f"dev company created: {EXPECTED_DEV_COMPANY_ID}",
        f"NEXT_PUBLIC_DEV_COMPANY_ID={EXPECTED_DEV_COMPANY_ID}",
    ]


def test_second_run_prints_already_present_and_still_the_line(
    seed: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The id is what the developer came for, whether or not this run created the row."""
    # Arrange
    monkeypatch.setattr(seed.psycopg, "connect", lambda *_a, **_kw: FakeConnection(row=None))

    # Act
    created = seed.run("postgresql://fake")

    # Assert
    out = capsys.readouterr().out
    assert created is False
    assert f"dev company already present: {EXPECTED_DEV_COMPANY_ID}" in out
    assert out.rstrip().endswith(f"NEXT_PUBLIC_DEV_COMPANY_ID={EXPECTED_DEV_COMPANY_ID}")


def test_the_paste_line_names_the_variable_env_example_documents(seed: ModuleType) -> None:
    """If the web app's variable is ever renamed, this catches the script printing the old."""
    assert f"{seed.PASTE_VAR}=" in ENV_EXAMPLE.read_text(encoding="utf-8")
    assert seed.paste_line() == f"{seed.PASTE_VAR}={EXPECTED_DEV_COMPANY_ID}"


def test_a_database_error_is_one_line_naming_the_fix(
    seed: ModuleType,
    not_production: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Never a traceback: `migrate.py`'s contract, kept here."""
    # Arrange
    monkeypatch.setattr(sys, "argv", ["seed_dev_company.py", "--dsn", "postgresql://down"])
    monkeypatch.setattr(seed.psycopg, "connect", _refuse_to_connect)

    # Act
    code = seed.main()

    # Assert
    err = capsys.readouterr().err
    assert code == 1
    assert err.startswith("database error:")
    assert "make migrate" in err
    assert "Traceback" not in err


def _refuse_to_connect(*_args: object, **_kwargs: object) -> FakeConnection:
    raise psycopg.OperationalError("connection refused (fake)")
