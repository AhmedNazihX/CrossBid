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
    RequirementSource,
    RequirementStage,
    Threshold,
    ThresholdComparator,
    ThresholdUnit,
)
from crossbid.models.tender import BidStatus, DocumentKind
from crossbid.models.verdict import Decision
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
    claim_bid_for_review,
    company_language,
    create_bid,
    documents_by_id,
    fetch_bid,
    list_bids,
    mark_bid_failed,
    record_review,
    release_bid_to_review,
    set_bid_problems,
    set_bid_status,
    set_bid_verdict,
    thread_id_of,
    unfinished_bids,
)
from crossbid.readmodel.documents import DocumentStatus
from crossbid.readmodel.matrix import (
    UPDATE_REVIEWED_ROW,
    UPSERT_MATRIX_ROW,
    fetch_matrix_rows,
    write_matrix_rows,
    write_reviewed_rows,
)
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


class FakeTransaction:
    """`AsyncConnection.transaction()`, recording only how the block ended.

    Every pooled connection is `autocommit=True` (`db.pool_connection_kwargs`), so a writer
    whose two statements have to land together must open a block explicitly. Recording the
    outcome is what lets a test prove a failed pair rolled back, which counting borrows --
    what this module used to assert -- never could.
    """

    def __init__(self, outcomes: list[str]) -> None:
        self._outcomes = outcomes

    async def __aenter__(self) -> FakeTransaction:
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, *_exc: object) -> bool:
        self._outcomes.append("rollback" if exc_type is not None else "commit")
        return False


class FakeConnection:
    def __init__(self, answers: Sequence[Scripted]) -> None:
        self._answers = deque(answers)
        self.executed: list[tuple[str, Any]] = []
        self.transactions: list[str] = []

    async def execute(self, sql: str, params: dict[str, Any] | None = None) -> FakeCursor:
        self.executed.append((sql, params))
        answer = self._answers.popleft() if self._answers else Scripted()
        return FakeCursor(answer, self.executed)

    def cursor(self) -> FakeCursor:
        return FakeCursor(Scripted(), self.executed)

    def transaction(self) -> FakeTransaction:
        return FakeTransaction(self.transactions)


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
        "verdict": None,
        "decision": None,
        "buyer": None,
        "deadline": None,
        "deadline_utc_offset_minutes": None,
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


async def test_set_bid_verdict_sends_the_verdict_as_jsonb() -> None:
    # Arrange
    db = FakeDatabase(Scripted(rowcount=1))
    verdict = {"decision": "conditional", "rationale": "x", "gaps": []}

    # Act
    await set_bid_verdict(db, company_id=str(COMPANY_ID), bid_id=str(BID_ID), verdict=verdict)

    # Assert
    sent = db.params()["verdict"]
    assert isinstance(sent, Jsonb)
    assert sent.obj == verdict


async def test_set_bid_verdict_on_a_missing_bid_is_not_found() -> None:
    db = FakeDatabase(Scripted(rowcount=0))

    with pytest.raises(BidNotFoundError):
        await set_bid_verdict(
            db, company_id=str(COMPANY_ID), bid_id=str(BID_ID), verdict={"decision": "go"}
        )


async def test_claiming_a_parked_bid_moves_it_off_awaiting_review() -> None:
    # Arrange
    db = FakeDatabase(Scripted(rowcount=1))

    # Act
    await claim_bid_for_review(db, company_id=str(COMPANY_ID), bid_id=str(BID_ID))

    # Assert
    params = db.params()
    assert params["parked"] == BidStatus.AWAITING_REVIEW.value
    assert params["claimed"] == BidStatus.APPLYING_REVIEW.value


async def test_claiming_a_bid_that_is_not_parked_is_a_state_error() -> None:
    """The 409 in S3.4.2. `rowcount == 0` is how a conditional update says "somebody else
    got there first", and it is the same answer as "this bid never parked"."""
    db = FakeDatabase(Scripted(rowcount=0))

    with pytest.raises(BidStateError, match="not waiting for a review"):
        await claim_bid_for_review(db, company_id=str(COMPANY_ID), bid_id=str(BID_ID))


