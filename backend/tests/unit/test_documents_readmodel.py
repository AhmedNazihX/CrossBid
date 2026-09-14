"""S2.2.3 — the `documents` read model: every statement scoped, every transition returned.

Offline. The read model runs over `conftest`'s recording connection, which remembers the
statement text and the bound parameters and answers with scripted rows, so what is asserted
is exactly what Postgres would receive. That matters here because the API connects as a
`BYPASSRLS` role (ADR-0009): the `company_id = %(company_id)s` written into each statement is
the only tenant boundary there is, and asserting it is a security test, not a style test.

The migration parity test lives here rather than in `test_migrations.py` because that file's
guard scans `0001_init.sql` only and this story does not own it. `DocumentStatus` is defined
next to the column it constrains, so the two lists are compared by reading the SQL as text.
"""

from __future__ import annotations

import inspect
import re
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from crossbid.models import DocumentKind
from crossbid.readmodel.documents import (
    DOCUMENT_COLUMNS,
    INSERT_DOCUMENT_SQL,
    LIST_DOCUMENTS_SQL,
    MARK_FAILED_SQL,
    MARK_PARSED_SQL,
    MARK_STATUS_SQL,
    SCOPED_STATEMENTS,
    SELECT_DOCUMENT_SQL,
    SET_FLAGGED_CHUNKS_SQL,
    TENANT_PARAMETER,
    DocumentRecord,
    DocumentsReadModel,
    DocumentStatus,
    ReadModelError,
)
from tests.conftest import FakeConnectionSource

COMPANY_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
OTHER_COMPANY_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
DOCUMENT_ID = uuid.UUID("44444444-4444-4444-8444-444444444444")
FIXED_NOW = datetime(2026, 9, 11, 9, 0, tzinfo=UTC)

MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "0002_documents_status.sql"


def document_row(**overrides: Any) -> dict[str, Any]:
    """One `documents` row as `dict_row` would hand it back, every column present."""
    row: dict[str, Any] = {
        "id": DOCUMENT_ID,
        "company_id": COMPANY_ID,
        "bid_id": None,
        "kind": "company_evidence",
        "name": "Nachweis ISO 27001 (2026).pdf",
        "storage_path": f"{COMPANY_ID}/{DOCUMENT_ID}/Nachweis_ISO_27001_2026_.pdf",
        "status": "uploaded",
        "failure_reason": None,
        "pages": 0,
        "unread_pages": [],
        "flagged_chunks": [],
        "created_at": FIXED_NOW,
        "updated_at": FIXED_NOW,
    }
    return row | overrides


def read_model(
    rows: Sequence[Mapping[str, Any]] = (),
) -> tuple[DocumentsReadModel, FakeConnectionSource]:
    source = FakeConnectionSource(rows)
    return DocumentsReadModel(source), source


# ----------------------------------------------------------------- statements, as text


WHERE_SCOPED_STATEMENTS = tuple(
    sql for sql in SCOPED_STATEMENTS if sql is not INSERT_DOCUMENT_SQL
)
"""Every statement that filters rows. The insert is the one that creates the row instead."""


def _one_line(sql: str) -> str:
    """SQL whitespace is insignificant; the statements wrap where the line length says so."""
    return " ".join(sql.split())


@pytest.mark.parametrize("sql", WHERE_SCOPED_STATEMENTS, ids=lambda sql: sql.split()[0])
def test_every_filtering_statement_carries_the_tenant_scope_in_its_own_text(sql: str) -> None:
    """The only line between two companies (ADR-0009); nothing at run time may add it."""
    assert TENANT_PARAMETER in sql
    assert "where" in sql


def test_the_insert_binds_the_tenant_into_the_row_it_creates() -> None:
    """No `where` to scope, so the scope is the `company_id` value itself."""
    match = re.search(
        r"insert into documents \((?P<columns>[^)]*)\) values \((?P<values>.*?)\) returning",
        _one_line(INSERT_DOCUMENT_SQL),
    )
    assert match is not None, INSERT_DOCUMENT_SQL
    column_names = [name.strip() for name in match["columns"].split(",")]
    bound = [value.strip() for value in match["values"].split(",")]
    assert bound[column_names.index("company_id")] == "%(company_id)s"
    assert len(WHERE_SCOPED_STATEMENTS) == len(SCOPED_STATEMENTS) - 1


@pytest.mark.parametrize("sql", SCOPED_STATEMENTS, ids=lambda sql: sql.split()[0])
def test_every_statement_returns_the_full_record_column_list(sql: str) -> None:
    """Six copies of the column list, so a test keeps them identical rather than an f-string."""
    assert DOCUMENT_COLUMNS in _one_line(sql)


