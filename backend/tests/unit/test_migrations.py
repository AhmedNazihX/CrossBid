"""S0.2.1 — the migration runner, and the schema's agreement with the contracts.

Every test here is offline. The migration SQL is parsed as text rather than applied, and the
runner's logic is exercised against a temporary directory, so nothing needs a database. The
one test that needs a real Postgres is marked `live`.

The parity test is the reason this file exists. Enum columns are `text` with a check
constraint, and those value lists must stay identical to the Pydantic StrEnums in
`crossbid/models/`. Nothing else would catch a divergence: adding a value to a StrEnum and
forgetting the migration produces a clean type check, a green test run, and then an
`IntegrityError` in production the first time a graph node writes the new value.
"""

from __future__ import annotations

import enum
import hashlib
import re
from pathlib import Path

import pytest

import scripts.migrate as migrate
from crossbid.models import (
    BidStatus,
    Checkability,
    CompanyProfile,
    Decision,
    DocumentKind,
    LegalForm,
    Provider,
    RequirementCategory,
    RequirementKind,
    RequirementSource,
    RequirementStage,
    ReviewerStatus,
    RowStatus,
    Tone,
)
from crossbid.models.company import COUNTRY_PATTERN
from crossbid.readmodel.documents import DocumentStatus

MIGRATIONS_DIR = Path(migrate.__file__).resolve().parent.parent / "migrations"
INIT_SQL = MIGRATIONS_DIR / "0001_init.sql"
"""Read by the tests about 0001's own shape (tables, indexes, column types)."""

# Constraint name -> the StrEnum whose values it must mirror exactly.
CONSTRAINT_ENUMS: dict[str, type[enum.Enum]] = {
    "companies_legal_form_check": LegalForm,
    "companies_tone_check": Tone,
    "companies_active_provider_check": Provider,
    "provider_keys_provider_check": Provider,
    "documents_kind_check": DocumentKind,
    "bids_status_check": BidStatus,
    "requirements_category_check": RequirementCategory,
    "requirements_kind_check": RequirementKind,
    "requirements_stage_check": RequirementStage,
    "requirements_checkable_check": Checkability,
    "requirements_source_check": RequirementSource,  # 0005 (S2.5.1)
    "matrix_rows_status_check": RowStatus,
    "matrix_rows_reviewer_status_check": ReviewerStatus,
    "matrix_rows_agent_status_check": RowStatus,  # 0009 (H24): the agent's own verdict
    "reviews_decision_check": Decision,
    "bids_decision_check": Decision,  # 0006 (S3.4.2): the reviewer's own final call
    "documents_status_check": DocumentStatus,  # 0002 (S2.2.3)
}


REGEX_CHECK = re.compile(r"check\s*\(\s*(\w+)\s*~\s*'([^']+)'\s*\)")
"""Column-level `check (col ~ 'regex')` constraints, which the enum parity above cannot see."""


def _sql() -> str:
    """Every migration, in order, as one text: a constraint may be added by any of them.

    Later files add enum columns too (0002's `documents.status`), and a parity guard that
    scanned only 0001 would let those drift unnoticed -- which is what happened to the first
    draft of this test when S2.2.3 landed.
    """
    return "\n".join(m.sql for m in migrate.discover(MIGRATIONS_DIR))


def _sql_without_comments() -> str:
    """The SQL with `--` comments stripped.

    Tests about column *types* must not read the file's own prose: the header explains why
    `varchar` is avoided, which would otherwise trip a naive substring check.
    """
    return "\n".join(line.split("--", 1)[0] for line in _sql().splitlines())


def _constraint_values(sql: str, constraint: str) -> set[str]:
    """The quoted values inside `constraint <name> check (... in (...))`."""
    pattern = re.compile(
        rf"constraint\s+{re.escape(constraint)}\s+check\s*\((.*?)\)\s*\)",
        re.IGNORECASE | re.DOTALL,
    )
    matches = pattern.findall(sql)
    if not matches:
        raise AssertionError(f"constraint {constraint} not found in any migration")
    # The *last* definition wins: a later migration re-adds a constraint to change its list
    # (0004 did, for the design-system vocabulary), and the files are concatenated in order.
    return set(re.findall(r"'([^']+)'", matches[-1]))