async def test_recording_a_review_writes_the_audit_row_and_the_decision_together() -> None:
    # Arrange
    db = FakeDatabase(Scripted(rowcount=1), Scripted(rowcount=1))
    agent = {"decision": "no_go"}
    final = {"decision": "conditional"}

    # Act
    await record_review(
        db,
        company_id=str(COMPANY_ID),
        bid_id=str(BID_ID),
        decision=Decision.GO,
        agent_verdict=agent,
        final_verdict=final,
        override_reason="Die Referenzen liegen vor.",
    )

    # Assert -- both statements inside one committed transaction. The borrow count alone
    # proved nothing: `autocommit=True` means one connection is still two commits.
    assert db.borrowed == 1
    assert db.conn.transactions == ["commit"]
    assert "insert into reviews" in db.statements[0]
    assert "set decision" in db.statements[1]
    assert db.params(0)["agent_verdict"].obj == agent
    assert db.params(0)["final_verdict"].obj == final
    assert db.params(0)["decision"] == "go"
    assert db.params(0)["reviewer_id"] is None


async def test_recording_a_review_for_a_missing_bid_is_not_found() -> None:
    db = FakeDatabase(Scripted(rowcount=1), Scripted(rowcount=0))

    with pytest.raises(BidNotFoundError):
        await record_review(
            db,
            company_id=str(COMPANY_ID),
            bid_id=str(BID_ID),
            decision=Decision.GO,
            agent_verdict=None,
            final_verdict={"decision": "go"},
            override_reason=None,
        )


async def test_a_review_recorded_without_an_agent_verdict_stores_null_not_a_guess() -> None:
    # Arrange
    db = FakeDatabase(Scripted(rowcount=1), Scripted(rowcount=1))

    # Act
    await record_review(
        db,
        company_id=str(COMPANY_ID),
        bid_id=str(BID_ID),
        decision=Decision.GO,
        agent_verdict=None,
        final_verdict={"decision": "go"},
        override_reason=None,
    )

    # Assert
    assert db.params(0)["agent_verdict"].obj is None


def test_the_reviewers_decision_outranks_the_agents_on_the_dashboard() -> None:
    """Two answers to two questions, with a precedence rule -- not two copies of one."""
    # Arrange
    row = _bid_row_model(
        verdict={"decision": "no_go", "rationale": "x"},
        reviewed_decision=Decision.GO,
    )

    # Act / Assert
    assert row.decision is Decision.GO


def test_a_bid_awaiting_review_still_shows_the_agents_advisory_decision() -> None:
    row = _bid_row_model(verdict={"decision": "conditional", "rationale": "x"})

    assert row.decision is Decision.CONDITIONAL


def test_a_decision_column_the_vocabulary_no_longer_knows_reads_as_unset() -> None:
    """0004 renamed `go_with_open_items` out of the enum; a pre-rename row must not raise."""
    assert bids._optional_decision("go_with_open_items") is None
    assert bids._optional_decision(None) is None
    assert bids._optional_decision("go") is Decision.GO


def test_a_scored_bid_carries_its_decision_into_the_dashboard_row() -> None:
    # Arrange
    row = _bid_row_model(verdict={"decision": "no_go", "rationale": "x"})

    # Act / Assert
    assert row.decision is Decision.NO_GO
    assert row.summary().decision is Decision.NO_GO


@pytest.mark.parametrize(
    "verdict", [None, {}, {"decision": None}, {"decision": "go_with_open_items"}]
)
def test_an_absent_or_unreadable_verdict_leaves_the_decision_unset(
    verdict: dict[str, Any] | None,
) -> None:
    """A row the dashboard cannot interpret must not blank the whole list. `0004` renamed
    `go_with_open_items` out of the vocabulary, so a pre-rename row is the real case."""
    assert _bid_row_model(verdict=verdict).summary().decision is None


def _bid_row_model(**overrides: Any) -> BidRow:
    values: dict[str, Any] = {
        "id": str(BID_ID),
        "company_id": str(COMPANY_ID),
        "thread_id": thread_id_of(str(BID_ID)),
        "notice_number": "614251-2026",
        "title": "Netztechnik",
        "source_language": "de",
        "bidder_language": "de",
        "status": BidStatus.QUEUED,
        "created_at": NOW,
    }
    return BidRow(**(values | overrides))


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
        "source": "tender_document",
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
        "source": "tender_document",
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


async def test_an_espd_requirement_is_written_with_no_page_and_its_own_source() -> None:
    """S2.5.1: the DUME's criteria are rows too, and the column pair says where from."""
    # Arrange
    db = FakeDatabase()
    row = requirement(
        source=RequirementSource.ESPD_REQUEST,
        page=None,
        ecertis_criterion_id=CRITERION_IDS[0],
        document_name="DUME_acheteur.xml",
    )

    # Act
    await write_requirements(db, company_id=str(COMPANY_ID), rows=[row])

    # Assert
    [(_, params)] = db.conn.executed
    assert params[0]["source"] == "espd_request"
    assert params[0]["page"] is None
    assert params[0]["ecertis_criterion_id"] == CRITERION_IDS[0]