def test_the_column_list_names_exactly_the_record_fields() -> None:
    columns = [column.strip() for column in DOCUMENT_COLUMNS.split(",")]
    assert columns == list(DocumentRecord.model_fields)


def test_the_statements_are_the_seven_the_module_defines() -> None:
    assert SCOPED_STATEMENTS == (
        INSERT_DOCUMENT_SQL,
        MARK_PARSED_SQL,
        SET_FLAGGED_CHUNKS_SQL,
        MARK_STATUS_SQL,
        MARK_FAILED_SQL,
        SELECT_DOCUMENT_SQL,
        LIST_DOCUMENTS_SQL,
    )


@pytest.mark.parametrize(
    ("method", "names"),
    [
        ("insert", ("company_id", "document_id")),
        ("mark_parsed", ("company_id", "document_id")),
        ("mark_embedded", ("company_id", "document_id")),
        ("mark_ready", ("company_id", "document_id")),
        ("mark_failed", ("company_id", "document_id")),
        ("set_flagged_chunks", ("company_id", "document_id", "flagged_chunks")),
        ("get", ("company_id", "document_id")),
        ("list", ("company_id",)),
    ],
)
def test_scope_arguments_are_keyword_only_with_no_default(
    method: str, names: tuple[str, ...]
) -> None:
    """A call that forgets the company must not type-check, let alone run."""
    parameters = inspect.signature(getattr(DocumentsReadModel, method)).parameters
    for name in names:
        parameter = parameters[name]
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY, name
        assert parameter.default is inspect.Parameter.empty, name


# ------------------------------------------------------------------------------ insert


@pytest.mark.anyio
async def test_insert_writes_the_uploaded_row_and_returns_it() -> None:
    # Arrange
    model, source = read_model([document_row()])

    # Act
    record = await model.insert(
        company_id=COMPANY_ID,
        document_id=DOCUMENT_ID,
        kind=DocumentKind.COMPANY_EVIDENCE,
        name="Nachweis ISO 27001 (2026).pdf",
        storage_path=f"{COMPANY_ID}/{DOCUMENT_ID}/Nachweis_ISO_27001_2026_.pdf",
    )

    # Assert
    assert source.only.sql == INSERT_DOCUMENT_SQL
    assert source.only.params == {
        "id": DOCUMENT_ID,
        "company_id": COMPANY_ID,
        "kind": "company_evidence",
        "name": "Nachweis ISO 27001 (2026).pdf",
        "storage_path": f"{COMPANY_ID}/{DOCUMENT_ID}/Nachweis_ISO_27001_2026_.pdf",
    }
    assert record.status is DocumentStatus.UPLOADED
    assert record.name == "Nachweis ISO 27001 (2026).pdf"
    assert "'uploaded'" in INSERT_DOCUMENT_SQL, "the first status is written, not defaulted"


@pytest.mark.anyio
async def test_insert_that_returns_no_row_is_an_error_not_a_none() -> None:
    """`returning` always yields the row it inserted; nothing back means nothing written."""
    model, _source = read_model([])

    with pytest.raises(ReadModelError, match=str(DOCUMENT_ID)):
        await model.insert(
            company_id=COMPANY_ID,
            document_id=DOCUMENT_ID,
            kind=DocumentKind.TENDER_DOCUMENT,
            name="cctp.pdf",
            storage_path=f"{COMPANY_ID}/{DOCUMENT_ID}/cctp.pdf",
        )


# ------------------------------------------------------------------------- transitions


@pytest.mark.anyio
async def test_mark_parsed_binds_the_page_counts_and_a_list_for_the_array_column() -> None:
    """psycopg adapts a list to `integer[]` and a tuple to a composite record."""
    # Arrange
    model, source = read_model([document_row(status="parsed", pages=5, unread_pages=[2, 4])])

    # Act
    record = await model.mark_parsed(
        company_id=COMPANY_ID, document_id=DOCUMENT_ID, pages=5, unread_pages=(2, 4)
    )

    # Assert
    assert source.only.sql == MARK_PARSED_SQL
    assert source.only.params == {
        "document_id": DOCUMENT_ID,
        "company_id": COMPANY_ID,
        "pages": 5,
        "unread_pages": [2, 4],
    }
    assert isinstance(source.only.params["unread_pages"], list)
    assert record.status is DocumentStatus.PARSED
    assert record.unread_pages == (2, 4)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method", "status"),
    [("mark_embedded", DocumentStatus.EMBEDDED), ("mark_ready", DocumentStatus.READY)],
)
async def test_the_bare_transitions_bind_their_status_value(
    method: str, status: DocumentStatus
) -> None:
    # Arrange
    model, source = read_model([document_row(status=status.value)])

    # Act
    record = await getattr(model, method)(company_id=COMPANY_ID, document_id=DOCUMENT_ID)

    # Assert
    assert source.only.sql == MARK_STATUS_SQL
    assert source.only.params == {
        "document_id": DOCUMENT_ID,
        "company_id": COMPANY_ID,
        "status": status.value,
    }
    assert record.status is status


