"""S2.4.1 — the `companies` read model: the statements, the tenant, and the split.

Offline, over `conftest`'s recording connection: what is asserted is the statement text and
the bound parameters Postgres would actually receive. That matters
twice here.

* **Scope.** The API connects as a `BYPASSRLS` role (ADR-0009), so `id = %(company_id)s`
  written into each statement is the only boundary between two companies. The tenant key is
  the primary key rather than a `company_id` column, because the company *is* the row — the
  parameter is still named `company_id`, so the predicate reads the same everywhere. The
  insert S2.4.3 added has no rows to filter, so it is held to the other half of the rule:
  the tenant has to be a bound value of the row it creates, exactly as in `documents.py`.
* **The column/jsonb split.** Which half of `CompanyProfile` lands in a real column and which
  in `profile jsonb` is a decision a reader must not have to guess, so the two field tuples
  are asserted to partition the model exactly. Adding a field to `CompanyProfile` without
  deciding where it lives fails here rather than silently vanishing on the next save.
"""

from __future__ import annotations

import inspect
import re
import uuid
from typing import Any

import pytest
from psycopg.types.json import Jsonb

from crossbid.models import CompanyProfile
from crossbid.readmodel.companies import (
    COLUMN_FIELDS,
    INSERT_COMPANY_SQL,
    JSONB_FIELDS,
    SCOPED_STATEMENTS,
    SELECT_COMPANY_SQL,
    TENANT_PARAMETER,
    UPDATE_COMPANY_SQL,
    CompaniesReadModel,
    CompanyReadModelError,
    profile_document,
)
from tests.conftest import COMPANY_PROFILE, DEMO_COMPANY_ID, FakeConnectionSource, company_row

COMPANY_ID = DEMO_COMPANY_ID
OTHER_COMPANY_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
OWNER_USER_ID = uuid.UUID("55555555-5555-4555-8555-555555555555")

COMPANY_COLUMNS = "id, name, country, legal_form, language, tone, profile"
"""What both statements must select and return — an expectation about the SQL, so it lives
with the assertions rather than in the read model, which had no use for it.

The statements write the list out twice rather than splicing this in: psycopg types `execute`
on `LiteralString`, and while an f-string of `LiteralString` parts is still one (PEP 675),
ruff's S608 cannot see that and flags every f-string that looks like SQL. Two literals and
one test are cheaper than two `noqa`s on the module where a run-time-assembled query would be
an unscoped `where`."""

PROFILE = COMPANY_PROFILE
"""The demo bidder, and the row `company_row()` builds from it, both defined in
`conftest.py`: `test_companies_router.py` asserts against the same row through the HTTP
layer, and a profile that differed between the two would make the pair prove less."""


def read_model(
    rows: tuple[dict[str, Any], ...] = (),
) -> tuple[CompaniesReadModel, FakeConnectionSource]:
    source = FakeConnectionSource(rows)
    return CompaniesReadModel(source), source


# ----------------------------------------------------------------- statements, as text


def _one_line(sql: str) -> str:
    """SQL whitespace is insignificant; the statements wrap where the line length says so."""
    return " ".join(sql.split())


WHERE_SCOPED_STATEMENTS = tuple(
    sql for sql in SCOPED_STATEMENTS if sql is not INSERT_COMPANY_SQL
)
"""Every statement that filters rows. The insert is the one that creates the row instead."""


@pytest.mark.parametrize("sql", WHERE_SCOPED_STATEMENTS, ids=lambda sql: sql.split()[0])
def test_every_filtering_statement_carries_the_tenant_scope_in_its_own_text(sql: str) -> None:
    """The only line between two companies (ADR-0009); nothing at run time may add it."""
    assert TENANT_PARAMETER in sql
    assert "where" in sql


def test_the_insert_binds_the_tenant_into_the_row_it_creates() -> None:
    """No `where` to scope, so the scope is the `company_id` value itself (S2.4.3)."""
    match = re.search(
        r"insert into companies \((?P<columns>[^)]*)\) values \((?P<values>.*?)\) on conflict",
        _one_line(INSERT_COMPANY_SQL),
    )
    assert match is not None, INSERT_COMPANY_SQL
    columns = [name.strip() for name in match["columns"].split(",")]
    values = [value.strip() for value in match["values"].split(",")]
    assert columns[0] == "id"
    assert values[0] == "%(company_id)s"
    assert "%(owner_user_id)s" in values, "a company arrives with its owner or not at all"


