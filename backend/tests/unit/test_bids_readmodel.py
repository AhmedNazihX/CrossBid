"""S3.1.1/S3.3.1 — the `bids`, `requirements` and `matrix_rows` projections, scripted.

Offline. The statements are asserted as text (every tenant-scoped one carries the predicate,
the one unscoped one is named and known) and every writer and reader runs against a fake
connection that records what it was asked and answers from a script. psycopg's own
behaviour -- `UUID` and `datetime` objects back, `rowcount` on an update -- is what the
scripts imitate, because the row readers exist to translate exactly that.
"""

from __future__ import annotations

import uuid
from collections import deque
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from typing import Any

import pytest
from psycopg.types.json import Jsonb

from crossbid.models.ecertis_criteria import CRITERION_IDS
from crossbid.models.matrix import (
    EcertisEvidence,
    Evidence,
    MatrixRow,
    ReviewerStatus,
    RowStatus,
)
from crossbid.models.requirement import (
    Checkability,
    Requirement,
    RequirementCategory,
    RequirementKind,
    RequirementStage,
    Threshold,
    ThresholdComparator,
    ThresholdUnit,
)
from crossbid.models.tender import BidStatus, DocumentKind
from crossbid.readmodel import bids, matrix, requirements
from crossbid.readmodel.bids import (
    MAX_BIDS_LISTED,
    UNFINISHED_STATUSES,
    BidDocumentRow,
    BidNotFoundError,
    BidReadModelError,
    BidRow,
    BidStateError,
    attach_documents,
    bid_documents,
    company_language,
    create_bid,
    documents_by_id,
    fetch_bid,
    list_bids,
    mark_bid_failed,
    set_bid_problems,
    set_bid_status,
    thread_id_of,
    unfinished_bids,
)
from crossbid.readmodel.documents import DocumentStatus
from crossbid.readmodel.matrix import fetch_matrix_rows, write_matrix_rows
from crossbid.readmodel.requirements import fetch_requirements, write_requirements

pytestmark = pytest.mark.anyio

COMPANY_ID = uuid.uuid4()
BID_ID = uuid.uuid4()
NOW = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)
TENANT_PREDICATE = "%(company_id)s"


# ----------------------------------------------------------------------- fake connection


class Scripted:
    """One answer: the rows a select returns, or the rowcount an update reports."""

    def __init__(self, rows: Sequence[dict[str, Any]] = (), *, rowcount: int = 1) -> None:
        self.rows = list(rows)
        self.rowcount = rowcount


class FakeCursor:
    def __init__(self, answer: Scripted, log: list[tuple[str, Any]]) -> None:
        self.rowcount = answer.rowcount
        self._rows = answer.rows
        self._log = log

    async def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    async def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)

    async def executemany(self, sql: str, params: Sequence[dict[str, Any]]) -> None:
        self._log.append((sql, list(params)))

    async def __aenter__(self) -> FakeCursor:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


class FakeConnection:
    def __init__(self, answers: Sequence[Scripted]) -> None:
        self._answers = deque(answers)
        self.executed: list[tuple[str, Any]] = []

    async def execute(self, sql: str, params: dict[str, Any] | None = None) -> FakeCursor:
        self.executed.append((sql, params))
        answer = self._answers.popleft() if self._answers else Scripted()
        return FakeCursor(answer, self.executed)

    def cursor(self) -> FakeCursor:
        return FakeCursor(Scripted(), self.executed)


class FakeDatabase:
    """`ConnectionSource` over one scripted connection; counts how often it was borrowed."""

    def __init__(self, *answers: Scripted) -> None:
        self.conn = FakeConnection(answers)
        self.borrowed = 0

    def connection(self) -> Any:
        return self._borrow()

    @asynccontextmanager
    async def _borrow(self) -> AsyncIterator[FakeConnection]:
        self.borrowed += 1
        yield self.conn

    @property
    def statements(self) -> list[str]:
        return [sql for sql, _ in self.conn.executed]

    def params(self, index: int = 0) -> Any:
        return self.conn.executed[index][1]