# --------------------------------------------------------------- schema / contract parity


@pytest.mark.parametrize("constraint", sorted(CONSTRAINT_ENUMS))
def test_check_constraint_matches_its_pydantic_enum(constraint: str) -> None:
    """A value the model allows and the database rejects is an insert error in production."""
    # Arrange
    expected = {member.value for member in CONSTRAINT_ENUMS[constraint]}

    # Act
    actual = _constraint_values(_sql(), constraint)

    # Assert
    assert actual == expected, (
        f"{constraint} allows {sorted(actual)} but the enum defines {sorted(expected)}; "
        "add a new migration rather than editing an applied one"
    )


def test_every_enum_backed_column_is_covered_by_a_parity_check() -> None:
    """Guards the guard: a new `text ... in (...)` column must be added to CONSTRAINT_ENUMS.

    Without this, someone adds an enum column, no parity test exists for it, and the drift
    this file is meant to prevent goes unnoticed.
    """
    # Act
    declared = set(re.findall(r"constraint\s+(\w+_check)\s+check\s*\([^)]*\sin\s*\(", _sql()))

    # Assert
    assert declared <= set(CONSTRAINT_ENUMS), (
        "these check constraints use an `in (...)` value list but have no parity test: "
        f"{sorted(declared - set(CONSTRAINT_ENUMS))}"
    )


def test_a_regex_checked_column_is_mirrored_in_the_field_that_writes_it() -> None:
    """A pattern the model allows and the column refuses is a 500, not a 422.

    `companies.country` is the one column whose check is a regex rather than a value list, so
    the enum parity above does not cover it: `CompanyProfile.country` bounded only the length,
    `'DE'` passed Pydantic, and Postgres answered with a `CheckViolation` that
    `PUT /companies/me` had no handler for. The two texts are compared rather than the two
    behaviours because the migration is applied by a script that never imports the package.
    """
    # Arrange
    declared = CompanyProfile.model_json_schema()["properties"]["country"]["pattern"]

    # Act
    checked = dict(REGEX_CHECK.findall(_sql()))

    # Assert
    assert declared == COUNTRY_PATTERN
    assert checked == {"country": COUNTRY_PATTERN}, (
        "a column is constrained by a regex that no Pydantic field mirrors: "
        f"{sorted(set(checked) - {'country'})}"
    )


def test_the_embedding_dimension_matches_the_configured_model() -> None:
    """1536 is `text-embedding-3-small` (ADR-0004), and it is baked into the column type.

    Changing the embedding model means a migration and re-embedding the whole corpus, so the
    number is worth pinning where a reviewer will see it.
    """
    # Act
    dimensions = set(re.findall(r"vector\((\d+)\)", _sql()))

    # Assert
    assert dimensions == {"1536"}
    # Under pgvector's 2000-dimension index limit, which is what makes HNSW possible here.
    assert all(int(d) < 2000 for d in dimensions)


def test_both_chunk_tables_have_an_hnsw_index() -> None:
    """Cosine distance, and an index at all — the 1536-dim choice exists to allow one."""
    # Act
    sql = _sql()

    # Assert
    for table in ("company_chunks", "tender_chunks"):
        assert f"on {table} using hnsw (embedding vector_cosine_ops)" in sql


def test_every_tenant_scoped_table_carries_a_not_null_company_id() -> None:
    """Tenant isolation is application-level, so `company_id` is the filter every query needs.

    Keeping it NOT NULL on every scoped table is also what makes adding RLS later additive
    rather than a rewrite (ADR-0009).
    """
    # Arrange
    scoped = (
        "provider_keys",
        "bids",
        "documents",
        "company_chunks",
        "tender_chunks",
        "requirements",
        "matrix_rows",
        "reviews",
        "feedback",
        "llm_usage",
    )
    sql = _sql()

    # Act / Assert
    for table in scoped:
        body = re.search(rf"create table if not exists {table} \((.*?)\n\);", sql, re.DOTALL)
        assert body is not None, f"table {table} not found"
        assert re.search(r"company_id\s+uuid not null", body.group(1)), (
            f"{table} must carry a NOT NULL company_id"
        )