@pytest.mark.parametrize("sql", SCOPED_STATEMENTS, ids=lambda sql: sql.split()[0])
def test_every_statement_returns_the_same_column_list(sql: str) -> None:
    """The list is written out in each statement, so this is what stops the two drifting.

    `_profile` depends on it: it applies the five scalar columns over the jsonb, so a
    `returning` that had lost one of them would raise `CompanyReadModelError` on a perfectly
    good row — and only on the save path, which is the worse half to find it on.
    """
    assert COMPANY_COLUMNS in _one_line(sql)


def test_the_statements_are_the_three_the_module_defines() -> None:
    assert SCOPED_STATEMENTS == (SELECT_COMPANY_SQL, UPDATE_COMPANY_SQL, INSERT_COMPANY_SQL)


def test_the_column_list_is_the_id_the_scalar_columns_and_the_jsonb() -> None:
    columns = tuple(column.strip() for column in COMPANY_COLUMNS.split(","))
    assert columns == ("id", *COLUMN_FIELDS, "profile")


# ------------------------------------------------------------------ the split, asserted


def test_the_two_field_groups_partition_the_profile_with_no_overlap() -> None:
    """Where every fact lives is decided here, once, and a new field must join a group."""
    assert set(COLUMN_FIELDS).isdisjoint(JSONB_FIELDS)
    assert set(COLUMN_FIELDS) | set(JSONB_FIELDS) == set(CompanyProfile.model_fields)


def test_the_jsonb_document_holds_the_non_column_fields_only() -> None:
    """A scalar copied into the jsonb would be a second source of truth that can drift."""
    document = profile_document(PROFILE)

    assert set(document) == set(JSONB_FIELDS)
    assert "name" not in document and "country" not in document


def test_the_jsonb_document_is_json_and_not_python_objects() -> None:
    """`profile` is a jsonb column: dates go in as ISO strings, enums as their values."""
    document = profile_document(PROFILE)

    assert document["certificates"][0]["expires_on"] == "2026-05-01"
    assert document["turnover"][0] == {
        "year": 2025,
        "amount": 7_400_000.0,
        "currency": "EUR",
        "field_of_activity": "IT",
    }


# -------------------------------------------------------------------------------- get


@pytest.mark.anyio
async def test_get_binds_the_calling_company_and_nothing_else() -> None:
    # Arrange
    records, source = read_model((company_row(),))

    # Act
    await records.get(company_id=COMPANY_ID)

    # Assert
    assert source.only.sql == SELECT_COMPANY_SQL
    assert source.only.params == {"company_id": COMPANY_ID}


@pytest.mark.anyio
async def test_get_reassembles_the_profile_from_the_columns_and_the_jsonb() -> None:
    # Arrange
    records, _ = read_model((company_row(),))

    # Act
    found = await records.get(company_id=COMPANY_ID)

    # Assert
    assert found == PROFILE


@pytest.mark.anyio
async def test_get_returns_none_when_this_company_has_no_row() -> None:
    """`AUTH_MODE=dev` lets a header name a UUID with no row; the router answers 404."""
    records, _ = read_model(())

    assert await records.get(company_id=OTHER_COMPANY_ID) is None


@pytest.mark.anyio
async def test_a_seeded_row_with_an_empty_profile_reads_back_on_the_defaults() -> None:
    """`scripts/seed_dev_company.py` writes `profile = '{}'`: the form has not run yet."""
    # Arrange
    records, _ = read_model((company_row(profile={}),))

    # Act
    found = await records.get(company_id=COMPANY_ID)

    # Assert
    assert found is not None
    assert found.turnover == () and found.certificates == ()
    assert found.registration_number is None and found.staff_fte is None
    assert found.name == PROFILE.name