def bid_record(**overrides: Any) -> dict[str, Any]:
    """A `bids` row joined with the company language, as psycopg would hand it back."""
    record: dict[str, Any] = {
        "id": BID_ID,
        "company_id": COMPANY_ID,
        "thread_id": thread_id_of(str(BID_ID)),
        "ted_publication_number": "614251-2026",
        "title": "Netztechnik",
        "source_language": "de",
        "status": "queued",
        "failure_reason": None,
        "problems": [],
        "created_at": NOW,
        "updated_at": NOW,
        "bidder_language": "de",
    }
    return record | overrides


def document_record(**overrides: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "id": uuid.uuid4(),
        "name": "Bewerbungsbedingungen.pdf",
        "storage_path": f"{COMPANY_ID}/doc/Bewerbungsbedingungen.pdf",
        "kind": "tender_document",
        "status": "ready",
        "bid_id": None,
        "pages": 12,
        "unread_pages": [3, 4],
    }
    return record | overrides


def requirement(**overrides: Any) -> Requirement:
    values: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "bid_id": str(BID_ID),
        "category": RequirementCategory.ECONOMIC_FINANCIAL,
        "kind": RequirementKind.MANDATORY,
        "stage": RequirementStage.BID_ELIGIBILITY,
        "checkable": Checkability.COMPANY_PROPERTY,
        "source_text": "Der Umsatz muss mindestens 3.000.000,00 EUR pro Jahr betragen.",
        "source_lang": "de",
        "document_name": "Bewerbungsbedingungen.pdf",
        "page": 4,
        "translation": "Mindestumsatz von 3.000.000,00 EUR pro Jahr.",
    }
    return Requirement(**(values | overrides))


# --------------------------------------------------------------------- the statements


@pytest.mark.parametrize("statement", bids.SCOPED_STATEMENTS)
def test_every_scoped_bid_statement_binds_the_company(statement: str) -> None:
    """The API connects with `BYPASSRLS`; this predicate is the only tenant boundary."""
    assert TENANT_PREDICATE in statement


@pytest.mark.parametrize("statement", requirements.SCOPED_STATEMENTS)
def test_every_requirement_statement_binds_the_company(statement: str) -> None:
    assert TENANT_PREDICATE in statement


@pytest.mark.parametrize("statement", matrix.SCOPED_STATEMENTS)
def test_every_matrix_statement_binds_the_company(statement: str) -> None:
    assert TENANT_PREDICATE in statement


def test_the_startup_query_is_the_one_deliberately_unscoped_statement() -> None:
    """Named and known: it spans every company on purpose and is never reachable from a
    request. Anything else without the predicate would be a leak."""
    unscoped = [
        name
        for name, value in vars(bids).items()
        if name.isupper() and isinstance(value, str) and "select" in value.lower()
        if TENANT_PREDICATE not in value
    ]
    assert unscoped == ["SELECT_UNFINISHED_BIDS"]
    assert bids.SELECT_UNFINISHED_BIDS not in bids.SCOPED_STATEMENTS


def test_unfinished_statuses_exclude_the_parked_and_terminal_ones() -> None:
    assert BidStatus.AWAITING_REVIEW not in UNFINISHED_STATUSES
    assert BidStatus.COMPLETE not in UNFINISHED_STATUSES
    assert BidStatus.FAILED not in UNFINISHED_STATUSES
    assert {BidStatus.QUEUED, BidStatus.PARSING, BidStatus.EXTRACTING} <= UNFINISHED_STATUSES


def test_thread_id_follows_the_bid_convention() -> None:
    assert thread_id_of("abc") == "bid:abc"


# -------------------------------------------------------------------------------- bids


async def test_create_bid_inserts_queued_on_a_fresh_thread_and_reads_it_back() -> None:
    db = FakeDatabase(Scripted(), Scripted([bid_record()]))

    row = await create_bid(
        db,
        company_id=str(COMPANY_ID),
        notice_number="614251-2026",
        title="Netztechnik",
        source_language="de",
        bidder_language="de",
    )

    insert = db.params(0)
    assert db.statements[0] is bids.INSERT_BID
    assert insert["status"] == "queued"
    assert insert["thread_id"] == f"bid:{insert['id']}"
    assert uuid.UUID(insert["id"])
    assert insert["company_id"] == str(COMPANY_ID)
    assert db.statements[1] is bids.SELECT_BID
    assert db.params(1) == {"company_id": str(COMPANY_ID), "bid_id": insert["id"]}
    assert row.id == str(BID_ID) and row.status is BidStatus.QUEUED
    assert db.borrowed == 1, "insert and read-back share one connection"