@pytest.mark.anyio
async def test_mark_failed_binds_the_reason_the_bidder_will_read() -> None:
    # Arrange
    reason = "The file could not be read as a PDF. Re-export it and upload it again."
    model, source = read_model([document_row(status="failed", failure_reason=reason)])

    # Act
    record = await model.mark_failed(
        company_id=COMPANY_ID, document_id=DOCUMENT_ID, reason=reason
    )

    # Assert
    assert source.only.sql == MARK_FAILED_SQL
    assert source.only.params == {
        "document_id": DOCUMENT_ID,
        "company_id": COMPANY_ID,
        "reason": reason,
    }
    assert record.status is DocumentStatus.FAILED
    assert record.failure_reason == reason


@pytest.mark.anyio
@pytest.mark.parametrize("reason", ["", "   ", "\n"])
async def test_mark_failed_refuses_a_blank_reason_before_touching_the_database(
    reason: str,
) -> None:
    """A `failed` row with nothing to act on is a dead end on the dashboard."""
    model, source = read_model([document_row()])

    with pytest.raises(ReadModelError, match="without a reason"):
        await model.mark_failed(company_id=COMPANY_ID, document_id=DOCUMENT_ID, reason=reason)
    assert source.log == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    "method", ["mark_parsed", "mark_embedded", "mark_ready", "mark_failed"]
)
async def test_a_transition_that_touches_no_row_is_an_error_naming_the_document(
    method: str,
) -> None:
    """A quiet `None` here would let a poller wait forever on a row that never moves."""
    model, _source = read_model([])
    extra: dict[str, Any] = {
        "mark_parsed": {"pages": 1, "unread_pages": ()},
        "mark_failed": {"reason": "Processing failed unexpectedly. Try again later."},
    }.get(method, {})

    with pytest.raises(ReadModelError, match=str(DOCUMENT_ID)):
        await getattr(model, method)(company_id=COMPANY_ID, document_id=DOCUMENT_ID, **extra)


@pytest.mark.anyio
async def test_set_flagged_chunks_binds_the_numbers_and_leaves_the_status_alone() -> None:
    """The guard's verdict is not a stage of the pipeline (S2.3.1).

    A document whose chunks were withheld still goes on to `embedded` and `ready`; writing a
    status here would invent a transition the poller would have to learn.
    """
    # Arrange
    model, source = read_model([document_row(flagged_chunks=[2, 7])])

    # Act
    record = await model.set_flagged_chunks(
        company_id=COMPANY_ID, document_id=DOCUMENT_ID, flagged_chunks=(2, 7)
    )

    # Assert
    assert source.only.sql == SET_FLAGGED_CHUNKS_SQL
    assert source.only.params == {
        "document_id": DOCUMENT_ID,
        "company_id": COMPANY_ID,
        "flagged_chunks": [2, 7],
    }
    assert "set flagged_chunks" in source.only.sql
    assert "status =" not in source.only.sql
    assert record.flagged_chunks == (2, 7)


@pytest.mark.anyio
async def test_set_flagged_chunks_binds_a_list_not_the_sequence_it_was_given() -> None:
    """psycopg adapts a tuple to a composite record, a list to an array (CLAUDE.md)."""
    # Arrange
    model, source = read_model([document_row(flagged_chunks=[])])

    # Act
    await model.set_flagged_chunks(
        company_id=COMPANY_ID, document_id=DOCUMENT_ID, flagged_chunks=()
    )

    # Assert
    assert isinstance(source.only.params["flagged_chunks"], list)


@pytest.mark.anyio
async def test_set_flagged_chunks_on_a_row_that_is_not_there_names_the_document() -> None:
    # Arrange
    model, _source = read_model([])

    # Act & Assert
    with pytest.raises(ReadModelError, match=str(DOCUMENT_ID)):
        await model.set_flagged_chunks(
            company_id=COMPANY_ID, document_id=DOCUMENT_ID, flagged_chunks=(1,)
        )


# ---------------------------------------------------------------------------- reads


