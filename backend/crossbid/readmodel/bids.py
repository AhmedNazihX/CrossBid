"""S3.1.1 — the `bids` projection: what the poller reads, and how the graph keeps it current.

The read model is a projection of the graph's state, and the plan's rule is stark: if the
two disagree, the checkpoint is right and the writer here has a bug. So this module is
written to be boring. Every statement is a `Final[LiteralString]` module constant with the
tenant predicate already in its text — `company_id = %(company_id)s` is not an argument a
caller may leave out, and `SCOPED_STATEMENTS` exists so a test can assert that across all
of them (ADR-0011). The API connects as a role with `BYPASSRLS`, so this filter is the
*only* line of defence and one missing `WHERE` clause is a cross-tenant leak (ADR-0009).

One statement is deliberately not scoped, and it is named for it: `SELECT_UNFINISHED_BIDS`
runs once at startup to find every company's runs that a restart interrupted. It answers a
question about the process, not about a tenant, and it returns ids only to the runner —
never to a request.

Two shapes of failure are kept apart. `BidNotFoundError` means the row for *this company*
is not there — the router turns it into 404 whether the bid never existed or belongs to
someone else, because a 403 would confirm that it exists. `BidStateError` means the row is
there but not in a state the operation makes sense for (a document already attached to
another bid, say); the router names the problem.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Any, Final, LiteralString, Protocol

from psycopg import AsyncConnection
from psycopg.rows import DictRow
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from crossbid.models.tender import BidStatus, BidSummary, DocumentKind
from crossbid.models.verdict import Decision
from crossbid.readmodel.documents import DocumentStatus

THREAD_ID_PREFIX: Final = "bid:"
"""The LangGraph thread a bid runs on is `bid:{id}`; chat (F3.5) will be `bid:{id}:chat`."""

MAX_BIDS_LISTED: Final = 200
"""The dashboard never pages, so the list query is bounded here rather than unbounded."""

UNFINISHED_STATUSES: Final = frozenset(
    {
        BidStatus.QUEUED,
        BidStatus.PARSING,
        BidStatus.EXTRACTING,
        BidStatus.CHECKING,
        BidStatus.SCORING,
        BidStatus.APPLYING_REVIEW,
    }
)
"""Statuses that mean "the graph should be running". `AWAITING_REVIEW` is parked, not
running — a human resumes it (S3.4.2) — and `COMPLETE` and `FAILED` are terminal."""

TENDER_DOCUMENT_KINDS: Final = frozenset(
    {
        DocumentKind.TENDER_DOCUMENT,
        DocumentKind.TENDER_NOTICE,
        DocumentKind.TENDER_ESPD_REQUEST,
    }
)
"""What a bid may be started from. A company's own evidence pack is never parsed as a
tender, however it was uploaded. The published ESPD request belongs to the tender like any
other of its files — `parse_docs` reads it with the ESPD reader rather than the PDF parser
(S2.5.1) — so leaving it out here would be the one way to upload a DUME and never use it."""


class BidReadModelError(RuntimeError):
    """A read-model operation could not be completed. Never carries a DSN or a row."""


class BidNotFoundError(BidReadModelError):
    """No such bid *for this company*. Routers map it to 404 — never 403, see the module."""


class BidStateError(BidReadModelError):
    """The row exists but the operation does not fit its state; the message names why."""


class ConnectionSource(Protocol):
    """Something that lends a pooled connection. `crossbid.db.Database` satisfies it.

    Mirrors `ingestion.embeddings.ConnectionSource` rather than importing it: the read model
    needs no `vector` registration, and the two modules should not have to move together.
    """

    def connection(self) -> AbstractAsyncContextManager[AsyncConnection[DictRow]]: ...


# ------------------------------------------------------------------------------- rows


class BidRow(BaseModel):
    """One `bids` row joined with the company's language, as the graph and router read it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    company_id: str
    thread_id: str
    notice_number: str | None
    title: str
    source_language: str | None
    bidder_language: str
    status: BidStatus
    failure_reason: str | None = None
    problems: list[Any] = Field(default_factory=list)
    """The `ExtractionProblem` list as stored — raw JSON here, validated by the router, so
    that this module never imports from `agent/`."""
    verdict: dict[str, Any] | None = None
    """The `Verdict` as stored, raw for the same reason `problems` is. `None` until
    `score_verdict` has run (S3.4.1)."""
    reviewed_decision: Decision | None = None
    """`bids.decision` (migration 0006): the *reviewer's* final call, `None` until a human
    has made one. Named apart from `decision` below because they are not the same fact —
    see that property."""
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def summary(self) -> BidSummary:
        """The dashboard's shape, from `models/`.

        `decision` is read out of the stored verdict rather than kept in a column of its
        own: two places recording the same answer is two places that can disagree, and the
        column would have to be written by the same statement anyway. A verdict whose shape
        the dashboard does not recognise leaves `decision` unset instead of failing the
        list — one unreadable row must not blank a company's dashboard.
        """
        return BidSummary(
            id=self.id,
            company_id=self.company_id,
            ted_publication_number=self.notice_number,
            title=self.title,
            source_language=self.source_language,
            status=self.status,
            decision=self.decision,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    @property
    def decision(self) -> Decision | None:
        """What the dashboard shows: the reviewer's call once there is one, else the agent's.

        Two sources with a precedence rule, not two copies of one answer. `bids.decision` is
        what a person decided and exists only after a review (S3.4.2); the verdict's own
        decision is the agent's advisory reading, which is what a bid parked at
        `awaiting_review` has to offer. A bid with neither is still in flight and shows
        nothing, which is what `BidSummary.decision` documents.

        A verdict the current vocabulary does not recognise answers `None` rather than
        raising: 0004 renamed `go_with_open_items` out of the enum, and one unreadable row
        must not blank a company's dashboard.
        """
        if self.reviewed_decision is not None:
            return self.reviewed_decision
        try:
            return Decision((self.verdict or {}).get("decision"))
        except ValueError:
            return None


class BidDocumentRow(BaseModel):
    """One `documents` row, as much of it as starting and parsing a bid needs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str
    storage_path: str
    kind: DocumentKind
    status: DocumentStatus
    """Where the upload has got to (S2.2.3). Only `READY` documents may start a bid."""
    bid_id: str | None
    pages: int
    unread_pages: tuple[int, ...] = ()


def thread_id_of(bid_id: str) -> str:
    """The checkpointer's conversation key for a bid. One definition, used by both sides."""
    return f"{THREAD_ID_PREFIX}{bid_id}"


# -------------------------------------------------------------------------------- SQL

_BID_COLUMNS: Final[LiteralString] = """
    b.id, b.company_id, b.thread_id, b.ted_publication_number, b.title, b.source_language,
    b.status, b.failure_reason, b.problems, b.verdict, b.decision, b.created_at,
    b.updated_at,
    c.language as bidder_language
"""

"""Spliced into the selects below with an f-string, which ruff's S608 flags as query
construction. Every part is a module literal -- nothing from a request reaches these strings
-- and pyright's `LiteralString` check on each constant enforces that, so the rule is
silenced per statement (as `readmodel/documents.py` does) rather than worked around."""

INSERT_BID: Final[LiteralString] = """
insert into bids (id, company_id, thread_id, ted_publication_number, title, source_language,
                  status)
values (%(id)s, %(company_id)s, %(thread_id)s, %(notice_number)s, %(title)s,
        %(source_language)s, %(status)s)
"""

SELECT_BID: Final[LiteralString] = f"""
select {_BID_COLUMNS}
from bids b
join companies c on c.id = b.company_id
where b.company_id = %(company_id)s and b.id = %(bid_id)s
"""  # noqa: S608 -- module literals only

SELECT_BIDS: Final[LiteralString] = f"""
select {_BID_COLUMNS}
from bids b
join companies c on c.id = b.company_id
where b.company_id = %(company_id)s
order by b.created_at desc
limit %(limit)s
"""  # noqa: S608 -- module literals only

SELECT_UNFINISHED_BIDS: Final[LiteralString] = f"""
select {_BID_COLUMNS}
from bids b
join companies c on c.id = b.company_id
where b.status = any(%(statuses)s)
order by b.created_at
"""  # noqa: S608 -- module literals only
"""Deliberately unscoped: the startup resume spans every company. See the module."""

UPDATE_BID_STATUS: Final[LiteralString] = """
update bids
set status = %(status)s, updated_at = now()
where company_id = %(company_id)s and id = %(bid_id)s
"""

UPDATE_BID_FAILED: Final[LiteralString] = """
update bids
set status = %(status)s, failure_reason = %(reason)s, updated_at = now()
where company_id = %(company_id)s and id = %(bid_id)s
"""

UPDATE_BID_PROBLEMS: Final[LiteralString] = """
update bids
set problems = %(problems)s, updated_at = now()
where company_id = %(company_id)s and id = %(bid_id)s
"""

UPDATE_BID_VERDICT: Final[LiteralString] = """
update bids
set verdict = %(verdict)s, updated_at = now()
where company_id = %(company_id)s and id = %(bid_id)s
"""
"""S3.4.1 writes the agent's verdict here at scoring; S3.4.2 overwrites it with the
reviewer's final one. One jsonb column rather than a table, for the reason `problems` is
one: it is a projection of the graph state, read whole and never queried by field. The
`reviews` table is the separate, append-only record of *who decided what*."""

UPDATE_BID_DECISION: Final[LiteralString] = """
update bids
set decision = %(decision)s, updated_at = now()
where company_id = %(company_id)s and id = %(bid_id)s
"""

CLAIM_BID_FOR_REVIEW: Final[LiteralString] = """
update bids
set status = %(claimed)s, updated_at = now()
where company_id = %(company_id)s and id = %(bid_id)s and status = %(parked)s
"""
"""The 409 in S3.4.2, made atomic. A read-then-write would let two submissions both see
`awaiting_review` and both resume the graph; a conditional update lets exactly one row
change and the loser sees `rowcount == 0`. Migration 0006's column is not involved -- this
is the *status*, and moving it off `awaiting_review` is the claim."""

RELEASE_BID_TO_REVIEW: Final[LiteralString] = """
update bids
set status = %(status)s, failure_reason = %(reason)s, updated_at = now()
where company_id = %(company_id)s and id = %(bid_id)s
"""
"""Undoes `CLAIM_BID_FOR_REVIEW` when the resume it claimed for failed.

`failed` would be the obvious status and is a trap: it is terminal, it is not in
`UNFINISHED_STATUSES` so the startup resume skips it, and `claim_bid_for_review` only accepts
`awaiting_review` — so a review that failed on a transient pool timeout would leave the bid
dead, with the reviewer's submission sitting in its checkpoint and a permanent 409 in front of
the only endpoint that could finish it. Back to `awaiting_review` is the honest state: the
graph is still parked, and resubmitting is the affordance the product has."""

INSERT_REVIEW: Final[LiteralString] = """
insert into reviews (bid_id, company_id, decision, agent_verdict, final_verdict,
                     override_reason, reviewer_id)
values (%(bid_id)s, %(company_id)s, %(decision)s, %(agent_verdict)s, %(final_verdict)s,
        %(override_reason)s, %(reviewer_id)s)
"""
"""Append-only: a second review of the same bid would be a second row, never an update.
`reviewer_id` is nullable since 0006 and is `None` under dev auth -- see that migration for
why recording an unverified identity is worse than recording none."""

SELECT_COMPANY_LANGUAGE: Final[LiteralString] = """
select language from companies where id = %(company_id)s
"""

_DOCUMENT_COLUMNS: Final[LiteralString] = (
    "id, name, storage_path, kind, status, bid_id, pages, unread_pages"
)

SELECT_DOCUMENTS_BY_ID: Final[LiteralString] = f"""
select {_DOCUMENT_COLUMNS}
from documents
where company_id = %(company_id)s and id = any(%(document_ids)s)
order by name
"""  # noqa: S608 -- module literals only

SELECT_BID_DOCUMENTS: Final[LiteralString] = f"""
select {_DOCUMENT_COLUMNS}
from documents
where company_id = %(company_id)s and bid_id = %(bid_id)s
order by name
"""  # noqa: S608 -- module literals only

ATTACH_DOCUMENTS: Final[LiteralString] = """
update documents
set bid_id = %(bid_id)s
where company_id = %(company_id)s and id = any(%(document_ids)s) and bid_id is null
"""

SCOPED_STATEMENTS: Final[tuple[LiteralString, ...]] = (
    INSERT_BID,
    SELECT_BID,
    SELECT_BIDS,
    UPDATE_BID_STATUS,
    UPDATE_BID_FAILED,
    UPDATE_BID_PROBLEMS,
    UPDATE_BID_VERDICT,
    UPDATE_BID_DECISION,
    CLAIM_BID_FOR_REVIEW,
    RELEASE_BID_TO_REVIEW,
    INSERT_REVIEW,
    SELECT_DOCUMENTS_BY_ID,
    SELECT_BID_DOCUMENTS,
    ATTACH_DOCUMENTS,
)
"""Every statement that touches tenant data. A test asserts each carries the predicate."""


# ---------------------------------------------------------------------------- bids


async def create_bid(
    db: ConnectionSource,
    *,
    company_id: str,
    notice_number: str,
    title: str,
    source_language: str,
    bidder_language: str,
) -> BidRow:
    """Insert a `queued` bid on a fresh thread and return it as the graph will see it.

    The id is minted here rather than by the database because the thread id is derived
    from it and both go into the same insert.
    """
    bid_id = str(uuid.uuid4())
    async with db.connection() as conn:
        await conn.execute(
            INSERT_BID,
            {
                "id": bid_id,
                "company_id": company_id,
                "thread_id": thread_id_of(bid_id),
                "notice_number": notice_number,
                "title": title,
                "source_language": source_language,
                "status": BidStatus.QUEUED.value,
            },
        )
        record = await (
            await conn.execute(SELECT_BID, {"company_id": company_id, "bid_id": bid_id})
        ).fetchone()
    if record is None:
        raise BidReadModelError(f"bid {bid_id} was inserted but could not be read back")
    return _bid_row(record)


async def fetch_bid(db: ConnectionSource, *, company_id: str, bid_id: str) -> BidRow | None:
    """The bid, or `None` when there is no such bid for this company."""
    async with db.connection() as conn:
        record = await (
            await conn.execute(SELECT_BID, {"company_id": company_id, "bid_id": bid_id})
        ).fetchone()
    return None if record is None else _bid_row(record)


async def list_bids(db: ConnectionSource, *, company_id: str) -> list[BidRow]:
    """This company's bids, newest first, at most `MAX_BIDS_LISTED`."""
    async with db.connection() as conn:
        records = await (
            await conn.execute(
                SELECT_BIDS, {"company_id": company_id, "limit": MAX_BIDS_LISTED}
            )
        ).fetchall()
    return [_bid_row(record) for record in records]


async def unfinished_bids(db: ConnectionSource) -> list[BidRow]:
    """Every company's bids whose status says the graph should be running. Startup only."""
    statuses = sorted(status.value for status in UNFINISHED_STATUSES)
    async with db.connection() as conn:
        records = await (
            await conn.execute(SELECT_UNFINISHED_BIDS, {"statuses": statuses})
        ).fetchall()
    return [_bid_row(record) for record in records]


async def set_bid_status(
    db: ConnectionSource, *, company_id: str, bid_id: str, status: BidStatus
) -> None:
    """Record that the run has reached `status`. Raises if the bid is not this company's."""
    async with db.connection() as conn:
        cursor = await conn.execute(
            UPDATE_BID_STATUS,
            {"company_id": company_id, "bid_id": bid_id, "status": status.value},
        )
        _require_one_row(cursor.rowcount, bid_id)


async def mark_bid_failed(
    db: ConnectionSource, *, company_id: str, bid_id: str, reason: str
) -> None:
    """Terminal: `failed`, with a reason the dashboard can show. See migration 0003."""
    async with db.connection() as conn:
        cursor = await conn.execute(
            UPDATE_BID_FAILED,
            {
                "company_id": company_id,
                "bid_id": bid_id,
                "status": BidStatus.FAILED.value,
                "reason": reason,
            },
        )
        _require_one_row(cursor.rowcount, bid_id)


async def set_bid_problems(
    db: ConnectionSource, *, company_id: str, bid_id: str, problems: Sequence[Mapping[str, Any]]
) -> None:
    """Replace the bid's problem list with the graph's accumulated one."""
    async with db.connection() as conn:
        cursor = await conn.execute(
            UPDATE_BID_PROBLEMS,
            {"company_id": company_id, "bid_id": bid_id, "problems": Jsonb(list(problems))},
        )
        _require_one_row(cursor.rowcount, bid_id)


async def set_bid_verdict(
    db: ConnectionSource, *, company_id: str, bid_id: str, verdict: Mapping[str, Any]
) -> None:
    """Record the bid's verdict as the dashboard and the workspace read it.

    Takes the already-dumped mapping rather than a `Verdict`, so this module keeps its rule
    of importing nothing from `agent/` or `models/verdict`: the caller owns the contract,
    the projection owns the column.
    """
    async with db.connection() as conn:
        cursor = await conn.execute(
            UPDATE_BID_VERDICT,
            {"company_id": company_id, "bid_id": bid_id, "verdict": Jsonb(dict(verdict))},
        )
        _require_one_row(cursor.rowcount, bid_id)


async def claim_bid_for_review(db: ConnectionSource, *, company_id: str, bid_id: str) -> None:
    """Move the bid off `awaiting_review`, or refuse because it was never parked there.

    The one operation that makes "a second submission is 409" true under concurrency. A
    `BidStateError` here means either that someone else submitted first or that the bid is
    not waiting on a human at all; the router cannot tell the two apart and neither can the
    reviewer, so it says the same thing for both.
    """
    async with db.connection() as conn:
        cursor = await conn.execute(
            CLAIM_BID_FOR_REVIEW,
            {
                "company_id": company_id,
                "bid_id": bid_id,
                "claimed": BidStatus.APPLYING_REVIEW.value,
                "parked": BidStatus.AWAITING_REVIEW.value,
            },
        )
    if cursor.rowcount != 1:
        raise BidStateError(f"bid {bid_id} is not waiting for a review")


async def release_bid_to_review(
    db: ConnectionSource, *, company_id: str, bid_id: str, reason: str
) -> None:
    """Put a claimed bid back on `awaiting_review` and record why. See the statement."""
    async with db.connection() as conn:
        cursor = await conn.execute(
            RELEASE_BID_TO_REVIEW,
            {
                "company_id": company_id,
                "bid_id": bid_id,
                "status": BidStatus.AWAITING_REVIEW.value,
                "reason": reason,
            },
        )
        _require_one_row(cursor.rowcount, bid_id)


async def record_review(
    db: ConnectionSource,
    *,
    company_id: str,
    bid_id: str,
    decision: Decision,
    agent_verdict: Mapping[str, Any] | None,
    final_verdict: Mapping[str, Any],
    override_reason: str | None,
    reviewer_id: str | None = None,
) -> None:
    """Append the audit row and set the bid's final decision, in one transaction.

    One transaction because the pair is the record: a `bids.decision` with no `reviews` row
    behind it is a verdict nobody can audit, and a `reviews` row the dashboard does not
    reflect is an audit of something that never happened. psycopg commits the connection
    when the `async with` block leaves without an exception, so the two statements either
    both land or neither does.

    `agent_verdict` is nullable in this signature and not in the column: a bid can only have
    reached a review through `score_verdict`, so `None` means a caller assembled the record
    by hand, and `'null'::jsonb` records that honestly rather than inventing a verdict.
    """
    async with db.connection() as conn:
        await conn.execute(
            INSERT_REVIEW,
            {
                "bid_id": bid_id,
                "company_id": company_id,
                "decision": decision.value,
                "agent_verdict": Jsonb(dict(agent_verdict) if agent_verdict else None),
                "final_verdict": Jsonb(dict(final_verdict)),
                "override_reason": override_reason,
                "reviewer_id": reviewer_id,
            },
        )
        cursor = await conn.execute(
            UPDATE_BID_DECISION,
            {"company_id": company_id, "bid_id": bid_id, "decision": decision.value},
        )
        _require_one_row(cursor.rowcount, bid_id)


# ----------------------------------------------------------------- companies, documents


async def company_language(db: ConnectionSource, *, company_id: str) -> str | None:
    """The company's bidder language, or `None` when no such company row exists.

    Also the existence check `POST /bids` needs: with `AUTH_MODE=dev` the header can name a
    UUID that has no row, and the bid's foreign key would refuse it less readably.
    """
    async with db.connection() as conn:
        record = await (
            await conn.execute(SELECT_COMPANY_LANGUAGE, {"company_id": company_id})
        ).fetchone()
    return None if record is None else str(record["language"])


async def documents_by_id(
    db: ConnectionSource, *, company_id: str, document_ids: Sequence[str]
) -> list[BidDocumentRow]:
    """The company's rows among `document_ids`. Ids of other companies are simply absent."""
    async with db.connection() as conn:
        records = await (
            await conn.execute(
                SELECT_DOCUMENTS_BY_ID,
                {"company_id": company_id, "document_ids": _uuids(document_ids)},
            )
        ).fetchall()
    return [_document_row(record) for record in records]


async def bid_documents(
    db: ConnectionSource, *, company_id: str, bid_id: str
) -> list[BidDocumentRow]:
    """The documents attached to a bid, in name order — what `parse_docs` reads."""
    async with db.connection() as conn:
        records = await (
            await conn.execute(
                SELECT_BID_DOCUMENTS, {"company_id": company_id, "bid_id": bid_id}
            )
        ).fetchall()
    return [_document_row(record) for record in records]


async def attach_documents(
    db: ConnectionSource, *, company_id: str, bid_id: str, document_ids: Sequence[str]
) -> None:
    """Attach unattached documents to the bid; every id must take, or none should have.

    The router checked the rows a moment ago, so a shortfall here means a concurrent start
    claimed one of them. That is a `BidStateError`, not a silent partial bid.
    """
    if not document_ids:
        raise BidStateError("a bid needs at least one document to parse")
    async with db.connection() as conn:
        cursor = await conn.execute(
            ATTACH_DOCUMENTS,
            {"company_id": company_id, "bid_id": bid_id, "document_ids": _uuids(document_ids)},
        )
    if cursor.rowcount != len(document_ids):
        raise BidStateError(
            f"only {cursor.rowcount} of {len(document_ids)} documents could be attached to "
            f"bid {bid_id}: one was claimed by another bid first"
        )


# ------------------------------------------------------------------------- row readers


def _bid_row(record: Mapping[str, Any]) -> BidRow:
    """psycopg hands back `UUID` and `datetime` objects; the row model speaks strings."""
    return BidRow(
        id=str(record["id"]),
        company_id=str(record["company_id"]),
        thread_id=str(record["thread_id"]),
        notice_number=_optional_str(record["ted_publication_number"]),
        title=str(record["title"]),
        source_language=_optional_str(record["source_language"]),
        bidder_language=str(record["bidder_language"]),
        status=BidStatus(record["status"]),
        failure_reason=_optional_str(record.get("failure_reason")),
        problems=list(record.get("problems") or []),
        verdict=record.get("verdict"),
        reviewed_decision=_optional_decision(record.get("decision")),
        created_at=record.get("created_at"),
        updated_at=record.get("updated_at"),
    )


def _document_row(record: Mapping[str, Any]) -> BidDocumentRow:
    return BidDocumentRow(
        id=str(record["id"]),
        name=str(record["name"]),
        storage_path=str(record["storage_path"]),
        kind=DocumentKind(record["kind"]),
        status=DocumentStatus(record["status"]),
        bid_id=_optional_str(record["bid_id"]),
        pages=int(record["pages"]),
        unread_pages=tuple(int(page) for page in record.get("unread_pages") or ()),
    )


def _optional_decision(value: object) -> Decision | None:
    """`bids.decision` as the contract knows it, or `None` for a word it no longer does."""
    try:
        return Decision(value)
    except ValueError:
        return None


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _uuids(ids: Sequence[str]) -> list[uuid.UUID]:
    """Typed for `= any(%s)`: psycopg sends a list of `str` as `text[]`, which Postgres
    will not compare with a `uuid` column; a list of `UUID` goes as `uuid[]`."""
    return [uuid.UUID(identifier) for identifier in ids]


def _require_one_row(rowcount: int, bid_id: str) -> None:
    if rowcount != 1:
        raise BidNotFoundError(f"bid {bid_id} does not exist for this company")