async def test_create_bid_that_cannot_be_read_back_is_an_error() -> None:
    db = FakeDatabase(Scripted(), Scripted([]))

    with pytest.raises(BidReadModelError, match="could not be read back"):
        await create_bid(
            db,
            company_id=str(COMPANY_ID),
            notice_number="n",
            title="t",
            source_language="de",
            bidder_language="de",
        )


async def test_fetch_bid_translates_psycopg_types_and_answers_none_when_absent() -> None:
    db = FakeDatabase(Scripted([bid_record(problems=[{"reason": "x"}])]), Scripted([]))

    found = await fetch_bid(db, company_id=str(COMPANY_ID), bid_id=str(BID_ID))
    missing = await fetch_bid(db, company_id=str(COMPANY_ID), bid_id=str(uuid.uuid4()))

    assert found is not None
    assert found.id == str(BID_ID) and found.company_id == str(COMPANY_ID)
    assert found.notice_number == "614251-2026"
    assert found.bidder_language == "de"
    assert found.problems == [{"reason": "x"}]
    assert found.created_at == NOW
    assert missing is None


async def test_list_bids_is_bounded() -> None:
    db = FakeDatabase(Scripted([bid_record(), bid_record(id=uuid.uuid4())]))

    rows = await list_bids(db, company_id=str(COMPANY_ID))

    assert len(rows) == 2
    assert db.params() == {"company_id": str(COMPANY_ID), "limit": MAX_BIDS_LISTED}


async def test_unfinished_bids_asks_for_exactly_the_running_statuses() -> None:
    db = FakeDatabase(Scripted([bid_record(status="parsing")]))

    rows = await unfinished_bids(db)

    assert [row.status for row in rows] == [BidStatus.PARSING]
    assert db.params() == {"statuses": sorted(s.value for s in UNFINISHED_STATUSES)}
    assert "awaiting_review" not in db.params()["statuses"]


async def test_set_bid_status_writes_the_value_scoped_by_company() -> None:
    db = FakeDatabase(Scripted(rowcount=1))

    await set_bid_status(
        db, company_id=str(COMPANY_ID), bid_id=str(BID_ID), status=BidStatus.EXTRACTING
    )

    assert db.statements == [bids.UPDATE_BID_STATUS]
    assert db.params() == {
        "company_id": str(COMPANY_ID),
        "bid_id": str(BID_ID),
        "status": "extracting",
    }


async def test_a_status_write_that_touches_no_row_is_not_found() -> None:
    """Another company's bid id, or a deleted bid: the caller must hear about it."""
    db = FakeDatabase(Scripted(rowcount=0))

    with pytest.raises(BidNotFoundError, match=str(BID_ID)):
        await set_bid_status(
            db, company_id=str(COMPANY_ID), bid_id=str(BID_ID), status=BidStatus.PARSING
        )


async def test_mark_bid_failed_writes_failed_with_the_reason() -> None:
    db = FakeDatabase(Scripted(rowcount=1))

    await mark_bid_failed(
        db, company_id=str(COMPANY_ID), bid_id=str(BID_ID), reason="parsing failed: OSError"
    )

    assert db.statements == [bids.UPDATE_BID_FAILED]
    assert db.params()["status"] == "failed"
    assert db.params()["reason"] == "parsing failed: OSError"


async def test_mark_bid_failed_on_a_missing_bid_is_not_found() -> None:
    db = FakeDatabase(Scripted(rowcount=0))

    with pytest.raises(BidNotFoundError):
        await mark_bid_failed(db, company_id=str(COMPANY_ID), bid_id=str(BID_ID), reason="r")


async def test_set_bid_problems_sends_the_list_as_jsonb() -> None:
    db = FakeDatabase(Scripted(rowcount=1))
    problems = [{"reason": "unreadable_document", "document_name": "a.pdf"}]

    await set_bid_problems(
        db, company_id=str(COMPANY_ID), bid_id=str(BID_ID), problems=problems
    )

    sent = db.params()["problems"]
    assert isinstance(sent, Jsonb)
    assert sent.obj == problems