@pytest.mark.anyio
async def test_get_binds_both_halves_of_the_scope_and_returns_the_record() -> None:
    # Arrange
    model, source = read_model([document_row(status="ready", pages=3)])

    # Act
    record = await model.get(company_id=COMPANY_ID, document_id=DOCUMENT_ID)

    # Assert
    assert source.only.sql == SELECT_DOCUMENT_SQL
    assert source.only.params == {"document_id": DOCUMENT_ID, "company_id": COMPANY_ID}
    assert record is not None
    assert record.status is DocumentStatus.READY
    assert record.pages == 3


@pytest.mark.anyio
async def test_get_for_another_company_is_none_never_an_error() -> None:
    """The router turns `None` into 404; a distinct answer would confirm the id exists."""
    model, source = read_model([])

    found = await model.get(company_id=OTHER_COMPANY_ID, document_id=DOCUMENT_ID)

    assert found is None
    assert source.only.params["company_id"] == OTHER_COMPANY_ID


@pytest.mark.anyio
async def test_list_returns_every_row_in_the_order_the_database_gave() -> None:
    # Arrange
    second = uuid.UUID("55555555-5555-4555-8555-555555555555")
    model, source = read_model([document_row(id=second, status="ready"), document_row()])

    # Act
    records = await model.list(company_id=COMPANY_ID)

    # Assert
    assert source.only.sql == LIST_DOCUMENTS_SQL
    assert source.only.params == {"company_id": COMPANY_ID}
    assert [record.id for record in records] == [second, DOCUMENT_ID]
    assert "order by created_at desc" in LIST_DOCUMENTS_SQL


@pytest.mark.anyio
async def test_list_with_no_documents_is_empty() -> None:
    model, _source = read_model([])
    assert await model.list(company_id=COMPANY_ID) == ()


@pytest.mark.anyio
async def test_a_row_with_an_unexpected_shape_is_a_loud_error() -> None:
    """Never a half-filled record: the query and the model have drifted apart."""
    model, _source = read_model([document_row(pages=-1)])

    with pytest.raises(ReadModelError, match="unexpected shape"):
        await model.get(company_id=COMPANY_ID, document_id=DOCUMENT_ID)


# ------------------------------------------------------------------------ the record


def test_a_failed_record_must_carry_a_reason() -> None:
    with pytest.raises(ValidationError, match="failure_reason"):
        DocumentRecord.model_validate(document_row(status="failed", failure_reason=None))


def test_no_other_status_may_carry_a_reason() -> None:
    """Mirrors `documents_failed_needs_reason_check`: a reason if and only if failed."""
    with pytest.raises(ValidationError, match="failure_reason"):
        DocumentRecord.model_validate(document_row(status="ready", failure_reason="stale"))


def test_the_record_is_frozen_and_refuses_unknown_columns() -> None:
    record = DocumentRecord.model_validate(document_row())

    with pytest.raises(ValidationError):
        record.status = DocumentStatus.READY  # type: ignore[misc]
    with pytest.raises(ValidationError, match="extra"):
        # `flagged_chunks` stood here until S2.3.1 made it a real column, which is the
        # hazard with using a plausible future name as the example of an impossible one.
        DocumentRecord.model_validate(document_row(shredded_by_goat=True))


def test_the_happy_path_statuses_are_linear_and_failed_is_terminal() -> None:
    """The names are user-visible: the browser renders them as the upload's progress."""
    assert [status.value for status in DocumentStatus] == [
        "uploaded",
        "parsed",
        "embedded",
        "ready",
        "failed",
    ]


# --------------------------------------------------------- schema / contract parity


def _constraint_values(sql: str, constraint: str) -> set[str]:
    """The quoted values inside `constraint <name> check (... in (...))`, as 0001's guard."""
    pattern = re.compile(
        rf"constraint\s+{re.escape(constraint)}\s+check\s*\((.*?)\)\s*\)",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(sql)
    assert match is not None, f"constraint {constraint} not found in {MIGRATION.name}"
    return set(re.findall(r"'([^']+)'", match.group(1)))


def test_the_migration_status_list_equals_the_enum() -> None:
    """A value the model allows and the database rejects is an insert error in production."""
    # Act
    allowed = _constraint_values(
        MIGRATION.read_text(encoding="utf-8"), "documents_status_check"
    )

    # Assert
    assert allowed == {status.value for status in DocumentStatus}


def test_the_migration_adds_the_three_columns_and_the_reason_invariant() -> None:
    """`failed` if and only if there is a reason, in the database as well as in Pydantic."""
    sql = MIGRATION.read_text(encoding="utf-8")

    for column in ("status", "failure_reason", "updated_at"):
        assert re.search(rf"add column if not exists {column}\b", sql), column
    assert "documents_failed_needs_reason_check" in sql
    assert "(status = 'failed') = (failure_reason is not null)" in sql