def test_timestamps_are_timezone_aware() -> None:
    """A bid deadline without a zone is a bug waiting to happen across EU time zones."""
    assert " timestamp " not in _sql_without_comments().replace("timestamptz", "")


def test_no_varchar_columns() -> None:
    """`text` everywhere: same performance, no artificial limit to migrate away from later."""
    assert "varchar" not in _sql_without_comments().lower()


def test_money_is_numeric_not_float() -> None:
    """Cost accounting must be exact; float would drift."""
    assert re.search(r"cost_usd\s+numeric", _sql_without_comments())


def test_the_supported_row_invariant_is_enforced_in_the_database_too() -> None:
    """The Pydantic model enforces it, but a direct SQL write would bypass that.

    "Every cell carries a citation or is marked partially supported" is the product's central
    promise, so it is worth having in both places. 0004 renamed the constraint with the
    vocabulary; the new definition must guard `supported`, and the old name must be dropped.
    """
    sql = _sql()
    definition = sql[sql.rindex("matrix_rows_supported_needs_evidence_check check") :]
    assert "status <> 'supported'" in definition
    assert "drop constraint if exists matrix_rows_met_needs_evidence_check" in sql


def test_the_espd_citation_invariant_is_enforced_in_the_database_too() -> None:
    """S2.5.1: `page is null` exactly for ESPD rows, in the column pair as well as Pydantic.

    `Requirement` refuses the two bad shapes, but a direct SQL write would bypass it, and
    both are citation bugs: an extracted quote with no page cites nothing a reviewer can
    open, and an ESPD criterion with a page cites a page that does not exist.
    """
    # Act
    sql = _sql_without_comments()

    # Assert
    assert "requirements_page_matches_source_check" in sql
    assert "(source = 'espd_request') = (page is null)" in sql


def test_the_override_reason_invariant_is_enforced_in_the_database_too() -> None:
    assert "matrix_rows_override_needs_reason_check" in _sql()


# --------------------------------------------------------------- the runner


def test_discovery_finds_the_real_migration() -> None:
    # Act
    found = migrate.discover(MIGRATIONS_DIR)

    # Assert
    assert [m.version for m in found] == sorted(m.version for m in found)
    assert found[0].version == "0001"
    assert found[0].name == "init"


def test_discovery_is_ordered_numerically(tmp_path: Path) -> None:
    """Lexicographic order would put 0010 before 0009 once the numbers grow."""
    # Arrange
    for name in ("0002_b.sql", "0010_c.sql", "0001_a.sql", "0009_d.sql"):
        (tmp_path / name).write_text("select 1;", encoding="utf-8")

    # Act
    versions = [m.version for m in migrate.discover(tmp_path)]

    # Assert
    assert versions == ["0001", "0002", "0009", "0010"]


def test_a_badly_named_file_is_an_error_not_a_silent_skip(tmp_path: Path) -> None:
    """A skipped migration diverges the schema quietly, which is the worst failure mode."""
    # Arrange
    (tmp_path / "1_init.sql").write_text("select 1;", encoding="utf-8")

    # Act / Assert
    with pytest.raises(migrate.MigrationError, match="does not match"):
        migrate.discover(tmp_path)


def test_duplicate_versions_are_rejected(tmp_path: Path) -> None:
    """Two files claiming 0002 would apply in an order nobody chose."""
    # Arrange
    (tmp_path / "0002_alpha.sql").write_text("select 1;", encoding="utf-8")
    (tmp_path / "0002_beta.sql").write_text("select 2;", encoding="utf-8")

    # Act / Assert
    with pytest.raises(migrate.MigrationError, match="duplicate migration version"):
        migrate.discover(tmp_path)


def test_a_missing_directory_is_an_error() -> None:
    with pytest.raises(migrate.MigrationError, match="no migrations directory"):
        migrate.discover(Path("/nonexistent/migrations"))


def test_checksum_is_the_sha256_of_the_file(tmp_path: Path) -> None:
    # Arrange
    body = "create table t (id int);\n"
    (tmp_path / "0001_t.sql").write_text(body, encoding="utf-8")

    # Act
    migration = migrate.discover(tmp_path)[0]

    # Assert
    assert migration.checksum == hashlib.sha256(body.encode()).hexdigest()