async def test_set_bid_problems_on_a_missing_bid_is_not_found() -> None:
    db = FakeDatabase(Scripted(rowcount=0))

    with pytest.raises(BidNotFoundError):
        await set_bid_problems(db, company_id=str(COMPANY_ID), bid_id=str(BID_ID), problems=[])


def test_bid_row_summary_is_the_dashboard_shape() -> None:
    row = BidRow(
        id=str(BID_ID),
        company_id=str(COMPANY_ID),
        thread_id=thread_id_of(str(BID_ID)),
        notice_number="614251-2026",
        title="Netztechnik",
        source_language="de",
        bidder_language="de",
        status=BidStatus.QUEUED,
        created_at=NOW,
    )

    summary = row.summary()

    assert summary.id == str(BID_ID)
    assert summary.ted_publication_number == "614251-2026"
    assert summary.status is BidStatus.QUEUED
    assert summary.decision is None
    assert summary.created_at == NOW


# --------------------------------------------------------------------- companies, docs


async def test_company_language_answers_the_language_or_none() -> None:
    db = FakeDatabase(Scripted([{"language": "fr"}]), Scripted([]))

    assert await company_language(db, company_id=str(COMPANY_ID)) == "fr"
    assert await company_language(db, company_id=str(uuid.uuid4())) is None


async def test_documents_by_id_binds_uuids_and_reads_the_status() -> None:
    """A list of `str` goes to Postgres as `text[]`, which will not compare with a `uuid`
    column; the ids are converted so the array is typed."""
    record = document_record()
    db = FakeDatabase(Scripted([record]))

    [row] = await documents_by_id(
        db, company_id=str(COMPANY_ID), document_ids=[str(record["id"])]
    )

    assert db.params()["document_ids"] == [record["id"]]
    assert all(isinstance(value, uuid.UUID) for value in db.params()["document_ids"])
    assert row == BidDocumentRow(
        id=str(record["id"]),
        name="Bewerbungsbedingungen.pdf",
        storage_path=record["storage_path"],
        kind=DocumentKind.TENDER_DOCUMENT,
        status=DocumentStatus.READY,
        bid_id=None,
        pages=12,
        unread_pages=(3, 4),
    )


async def test_bid_documents_reads_the_attached_rows() -> None:
    db = FakeDatabase(Scripted([document_record(bid_id=BID_ID, unread_pages=None)]))

    [row] = await bid_documents(db, company_id=str(COMPANY_ID), bid_id=str(BID_ID))

    assert db.statements == [bids.SELECT_BID_DOCUMENTS]
    assert row.bid_id == str(BID_ID)
    assert row.unread_pages == ()


async def test_attach_documents_needs_at_least_one_id() -> None:
    db = FakeDatabase()

    with pytest.raises(BidStateError, match="at least one document"):
        await attach_documents(
            db, company_id=str(COMPANY_ID), bid_id=str(BID_ID), document_ids=[]
        )

    assert db.borrowed == 0


async def test_attach_documents_takes_every_id_or_reports_the_shortfall() -> None:
    ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    db = FakeDatabase(Scripted(rowcount=2), Scripted(rowcount=1))

    await attach_documents(db, company_id=str(COMPANY_ID), bid_id=str(BID_ID), document_ids=ids)
    with pytest.raises(BidStateError, match="only 1 of 2"):
        await attach_documents(
            db, company_id=str(COMPANY_ID), bid_id=str(BID_ID), document_ids=ids
        )

    assert db.statements == [bids.ATTACH_DOCUMENTS, bids.ATTACH_DOCUMENTS]
    assert db.params()["document_ids"] == [uuid.UUID(identifier) for identifier in ids]


def test_bid_document_row_is_frozen() -> None:
    row = BidDocumentRow(
        id="d",
        name="n",
        storage_path="p",
        kind=DocumentKind.TENDER_DOCUMENT,
        status=DocumentStatus.READY,
        bid_id=None,
        pages=1,
    )
    with pytest.raises(Exception, match="frozen"):
        row.name = "other"  # type: ignore[misc]


# ------------------------------------------------------------------------ requirements


async def test_write_requirements_with_nothing_to_write_borrows_no_connection() -> None:
    db = FakeDatabase()

    assert await write_requirements(db, company_id=str(COMPANY_ID), rows=[]) == 0
    assert db.borrowed == 0


