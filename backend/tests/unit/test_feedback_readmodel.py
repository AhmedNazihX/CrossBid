"""S4.6.3 — the `feedback` read model: the statements, the tenant, and the log.

Offline, over `conftest`'s recording connection: what is asserted is the statement text and
the parameters Postgres would actually receive. Three things are worth that trouble here.

* **Scope.** The API connects as a `BYPASSRLS` role (ADR-0009), so the `company_id`
  predicate written into each statement is the only boundary between two companies. This
  module's insert is the interesting case: it has a `where` to be scoped by *and* a row to
  create, so it is held to both halves of the rule — the predicate is in its text, and the
  `company_id` it writes comes from the bid row that predicate proved rather than from the
  caller's parameter.
* **The row check.** A bidder must not be able to rate another company's matrix row, and
  nothing in the router can enforce that: the `exists` subquery is the whole mechanism, so
  its own scope is asserted rather than assumed.
* **The vocabulary.** `rating` is an enum column like any other, except that its values are
  numbers — which is why `test_migrations.py`'s parity guard, scanning for `text ... in
  (...)` constraints, cannot see it. The parity is asserted here instead.
"""

from __future__ import annotations

import inspect
import re
from datetime import UTC, datetime
from typing import Any

import pytest

from crossbid.readmodel.feedback import (
    INSERT_FEEDBACK,
    SCOPED_STATEMENTS,
    SELECT_LATEST_FEEDBACK,
    TENANT_PARAMETER,
    FeedbackRecord,
    Rating,
    fetch_feedback,
    record_feedback,
)
from tests.conftest import BACKEND_DIR, BID_ID, COMPANY_ID, FakeConnectionSource

MATRIX_ROW_ID = "77777777-7777-4777-8777-777777777777"
CREATED_AT = datetime(2026, 9, 14, 10, 30, tzinfo=UTC)
COMMENT = "Die Bescheinigung deckt das ab — siehe Seite 2."

INIT_SQL = (BACKEND_DIR / "migrations" / "0001_init.sql").read_text(encoding="utf-8")
"""0001 declared `feedback` and no later migration has touched it, so the table this module
writes to is described in that one file."""

FEEDBACK_TABLE_SQL = INIT_SQL[INIT_SQL.index("create table if not exists feedback") :]


def stored_row(**overrides: Any) -> dict[str, Any]:
    """One `feedback` row as `dict_row` hands it back."""
    row: dict[str, Any] = {
        "id": 7,
        "bid_id": BID_ID,
        "matrix_row_id": MATRIX_ROW_ID,
        "rating": 1,
        "comment": COMMENT,
        "created_at": CREATED_AT,
    }
    return row | overrides


def _one_line(sql: str) -> str:
    """SQL whitespace is insignificant; the statements wrap where the line length says so."""
    return " ".join(sql.split())


# ------------------------------------------------------------------ statements, as text


@pytest.mark.parametrize("sql", SCOPED_STATEMENTS, ids=lambda sql: sql.split()[0])
def test_every_statement_carries_the_tenant_scope_in_its_own_text(sql: str) -> None:
    """The only line between two companies (ADR-0009); nothing at run time may add it."""
    assert TENANT_PARAMETER in sql
    assert "where" in sql


def test_the_statements_are_the_two_the_module_defines() -> None:
    assert SCOPED_STATEMENTS == (INSERT_FEEDBACK, SELECT_LATEST_FEEDBACK)


def test_the_insert_writes_the_company_from_the_bid_row_and_not_from_the_parameter() -> None:
    """An `insert ... values` would bind the tenant blind and let the row land on any bid.

    Selecting `b.company_id` instead means the tenant written is the one the `where` has
    just proved, so the scope and the stored value cannot disagree with each other.
    """
    statement = _one_line(INSERT_FEEDBACK)
    columns, rest = statement.split(") select ", maxsplit=1)

    assert columns.startswith("insert into feedback (company_id, bid_id, matrix_row_id,")
    assert rest.startswith("b.company_id, b.id,")
    assert "from bids b where b.company_id = %(company_id)s and b.id = %(bid_id)s" in rest


def test_a_named_matrix_row_must_belong_to_the_same_bid_and_the_same_company() -> None:
    """The whole defence against rating somebody else's row: there is no other check."""
    exists = _one_line(INSERT_FEEDBACK).split("or exists (", maxsplit=1)[1]

    assert "m.id = %(matrix_row_id)s::uuid" in exists
    assert "m.company_id = %(company_id)s" in exists
    assert "m.bid_id = b.id" in exists


def test_a_rating_with_no_row_is_allowed_because_the_column_is_nullable() -> None:
    """0001 made `matrix_row_id` nullable, and the null branch is a bid-level rating.

    The `::uuid` casts are load-bearing rather than decorative: psycopg sends a `str` as
    `unknown`, and `%(matrix_row_id)s is null` on an unknown is a type Postgres refuses to
    resolve.
    """
    assert "%(matrix_row_id)s::uuid is null" in _one_line(INSERT_FEEDBACK)
    assert "matrix_row_id uuid references matrix_rows" in _one_line(FEEDBACK_TABLE_SQL)
    assert "matrix_row_id uuid not null" not in _one_line(FEEDBACK_TABLE_SQL)


def test_the_read_answers_the_latest_rating_of_each_target() -> None:
    """Re-rating a row must not show the bidder two answers to the same question."""
    statement = _one_line(SELECT_LATEST_FEEDBACK)

    assert statement.startswith("select distinct on (matrix_row_id)")
    assert "order by matrix_row_id, created_at desc, id desc" in statement