def test_editing_an_applied_migration_is_refused(tmp_path: Path) -> None:
    """The database reflects what the file said when it ran; an edit cannot reconcile it."""
    # Arrange
    (tmp_path / "0001_t.sql").write_text("select 1;", encoding="utf-8")
    migrations = migrate.discover(tmp_path)
    applied = {"0001": "a-checksum-from-when-it-was-different"}

    # Act / Assert
    with pytest.raises(migrate.MigrationError, match="contents have changed"):
        migrate.check_for_tampering(migrations, applied)


def test_an_unchanged_applied_migration_passes(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / "0001_t.sql").write_text("select 1;", encoding="utf-8")
    migrations = migrate.discover(tmp_path)

    # Act / Assert — no exception
    migrate.check_for_tampering(migrations, {"0001": migrations[0].checksum})


def test_a_migration_recorded_but_missing_on_disk_is_refused(tmp_path: Path) -> None:
    """Usually means the wrong database, which is worth stopping for."""
    # Arrange
    (tmp_path / "0001_t.sql").write_text("select 1;", encoding="utf-8")
    migrations = migrate.discover(tmp_path)
    applied = {"0001": migrations[0].checksum, "0002": "orphan"}

    # Act / Assert
    with pytest.raises(migrate.MigrationError, match="no longer exist on disk"):
        migrate.check_for_tampering(migrations, applied)


def test_resolve_dsn_prefers_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    monkeypatch.setenv("DATABASE_URL", "postgresql://someone@example:5432/db")

    # Act / Assert
    assert migrate.resolve_dsn() == "postgresql://someone@example:5432/db"


def test_resolve_dsn_fails_with_actionable_guidance(monkeypatch: pytest.MonkeyPatch) -> None:
    """A developer reading the failure should know exactly what to do next."""
    # Arrange
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(migrate, "BACKEND", Path("/nonexistent/backend"))

    # Act / Assert
    with pytest.raises(migrate.MigrationError, match=re.escape("infra/.env.example")):
        migrate.resolve_dsn()


def test_the_advisory_lock_key_is_stable() -> None:
    """Changing this value would let two runners interleave against one database.

    Pinned literally rather than recomputed, so a well-meaning edit fails the test.
    """
    assert migrate.ADVISORY_LOCK_KEY == 0x43524F5353424944
    # Must fit a signed 64-bit integer, which is what pg_advisory_lock takes.
    assert -(2**63) <= migrate.ADVISORY_LOCK_KEY < 2**63


# --------------------------------------------------------------- live


@pytest.mark.live
@pytest.mark.database
def test_migrations_are_idempotent_against_a_real_database() -> None:
    """S0.2.1's acceptance criterion: run twice, apply once, record the version."""
    # Arrange
    dsn = migrate.resolve_dsn()

    # Act
    first = migrate.run(dsn)
    second = migrate.run(dsn)

    # Assert
    assert second == 0, "a second run must apply nothing"
    assert first >= 0


def test_a_deadline_offset_cannot_exist_without_its_deadline() -> None:
    """0007's pair rule, in the database as well as in the request model.

    An offset alone describes nothing and would print as a time zone on a bid that has no
    date. The API refuses a naive timestamp for the mirror-image reason, so both halves of
    the rule are enforced at both ends.
    """
    sql = _sql()

    assert "bids_deadline_offset_needs_a_deadline_check" in sql
    definition = sql[sql.rindex("bids_deadline_offset_needs_a_deadline_check check") :]
    assert "deadline is not null" in definition[: definition.index(")") + 1]


def test_the_deadline_offset_is_stored_as_an_offset_and_not_as_a_zone_name() -> None:
    """Neither a notice nor TED publishes an IANA zone, so a zone name would be an inference
    — and one whose answer changes twice a year. 0007 keeps the offset the buyer published."""
    sql = _sql()

    assert "deadline_utc_offset_minutes smallint" in sql
    assert "bids_deadline_offset_range_check" in sql