async def test_write_requirements_upserts_every_row_in_one_executemany() -> None:
    db = FakeDatabase()
    threshold = Threshold(
        comparator=ThresholdComparator.AT_LEAST,
        value=3_000_000,
        unit=ThresholdUnit.CURRENCY,
        currency="EUR",
        period="per_year",
    )
    rows = [requirement(threshold=threshold), requirement(translation=None)]

    written = await write_requirements(db, company_id=str(COMPANY_ID), rows=rows)

    assert written == 2
    [(sql, params)] = db.conn.executed
    assert sql is requirements.UPSERT_REQUIREMENT
    first, second = params
    assert first["company_id"] == str(COMPANY_ID)
    assert first["category"] == "economic_financial"
    assert first["stage"] == "bid_eligibility"
    assert isinstance(first["threshold"], Jsonb)
    assert first["threshold"].obj["comparator"] == "at_least"
    assert second["threshold"] is None
    assert second["translation"] is None


async def test_fetch_requirements_revalidates_rows_from_the_table() -> None:
    row = requirement(deadline=date(2026, 10, 1))
    record = {
        "id": uuid.UUID(row.id),
        "bid_id": BID_ID,
        "category": "economic_financial",
        "kind": "mandatory",
        "stage": "bid_eligibility",
        "checkable": "company_property",
        "source_text": row.source_text,
        "source_lang": "de",
        "document_name": row.document_name,
        "page": 4,
        "translation": row.translation,
        "ecertis_criterion_id": None,
        "threshold": {"comparator": "at_least", "value": 29, "unit": "fte"},
        "deadline": date(2026, 10, 1),
    }
    db = FakeDatabase(Scripted([record]))

    [found] = await fetch_requirements(db, company_id=str(COMPANY_ID), bid_id=str(BID_ID))

    assert db.params() == {"company_id": str(COMPANY_ID), "bid_id": str(BID_ID)}
    assert found.id == row.id and found.bid_id == str(BID_ID)
    assert found.threshold == Threshold(
        comparator=ThresholdComparator.AT_LEAST, value=29, unit=ThresholdUnit.FTE
    )
    assert found.deadline == date(2026, 10, 1)
    assert found.ecertis_criterion_id is None


async def test_fetch_requirements_turns_a_criterion_uuid_back_into_a_string() -> None:
    from crossbid.models.ecertis_criteria import CRITERION_IDS

    record = {
        "id": uuid.uuid4(),
        "bid_id": BID_ID,
        "category": "exclusion_ground",
        "kind": "mandatory",
        "stage": "bid_eligibility",
        "checkable": "neither",
        "source_text": "Ausschlussgrund",
        "source_lang": "de",
        "document_name": "a.pdf",
        "page": 1,
        "translation": None,
        "ecertis_criterion_id": uuid.UUID(CRITERION_IDS[0]),
        "threshold": None,
        "deadline": None,
    }
    db = FakeDatabase(Scripted([record]))

    [found] = await fetch_requirements(db, company_id=str(COMPANY_ID), bid_id=str(BID_ID))

    assert found.ecertis_criterion_id == CRITERION_IDS[0]
    assert found.threshold is None


# ------------------------------------------------------------------------- matrix rows


def matrix_row(**overrides: Any) -> MatrixRow:
    values: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "requirement_id": str(uuid.uuid4()),
        "status": RowStatus.SUPPORTED,
        "evidence": (
            Evidence(
                document_id=str(uuid.uuid4()),
                document_name="Jahresabschluss_2025.pdf",
                page=2,
                quote="Der Jahresumsatz 2025 betrug 7.400.000,00 EUR.",
            ),
        ),
        "agent_rationale": "Der Jahresabschluss weist 7,4 Mio. EUR aus.",
    }
    return MatrixRow(**(values | overrides))


async def test_write_matrix_rows_with_nothing_to_write_borrows_no_connection() -> None:
    db = FakeDatabase()

    written = await write_matrix_rows(
        db, company_id=str(COMPANY_ID), bid_id=str(BID_ID), rows=[]
    )

    assert written == 0
    assert db.borrowed == 0