async def test_fetch_reads_an_espd_row_back_without_inventing_a_page() -> None:
    """A row the table says has no page must not come back claiming one."""
    # Arrange
    record = {
        "id": uuid.uuid4(),
        "bid_id": BID_ID,
        "category": "exclusion_ground",
        "kind": "mandatory",
        "stage": "bid_eligibility",
        "checkable": "document_submission",
        "source": "espd_request",
        "source_text": "Corruption",
        "source_lang": "fr",
        "document_name": "DUME_acheteur.xml",
        "page": None,
        "translation": None,
        "ecertis_criterion_id": uuid.UUID(CRITERION_IDS[0]),
        "threshold": None,
        "deadline": None,
    }
    db = FakeDatabase(Scripted([record]))

    # Act
    [found] = await fetch_requirements(db, company_id=str(COMPANY_ID), bid_id=str(BID_ID))

    # Assert
    assert found.source is RequirementSource.ESPD_REQUEST
    assert found.page is None


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


# ----------------------------------------------------------- the reviewer's own columns


async def test_the_agents_upsert_cannot_write_a_reviewers_column() -> None:
    """The safeguard: a resumed run re-checking a requirement refreshes the agent's finding
    and must leave a human's disposition exactly where it was (S3.4.2)."""
    updated = UPSERT_MATRIX_ROW[UPSERT_MATRIX_ROW.index("do update set") :]

    for column in ("reviewer_status", "override_reason", "attached_doc_ids", "reviewed_at"):
        assert column not in updated


async def test_writing_a_review_sends_the_reviewer_columns_and_the_status() -> None:
    # Arrange
    db = FakeDatabase(Scripted(rowcount=1))
    document_id = uuid.uuid4()
    row = MatrixRow(
        id=str(uuid.uuid4()),
        requirement_id=str(uuid.uuid4()),
        status=RowStatus.SUPPORTED,
        agent_rationale="Kein Nachweis gefunden.",
        reviewer_status=ReviewerStatus.OVERRIDDEN,
        override_reason="Der Nachweis liegt als Anlage 4 vor.",
        attached_doc_ids=(str(document_id),),
        reviewed_at=NOW,
    )

    # Act
    written = await write_reviewed_rows(
        db, company_id=str(COMPANY_ID), bid_id=str(BID_ID), rows=[row]
    )

    # Assert
    assert written == 1
    [(_sql, sent)] = db.conn.executed  # one `executemany`, so the params are a list
    [params] = sent
    assert params["reviewer_status"] == "overridden"
    assert params["override_reason"] == "Der Nachweis liegt als Anlage 4 vor."
    assert params["status"] == "supported"
    assert params["reviewed_at"] == NOW
    # `attached_doc_ids` is a `uuid[]` column: a list of `str` would go as `text[]`.
    assert params["attached_doc_ids"] == [document_id]


async def test_writing_no_reviewed_rows_touches_the_database_at_all() -> None:
    db = FakeDatabase()

    assert (
        await write_reviewed_rows(db, company_id=str(COMPANY_ID), bid_id=str(BID_ID), rows=[])
        == 0
    )
    assert db.borrowed == 0


def test_the_reviewer_update_is_scoped_to_the_bid_as_well_as_the_tenant() -> None:
    """A row id is a `uuid5` over a requirement id, so scoping by bid costs nothing and
    keeps the statement unable to reach across one."""
    assert "company_id = %(company_id)s" in UPDATE_REVIEWED_ROW
    assert "bid_id = %(bid_id)s" in UPDATE_REVIEWED_ROW


async def test_releasing_a_claimed_bid_puts_it_back_on_awaiting_review() -> None:
    """`failed` would be the obvious status and is a trap — it is terminal, the startup
    resume skips it, and `claim_bid_for_review` refuses it, so a review that failed on a
    transient timeout would be dead with the submission already in its checkpoint."""
    # Arrange
    db = FakeDatabase(Scripted(rowcount=1))

    # Act
    await release_bid_to_review(
        db,
        company_id=str(COMPANY_ID),
        bid_id=str(BID_ID),
        reason="applying_review failed: OperationalError",
    )

    # Assert
    params = db.params()
    assert params["status"] == BidStatus.AWAITING_REVIEW.value
    assert params["reason"] == "applying_review failed: OperationalError"