def test_the_rating_values_match_the_check_constraint_that_stores_them() -> None:
    """A value the enum allows and the column rejects is an `IntegrityError` on a thumb.

    `test_migrations.py` makes this check for every `text` enum column by scanning for
    `constraint <name> check (... in (...))`. `feedback.rating` is a `smallint` with an
    inline check, which that scan cannot see, so the parity is asserted here.
    """
    # Act
    allowed = re.search(r"rating\s+smallint not null check \(rating in \(([^)]*)\)\)", INIT_SQL)

    # Assert
    assert allowed is not None, "the rating check constraint moved; the enum must follow"
    assert {int(value) for value in allowed.group(1).split(",")} == {
        member.value for member in Rating
    }


# ------------------------------------------------------------------------------- write


@pytest.mark.anyio
async def test_recording_a_rating_binds_the_company_the_bid_and_the_row() -> None:
    # Arrange
    source = FakeConnectionSource((stored_row(),))

    # Act
    await record_feedback(
        source,
        company_id=COMPANY_ID,
        bid_id=BID_ID,
        rating=Rating.UP,
        matrix_row_id=MATRIX_ROW_ID,
        comment=COMMENT,
    )

    # Assert
    assert source.only.sql == INSERT_FEEDBACK
    assert source.only.params == {
        "company_id": COMPANY_ID,
        "bid_id": BID_ID,
        "matrix_row_id": MATRIX_ROW_ID,
        "rating": 1,
        "comment": COMMENT,
    }


@pytest.mark.anyio
async def test_a_thumb_down_is_bound_as_the_column_stores_it() -> None:
    """`-1`, not the member: an `IntEnum` is an `int`, but the binding says so out loud."""
    # Arrange
    source = FakeConnectionSource((stored_row(rating=-1),))

    # Act
    await record_feedback(source, company_id=COMPANY_ID, bid_id=BID_ID, rating=Rating.DOWN)

    # Assert
    assert source.only.params["rating"] == -1
    assert source.only.params["matrix_row_id"] is None
    assert source.only.params["comment"] is None


@pytest.mark.anyio
async def test_recording_a_rating_answers_the_row_the_database_wrote() -> None:
    # Arrange
    source = FakeConnectionSource((stored_row(),))

    # Act
    stored = await record_feedback(
        source,
        company_id=COMPANY_ID,
        bid_id=BID_ID,
        rating=Rating.UP,
        matrix_row_id=MATRIX_ROW_ID,
        comment=COMMENT,
    )

    # Assert
    assert stored == FeedbackRecord(
        id=7,
        bid_id=BID_ID,
        matrix_row_id=MATRIX_ROW_ID,
        rating=Rating.UP,
        comment=COMMENT,
        created_at=CREATED_AT,
    )


@pytest.mark.anyio
async def test_recording_answers_none_when_the_insert_found_nothing_to_rate() -> None:
    """Another company's bid and a row that is not this bid's are the same empty `select`."""
    source = FakeConnectionSource(())

    stored = await record_feedback(
        source, company_id=COMPANY_ID, bid_id=BID_ID, rating=Rating.UP
    )

    assert stored is None


@pytest.mark.anyio
async def test_a_bid_level_rating_reads_back_with_no_row_id() -> None:
    """The null target is what a chat answer will be (F3.5), so it must survive the trip."""
    source = FakeConnectionSource((stored_row(matrix_row_id=None, comment=None),))

    stored = await record_feedback(
        source, company_id=COMPANY_ID, bid_id=BID_ID, rating=Rating.UP
    )

    assert stored is not None
    assert stored.matrix_row_id is None
    assert stored.comment is None


# -------------------------------------------------------------------------------- read


@pytest.mark.anyio
async def test_fetching_binds_the_calling_company_and_the_bid() -> None:
    # Arrange
    source = FakeConnectionSource((stored_row(),))

    # Act
    await fetch_feedback(source, company_id=COMPANY_ID, bid_id=BID_ID)

    # Assert
    assert source.only.sql == SELECT_LATEST_FEEDBACK
    assert source.only.params == {"company_id": COMPANY_ID, "bid_id": BID_ID}


@pytest.mark.anyio
async def test_fetching_revalidates_every_row_on_the_way_out() -> None:
    # Arrange
    source = FakeConnectionSource((stored_row(), stored_row(id=8, matrix_row_id=None)))

    # Act
    stored = await fetch_feedback(source, company_id=COMPANY_ID, bid_id=BID_ID)

    # Assert
    assert [record.id for record in stored] == [7, 8]
    assert stored[0].matrix_row_id == MATRIX_ROW_ID
    assert stored[1].matrix_row_id is None


@pytest.mark.anyio
async def test_a_bid_nobody_has_rated_is_an_empty_list() -> None:
    source = FakeConnectionSource(())

    assert await fetch_feedback(source, company_id=COMPANY_ID, bid_id=BID_ID) == []


@pytest.mark.anyio
async def test_a_rating_the_contract_refuses_fails_rather_than_reaching_a_screen() -> None:
    """The table is external data: a hand-written `0` has no thumb to render."""
    source = FakeConnectionSource((stored_row(rating=0),))

    with pytest.raises(ValueError, match="rating"):
        await fetch_feedback(source, company_id=COMPANY_ID, bid_id=BID_ID)


@pytest.mark.parametrize("function", [record_feedback, fetch_feedback])
def test_the_scope_argument_is_keyword_only_with_no_default(function: Any) -> None:
    """A call that forgets the company must not type-check and must not run."""
    parameter = inspect.signature(function).parameters["company_id"]

    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is inspect.Parameter.empty