@pytest.mark.anyio
async def test_a_row_the_model_cannot_validate_fails_loudly_and_names_the_table() -> None:
    """The table is external data: a hand-edited jsonb must not become a half-filled profile."""
    # Arrange
    records, _ = read_model((company_row(profile={"staff_fte": -1}),))

    # Act / Assert
    with pytest.raises(CompanyReadModelError, match="companies"):
        await records.get(company_id=COMPANY_ID)


@pytest.mark.anyio
async def test_a_jsonb_key_the_profile_does_not_know_is_a_loud_failure_too() -> None:
    """`CompanyProfile` forbids extras, so drift surfaces here and not as a lost fact."""
    records, _ = read_model((company_row(profile={"headcount": 12}),))

    with pytest.raises(CompanyReadModelError):
        await records.get(company_id=COMPANY_ID)


# ------------------------------------------------------------------------------- save


@pytest.mark.anyio
async def test_save_writes_the_scalars_to_columns_and_the_rest_to_the_jsonb() -> None:
    # Arrange
    records, source = read_model((company_row(),))

    # Act
    await records.save(company_id=COMPANY_ID, profile=PROFILE)

    # Assert
    assert source.only.sql == UPDATE_COMPANY_SQL
    params = source.only.params
    assert params["company_id"] == COMPANY_ID
    assert params["name"] == PROFILE.name
    assert params["country"] == "de"
    assert params["legal_form"] == "gmbh"
    assert params["tone"] == "plain"
    document = params["profile"]
    assert isinstance(document, Jsonb)
    assert document.obj == profile_document(PROFILE)


@pytest.mark.anyio
async def test_save_returns_the_row_the_database_handed_back() -> None:
    """Re-validated on the way out, so the caller answers with what the row says."""
    records, _ = read_model((company_row(),))

    assert await records.save(company_id=COMPANY_ID, profile=PROFILE) == PROFILE


@pytest.mark.anyio
async def test_save_returns_none_when_the_update_touched_no_row() -> None:
    """Another company's id and an unseeded one are the same answer: the router 404s."""
    records, _ = read_model(())

    assert await records.save(company_id=OTHER_COMPANY_ID, profile=PROFILE) is None


# ----------------------------------------------------------------------------- create


@pytest.mark.anyio
async def test_create_binds_both_ids_and_the_same_split_save_uses() -> None:
    """The seed must not grow a second opinion about where a fact lives (S2.4.3)."""
    # Arrange
    records, source = read_model((company_row(),))

    # Act
    await records.create(company_id=COMPANY_ID, owner_user_id=OWNER_USER_ID, profile=PROFILE)

    # Assert
    assert source.only.sql == INSERT_COMPANY_SQL
    params = source.only.params
    assert params["company_id"] == COMPANY_ID
    assert params["owner_user_id"] == OWNER_USER_ID
    assert params["name"] == PROFILE.name
    assert params["legal_form"] == "gmbh"
    document = params["profile"]
    assert isinstance(document, Jsonb)
    assert document.obj == profile_document(PROFILE)


@pytest.mark.anyio
async def test_create_returns_the_row_it_inserted() -> None:
    records, _ = read_model((company_row(),))

    created = await records.create(
        company_id=COMPANY_ID, owner_user_id=OWNER_USER_ID, profile=PROFILE
    )

    assert created == PROFILE


@pytest.mark.anyio
async def test_create_returns_none_when_the_company_is_already_there() -> None:
    """`on conflict do nothing` returns no row, which is how a second seed is detected."""
    records, _ = read_model(())

    created = await records.create(
        company_id=COMPANY_ID, owner_user_id=OWNER_USER_ID, profile=PROFILE
    )

    assert created is None


def test_create_leaves_active_provider_to_the_column_default() -> None:
    """The seed has no opinion about the provider, so it must not restate the default."""
    assert "active_provider" not in INSERT_COMPANY_SQL


@pytest.mark.parametrize("method", ["get", "save", "create"])
def test_the_scope_argument_is_keyword_only_with_no_default(method: str) -> None:
    """A call that forgets the company must not type-check and must not run."""
    parameter = inspect.signature(getattr(CompaniesReadModel, method)).parameters["company_id"]

    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is inspect.Parameter.empty