async def test_releasing_a_bid_that_is_not_this_companys_is_not_found() -> None:
    db = FakeDatabase(Scripted(rowcount=0))

    with pytest.raises(BidNotFoundError):
        await release_bid_to_review(
            db, company_id=str(COMPANY_ID), bid_id=str(BID_ID), reason="x"
        )


async def test_the_status_a_release_restores_is_the_one_the_claim_will_accept() -> None:
    """The pair has to agree or a failed review is unrecoverable — asserted against the
    values both statements actually send, because the defect was that they did not."""
    # Arrange
    claiming = FakeDatabase(Scripted(rowcount=1))
    releasing = FakeDatabase(Scripted(rowcount=1))

    # Act
    await claim_bid_for_review(claiming, company_id=str(COMPANY_ID), bid_id=str(BID_ID))
    await release_bid_to_review(
        releasing, company_id=str(COMPANY_ID), bid_id=str(BID_ID), reason="x"
    )

    # Assert -- what a release leaves behind is what a claim looks for
    assert releasing.params()["status"] == claiming.params()["parked"]
    # And it is not a status the startup resume would also pick up, which would race the
    # reviewer's own retry.
    assert BidStatus.AWAITING_REVIEW not in UNFINISHED_STATUSES


# ------------------------------------------------------- S4.4.1: what the dashboard counts


def test_the_open_item_statuses_are_the_two_a_row_can_be_unsettled_in() -> None:
    """Spelled out in SQL because `LiteralString` is what keeps a run-time value out of it,
    so the two definitions have to be compared by hand — which is this test."""
    # Arrange
    unsettled = {RowStatus.PARTIALLY_SUPPORTED.value, RowStatus.UNSUPPORTED.value}

    # Act / Assert -- every unsettled status is counted, and no settled one is
    for status in RowStatus:
        named = f"'{status.value}'" in bids._OPEN_ITEMS
        assert named == (status.value in unsettled), status


def test_the_open_item_subquery_carries_the_tenant_itself() -> None:
    """Not `m.company_id = b.company_id`: the fragment must be scoped on its own terms
    rather than by where it is spliced. The unscoped-statement guard caught it written the
    other way."""
    assert TENANT_PREDICATE in bids._OPEN_ITEMS
    assert "b.company_id" not in bids._OPEN_ITEMS


def test_only_the_list_query_pays_for_the_open_item_count() -> None:
    """A bid read on its own carries its whole matrix and can count what it already has."""
    assert "open_items" in bids.SELECT_BIDS
    assert "open_items" not in bids.SELECT_BID


async def test_a_listed_bid_carries_its_buyer_deadline_and_open_items() -> None:
    # Arrange
    deadline = datetime(2026, 10, 9, 14, 0, tzinfo=UTC)
    db = FakeDatabase(
        Scripted(
            [
                bid_record(
                    buyer="Ministère de l'Intérieur",
                    deadline=deadline,
                    deadline_utc_offset_minutes=120,
                    decision="conditional",
                    open_items=7,
                )
            ]
        )
    )

    # Act
    [row] = await list_bids(db, company_id=str(COMPANY_ID))
    summary = row.summary()

    # Assert
    assert summary.buyer == "Ministère de l'Intérieur"
    assert summary.deadline == deadline
    assert summary.deadline_utc_offset_minutes == 120
    assert summary.open_items == 7
    assert summary.decision is Decision.CONDITIONAL


async def test_a_bid_read_on_its_own_reports_no_open_items_rather_than_a_wrong_count() -> None:
    """`SELECT_BID` does not compute it, so the column is absent and the default stands —
    zero here means "not counted", and the workspace counts its own rows."""
    db = FakeDatabase(Scripted([bid_record()]))

    row = await fetch_bid(db, company_id=str(COMPANY_ID), bid_id=str(BID_ID))

    assert row is not None
    assert row.open_items == 0


async def test_starting_a_bid_stores_the_buyer_and_the_deadline_with_its_offset() -> None:
    # Arrange
    deadline = datetime(2026, 10, 9, 14, 0, tzinfo=UTC)
    db = FakeDatabase(Scripted(), Scripted([bid_record()]))

    # Act
    await create_bid(
        db,
        company_id=str(COMPANY_ID),
        notice_number="618320-2026",
        title="Conseil en architecture SI",
        source_language="fr",
        bidder_language="de",
        buyer="Ministère de l'Intérieur",
        deadline=deadline,
        deadline_utc_offset_minutes=120,
    )

    # Assert
    params = db.params()
    assert params["buyer"] == "Ministère de l'Intérieur"
    assert params["deadline"] == deadline
    assert params["deadline_offset"] == 120