async def test_write_matrix_rows_upserts_every_row_in_one_executemany() -> None:
    """One lane is dozens of rows; a statement each is dozens of round trips to Frankfurt."""
    # Arrange
    criterion = EcertisEvidence(
        criterion_id=CRITERION_IDS[0],
        criterion_name="Payment of taxes",
        country="de",
        found=True,
        evidence_names=("Freistellungsbescheinigung",),
    )
    rows = [
        matrix_row(ecertis_evidence=criterion),
        matrix_row(status=RowStatus.PARTIALLY_SUPPORTED, evidence=()),
    ]
    db = FakeDatabase()

    # Act
    written = await write_matrix_rows(
        db, company_id=str(COMPANY_ID), bid_id=str(BID_ID), rows=rows
    )

    # Assert
    assert written == 2
    [(sql, params)] = db.conn.executed
    assert sql is matrix.UPSERT_MATRIX_ROW
    first, second = params
    assert first["company_id"] == str(COMPANY_ID)
    assert first["bid_id"] == str(BID_ID)
    assert first["status"] == "supported"
    assert isinstance(first["evidence"], Jsonb)
    assert first["evidence"].obj[0]["quote"].startswith("Der Jahresumsatz")
    assert isinstance(first["ecertis_evidence"], Jsonb)
    assert first["ecertis_evidence"].obj["country"] == "de"
    assert second["ecertis_evidence"] is None
    assert second["evidence"].obj == []


def test_the_upsert_leaves_the_reviewers_own_columns_alone() -> None:
    """A re-check refreshes the agent's finding; a human's disposition is not the agent's
    to overwrite, and S3.4.x writes those columns through its own statement."""
    # Assert
    updated = matrix.UPSERT_MATRIX_ROW.split("do update set")[1]
    for column in ("reviewer_status", "override_reason", "attached_doc_ids", "reviewed_at"):
        assert column not in updated


async def test_fetch_matrix_rows_revalidates_rows_from_the_table() -> None:
    # Arrange
    document_id = uuid.uuid4()
    attached = uuid.uuid4()
    record = {
        "id": uuid.uuid4(),
        "requirement_id": uuid.uuid4(),
        "status": "partially_supported",
        "evidence": [
            {
                "document_id": str(document_id),
                "document_name": "Police.pdf",
                "page": 3,
                "quote": "Deckungssumme 5.000.000 EUR.",
            }
        ],
        "ecertis_evidence": None,
        "agent_rationale": "Die Police deckt weniger als gefordert.",
        "reviewer_status": "confirmed",
        "override_reason": None,
        "attached_doc_ids": [attached],
        "reviewed_at": NOW,
    }
    db = FakeDatabase(Scripted([record]))

    # Act
    [found] = await fetch_matrix_rows(db, company_id=str(COMPANY_ID), bid_id=str(BID_ID))

    # Assert -- psycopg hands back UUIDs and datetimes; the row model speaks strings
    assert db.params() == {"company_id": str(COMPANY_ID), "bid_id": str(BID_ID)}
    assert found.status is RowStatus.PARTIALLY_SUPPORTED
    assert found.evidence[0].document_id == str(document_id)
    assert found.reviewer_status is ReviewerStatus.CONFIRMED
    assert found.attached_doc_ids == (str(attached),)
    assert found.reviewed_at == NOW


async def test_fetch_matrix_rows_reads_an_ecertis_mapping_back() -> None:
    record = {
        "id": uuid.uuid4(),
        "requirement_id": uuid.uuid4(),
        "status": "not_applicable",
        "evidence": None,
        "ecertis_evidence": {
            "criterion_id": CRITERION_IDS[0],
            "criterion_name": "Payment of taxes",
            "country": "de",
            "found": True,
            "evidence_names": ["Freistellungsbescheinigung"],
            "issuers": ["Finanzamt"],
            "description": "Zahlung von Steuern",
        },
        "agent_rationale": "Betrifft nur Bietergemeinschaften.",
        "reviewer_status": "pending",
        "override_reason": None,
        "attached_doc_ids": None,
        "reviewed_at": None,
    }
    db = FakeDatabase(Scripted([record]))

    [found] = await fetch_matrix_rows(db, company_id=str(COMPANY_ID), bid_id=str(BID_ID))

    assert found.evidence == ()
    assert found.ecertis_evidence is not None
    assert found.ecertis_evidence.issuers == ("Finanzamt",)
    assert found.attached_doc_ids == ()