async def test_a_bid_started_without_a_deadline_stores_neither_half_of_the_pair() -> None:
    """Migration 0007 refuses an offset with no deadline: an offset alone describes nothing."""
    # Arrange
    db = FakeDatabase(Scripted(), Scripted([bid_record()]))

    # Act
    await create_bid(
        db,
        company_id=str(COMPANY_ID),
        notice_number="618320-2026",
        title="x",
        source_language="fr",
        bidder_language="de",
    )

    # Assert
    params = db.params()
    assert params["deadline"] is None
    assert params["deadline_offset"] is None


# ---------------------------------------------------- S3.2.2: TED's deadline, conditionally


@pytest.mark.anyio
async def test_teds_deadline_is_written_when_the_bid_has_none() -> None:
    db = FakeDatabase(Scripted(rowcount=1))

    written = await bids.set_bid_deadline_if_unset(
        db,
        company_id=str(COMPANY_ID),
        bid_id=str(BID_ID),
        deadline=datetime(2026, 10, 7, tzinfo=UTC),
        deadline_utc_offset_minutes=120,
    )

    assert written is True
    assert db.statements == [bids.UPDATE_BID_DEADLINE_IF_UNSET]
    assert db.params()["company_id"] == str(COMPANY_ID)
    assert db.params()["deadline_offset"] == 120


@pytest.mark.anyio
async def test_teds_deadline_never_overwrites_the_one_the_bidder_gave() -> None:
    """The bidder's carries an hour and TED's never does (ADR-0043), so theirs is strictly
    better information — and a resumed run must not quietly replace it."""
    db = FakeDatabase(Scripted(rowcount=0))

    written = await bids.set_bid_deadline_if_unset(
        db,
        company_id=str(COMPANY_ID),
        bid_id=str(BID_ID),
        deadline=datetime(2026, 10, 7, tzinfo=UTC),
        deadline_utc_offset_minutes=120,
    )

    assert written is False, "zero rows means 'already set', not 'no such bid'"


def test_the_conditional_update_refuses_to_touch_a_bid_that_has_a_deadline() -> None:
    """The guard is in the SQL, not in a caller that might forget it."""
    assert "deadline is null" in " ".join(bids.UPDATE_BID_DEADLINE_IF_UNSET.split())


@pytest.mark.anyio
async def test_a_review_whose_decision_lands_on_no_bid_leaves_no_orphan_audit_row() -> None:
    """The defect the explicit transaction closes.

    `INSERT_REVIEW` runs first. Under `autocommit=True` it had already committed by the time
    a rowcount of zero on the update raised, so a bid nobody could find still gained a
    `reviews` row — an audit of a decision the dashboard never showed.
    """
    # Arrange -- the insert takes, the decision update matches nothing.
    db = FakeDatabase(Scripted(rowcount=1), Scripted(rowcount=0))

    # Act / Assert
    with pytest.raises(BidNotFoundError):
        await record_review(
            db,
            company_id=str(COMPANY_ID),
            bid_id=str(BID_ID),
            decision=Decision.GO,
            agent_verdict=None,
            final_verdict={"decision": "go"},
            override_reason=None,
        )

    assert db.conn.transactions == ["rollback"]


@pytest.mark.anyio
async def test_a_partial_attach_is_rolled_back_rather_than_left_permanent() -> None:
    """A shortfall used to strand the documents that did match.

    They were committed with `bid_id` set, the router then marked the bid `failed`, and
    `ATTACH_DOCUMENTS` only takes a document whose `bid_id is null` — so those files could
    never start another bid. The check now runs inside the block it is deciding about.
    """
    # Arrange
    ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    db = FakeDatabase(Scripted(rowcount=1))

    # Act / Assert
    with pytest.raises(BidStateError, match="only 1 of 2"):
        await attach_documents(
            db, company_id=str(COMPANY_ID), bid_id=str(BID_ID), document_ids=ids
        )

    assert db.conn.transactions == ["rollback"]


@pytest.mark.anyio
async def test_a_complete_attach_commits() -> None:
    ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    db = FakeDatabase(Scripted(rowcount=2))

    await attach_documents(db, company_id=str(COMPANY_ID), bid_id=str(BID_ID), document_ids=ids)

    assert db.conn.transactions == ["commit"]
