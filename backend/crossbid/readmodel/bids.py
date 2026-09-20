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

import logging
import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Final, LiteralString

from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from crossbid.db import ConnectionSource
from crossbid.models.tender import BidStatus, BidSummary, DocumentKind
from crossbid.models.verdict import Decision
from crossbid.readmodel.documents import DocumentStatus
from crossbid.readmodel.pagination import Page, PageCursor

logger = logging.getLogger(__name__)

THREAD_ID_PREFIX: Final = "bid:"
"""The LangGraph thread a bid runs on is `bid:{id}`; chat (F3.5) will be `bid:{id}:chat`."""

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

DELETABLE_STATUSES: Final = frozenset(BidStatus) - UNFINISHED_STATUSES
"""What a bidder may delete: everything the graph is not in the middle of writing.

Derived rather than listed, so a status added to one set cannot be forgotten in the other. A
run in flight holds an `asyncio.Task` still inserting requirements and matrix rows, and
deleting the bid under it would fail those inserts on a foreign key half way through a paid
run — so the deletable states are the parked one and the two finished ones."""

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
    buyer: str | None = None
    deadline: datetime | None = None
    deadline_utc_offset_minutes: int | None = None
    open_items: int = 0
    """Only `list_bids` fills this: see `SELECT_BIDS`. A bid read on its own carries its whole
    matrix, so the caller counts what it already has rather than paying for a subquery."""
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
            buyer=self.buyer,
            source_language=self.source_language,
            deadline=self.deadline,
            deadline_utc_offset_minutes=self.deadline_utc_offset_minutes,
            status=self.status,
            decision=self.decision,
            open_items=self.open_items,
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
    pages: int
    unread_pages: tuple[int, ...] = ()
    searchable: bool | None = None
    """A retrieval tool can reach this document's text — or `None`, meaning nobody asked.

    False for every document of a bid analysed before `a55d14b` (2026-09-15), whose pack was
    parsed and extracted from without a searchable copy being kept. That is invisible
    everywhere else, because nothing failed (ADR-0098).

    **The third state is the point.** Only `bid_documents` selects the column; `documents_by_id`
    does not, and its two callers check ids and nothing else. Defaulting to `False` there would
    hand a future reader "this document is not searchable" as though it had been looked up,
    which is the shape of the defect this field exists to surface."""


def thread_id_of(bid_id: str) -> str:
    """The checkpointer's conversation key for a bid. One definition, used by both sides."""
    return f"{THREAD_ID_PREFIX}{bid_id}"


# -------------------------------------------------------------------------------- SQL

_BID_COLUMNS: Final[LiteralString] = """
    b.id, b.company_id, b.thread_id, b.ted_publication_number, b.title, b.source_language,
    b.buyer, b.deadline, b.deadline_utc_offset_minutes,
    b.status, b.failure_reason, b.problems, b.verdict, b.decision, b.created_at,
    b.updated_at,
    coalesce(b.bidder_language, c.language) as bidder_language
"""

_OPEN_ITEMS: Final[LiteralString] = """
    (select count(*) from matrix_rows m
      where m.company_id = %(company_id)s and m.bid_id = b.id
        and m.status in ('partially_supported', 'unsupported')) as open_items
"""
"""What the dashboard counts per bid (S4.4.1). A correlated subquery rather than a join with
a `group by`, because the outer query is already bounded at `MAX_BIDS_LISTED` and a left join
onto a table with one row per requirement would make the bid list's row count depend on the
size of its matrices.

**It carries the tenant parameter itself rather than leaning on `b.company_id`.** The two are
the same value — the outer query pins `b` to the parameter — but the fragment is then scoped
on its own terms rather than by where it happens to be spliced, which is what
`test_the_startup_query_is_the_one_deliberately_unscoped_statement` insists on for every
statement in this module. That guard caught this subquery written the other way (ADR-0009:
the API connects as a `BYPASSRLS` role, so a missing predicate is the whole of a leak).

The statuses are spelled out rather than derived from `RowStatus`: `LiteralString` is what
keeps a run-time value out of this SQL, and `test_bids_readmodel.py` asserts the two agree."""

"""Spliced into the selects below with an f-string, which ruff's S608 flags as query
construction. Every part is a module literal -- nothing from a request reaches these strings
-- and pyright's `LiteralString` check on each constant enforces that, so the rule is
silenced per statement (as `readmodel/documents.py` does) rather than worked around."""

INSERT_BID: Final[LiteralString] = """
insert into bids (id, company_id, thread_id, ted_publication_number, title, source_language,
                  bidder_language, buyer, deadline, deadline_utc_offset_minutes, status)
values (%(id)s, %(company_id)s, %(thread_id)s, %(notice_number)s, %(title)s,
        %(source_language)s, %(bidder_language)s, %(buyer)s, %(deadline)s, %(deadline_offset)s,
        %(status)s)
"""
"""Writes the bidder language **onto the bid**, which it did not until migration 0011.

The argument was taken and dropped, and every read answered with `companies.language` instead —
so an analysis written in German relabelled itself the moment its company switched to English,
in the workspace, in the chat preamble and in any resumed run. A bid is a thing that happened;
the language it happened in is a property of it, not of the account's current preference."""

SELECT_BID: Final[LiteralString] = f"""
select {_BID_COLUMNS}
from bids b
join companies c on c.id = b.company_id
where b.company_id = %(company_id)s and b.id = %(bid_id)s
"""  # noqa: S608 -- module literals only

SELECT_BIDS: Final[LiteralString] = f"""
select {_BID_COLUMNS}, {_OPEN_ITEMS}
from bids b
join companies c on c.id = b.company_id
where b.company_id = %(company_id)s
order by b.created_at desc, b.id desc
limit %(limit)s
"""  # noqa: S608 -- module literals only
"""The dashboard's first page, and the only query that carries `open_items`: `SELECT_BID`
answers a workspace that already holds every row and can count them itself.

`b.id desc` joins the ordering at M13, so the tie-break between two bids started in the same
microsecond runs the same way as the cursor comparison below."""

SELECT_BIDS_AFTER: Final[LiteralString] = f"""
select {_BID_COLUMNS}, {_OPEN_ITEMS}
from bids b
join companies c on c.id = b.company_id
where b.company_id = %(company_id)s
  and (b.created_at, b.id) < (%(after_created_at)s, %(after_id)s)
order by b.created_at desc, b.id desc
limit %(limit)s
"""  # noqa: S608 -- module literals only
"""Every dashboard page after the first (M13). The predicate names the last row the caller
saw, so a bid started between two requests changes what is above the boundary and nothing
about where the boundary is — which an `offset` cannot say."""

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

UPDATE_BID_DEADLINE_IF_UNSET: Final[LiteralString] = """
update bids
set deadline = %(deadline)s,
    deadline_utc_offset_minutes = %(deadline_offset)s,
    updated_at = now()
where company_id = %(company_id)s and id = %(bid_id)s and deadline is null
"""
"""S3.2.2 — the deadline TED published, written only where the bidder gave none.

`and deadline is null` is the whole point of the statement. The bidder types the deadline
from the notice PDF and it carries an **hour**; TED publishes a date and never a time
(ADR-0043). So the one the bidder gave is strictly better information, and a notice fetched
later in the run must not overwrite it — which is what an unconditional update would do
every time a bid was resumed from its checkpoint.

A zero row count therefore means "already set", not "no such bid", so this is the one
updater here that does not call `_require_one_row`."""

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
    "documents.id, documents.name, documents.storage_path, documents.kind, "
    "documents.status, documents.pages, documents.unread_pages"
)
"""Qualified, because `SELECT_BID_DOCUMENTS` joins `bid_documents` since ADR-0103 and an
unqualified `id` would be ambiguous the day another column is added to either table."""

SELECT_DOCUMENTS_BY_ID: Final[LiteralString] = f"""
select {_DOCUMENT_COLUMNS}
from documents
where documents.company_id = %(company_id)s and documents.id = any(%(document_ids)s)
order by documents.name
"""  # noqa: S608 -- module literals only

SELECT_BID_DOCUMENTS: Final[LiteralString] = f"""
select {_DOCUMENT_COLUMNS},
       exists (
           select 1
           from tender_chunks
           where tender_chunks.document_id = documents.id
             and tender_chunks.company_id = documents.company_id
             and tender_chunks.embedding is not null
       ) as searchable
from documents
join bid_documents
  on bid_documents.document_id = documents.id
 and bid_documents.company_id = documents.company_id
where documents.company_id = %(company_id)s and bid_documents.bid_id = %(bid_id)s
order by documents.name
"""  # noqa: S608 -- module literals only
"""The bid's pack, and whether a retrieval tool can reach each document.

**Read with the document rather than by a query of its own.** `GET /bids/{id}` is polled every
two seconds and ADR-0093 spent real work getting that path down to three reads; this is a
correlated `exists` on an indexed column inside a select that was already running.

**Only in this statement, not in the shared column list.** Putting it there made
`_DOCUMENT_COLUMNS` a constant containing the word `select` with no tenant predicate of its
own, and `test_the_startup_query_is_the_one_deliberately_unscoped_statement` read it as an
unscoped statement — correctly, since the guard cannot know a fragment from a query. The
subquery is scoped by the row it correlates to, and that row is scoped by the `where` below.
"""

DELETE_BID: Final[LiteralString] = """
delete from bids
where id = %(bid_id)s and company_id = %(company_id)s and status = any(%(statuses)s)
returning id
"""
"""Scoped by company *and* by a status the graph is not writing to.

The router refuses a running bid with a 409 first, which is what gives the bidder a sentence to
act on. This clause is that rule written where a race cannot get around it: a run that starts
between the router's read and this write finds no row to delete."""

ATTACH_DOCUMENTS: Final[LiteralString] = """
insert into bid_documents (bid_id, document_id, company_id)
select %(bid_id)s, documents.id, %(company_id)s
from documents
where documents.company_id = %(company_id)s and documents.id = any(%(document_ids)s)
on conflict (bid_id, document_id) do nothing
"""
"""Cites documents from a bid, without taking them from anyone (ADR-0103).

`insert ... select from documents` rather than `insert ... values`: the tenant predicate then
decides which rows exist to insert at all, so an id belonging to another company inserts
nothing and `attach_documents`' `rowcount` check refuses the whole call. That is the same
guarantee the old `and bid_id is null` gave, arrived at for a better reason -- it used to
double as the one-bid-per-document rule, which is exactly the rule being removed.

`on conflict do nothing` so a retried attach is a no-op rather than a `UniqueViolation`."""

SCOPED_STATEMENTS: Final[tuple[LiteralString, ...]] = (
    SELECT_BIDS_AFTER,
    INSERT_BID,
    SELECT_BID,
    SELECT_BIDS,
    UPDATE_BID_STATUS,
    UPDATE_BID_FAILED,
    UPDATE_BID_DEADLINE_IF_UNSET,
    UPDATE_BID_PROBLEMS,
    UPDATE_BID_VERDICT,
    UPDATE_BID_DECISION,
    CLAIM_BID_FOR_REVIEW,
    RELEASE_BID_TO_REVIEW,
    INSERT_REVIEW,
    SELECT_DOCUMENTS_BY_ID,
    SELECT_BID_DOCUMENTS,
    ATTACH_DOCUMENTS,
    DELETE_BID,
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
    buyer: str | None = None,
    deadline: datetime | None = None,
    deadline_utc_offset_minutes: int | None = None,
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
                "bidder_language": bidder_language,
                "buyer": buyer,
                "deadline": deadline,
                "deadline_offset": deadline_utc_offset_minutes,
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


async def list_bids(
    db: ConnectionSource, *, company_id: str, limit: int, after: PageCursor | None = None
) -> Page[BidRow]:
    """One page of this company's bids, newest first (M13).

    The silent cap this replaced is the finding: the dashboard truncated at 200 with nothing
    in the response saying so, and the constant's own docstring named a cursor as the answer.
    `limit + 1` rows are asked for so `Page.of` can tell a full page from a last one.
    """
    if after is None:
        statement: LiteralString = SELECT_BIDS
        params: dict[str, object] = {"company_id": company_id, "limit": limit + 1}
    else:
        statement = SELECT_BIDS_AFTER
        params = {
            "company_id": company_id,
            "after_created_at": after.created_at,
            "after_id": after.row_id,
            "limit": limit + 1,
        }
    async with db.connection() as conn:
        records = await (await conn.execute(statement, params)).fetchall()
    return Page.of([_bid_row(record) for record in records], limit=limit, key=_cursor_key)


def _cursor_key(row: BidRow) -> tuple[datetime, uuid.UUID]:
    """Where a page boundary sits, from the row that ends it.

    `created_at` is optional on `BidRow` because a bid can be constructed before the column is
    read; `SELECT_BIDS` always selects it, so `None` here means the query and the model have
    drifted apart. Loud rather than a cursor that silently points nowhere.
    """
    if row.created_at is None:  # pragma: no cover -- SELECT_BIDS always reads the column
        raise BidReadModelError(f"Bid {row.id} was listed without created_at; no cursor.")
    return row.created_at, uuid.UUID(row.id)


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


async def set_bid_deadline_if_unset(
    db: ConnectionSource,
    *,
    company_id: str,
    bid_id: str,
    deadline: datetime,
    deadline_utc_offset_minutes: int | None,
) -> bool:
    """Write TED's deadline onto the bid unless one is already there (S3.2.2).

    Answers whether it was written, so a caller can log which source the dashboard is now
    counting down from. Never raises for a bid that already had one: that is the expected
    case whenever the bidder typed the hour on the start form.
    """
    async with db.connection() as conn:
        cursor = await conn.execute(
            UPDATE_BID_DEADLINE_IF_UNSET,
            {
                "company_id": company_id,
                "bid_id": bid_id,
                "deadline": deadline,
                "deadline_offset": deadline_utc_offset_minutes,
            },
        )
        return cursor.rowcount == 1


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
    reflect is an audit of something that never happened.

    The transaction is explicit, and has to be. Every pooled connection carries
    `autocommit=True` (`db.pool_connection_kwargs`), so leaving the `async with` block
    commits nothing -- each statement had already committed on its own. Before this,
    `INSERT_REVIEW` landed and a `rowcount` of zero on the update then raised, leaving an
    orphan `reviews` row for a decision the dashboard never showed. `conn.transaction()`
    opens a real block under autocommit and rolls it back when the body raises.

    `agent_verdict` is nullable in this signature and not in the column: a bid can only have
    reached a review through `score_verdict`, so `None` means a caller assembled the record
    by hand, and `'null'::jsonb` records that honestly rather than inventing a verdict.
    """
    async with db.connection() as conn, conn.transaction():
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


async def delete_bid(db: ConnectionSource, *, company_id: str, bid_id: str) -> bool:
    """Delete one analysis, keep the papers it was made from. `False` when nothing was deleted.

    `False` covers an unknown id, another company's id, and a bid whose graph is still running
    — all three of which the router tells apart for the bidder before reaching this.

    **The documents were never the bid's to take, since ADR-0103.** Everything else a bid owns
    is meant to go with it: requirements, matrix rows, reviews and feedback all cascade, and
    they *are* the analysis. Its documents are not — they are the bidder's own files, they may
    be cited by other analyses at the same time, and their bytes live in Storage where this
    statement cannot reach. Only the `bid_documents` links cascade, which removes the citation
    and nothing else. This used to need a `DETACH_DOCUMENTS` statement and a transaction around
    the pair, because `documents.bid_id` cascaded and would have deleted the bidder's uploads.

    **Its passages survive too**, which is the half worth stating: `tender_chunks.bid_id` was
    `references bids (id) on delete cascade` until 0012, so deleting an analysis deleted its
    corpus. A shared corpus must not work that way — another live analysis is searching it, and
    retrieval returning nothing is not an error anywhere in this system, so the damage would be
    silent.

    Its spend stays as well, by a schema decision rather than one made here: migration 0010
    made `llm_usage.bid_id` `set null`, so the cost survives with the bid's name gone.

    The checkpoint the run lived in is **not** deleted here — `routers/bids.py` asks LangGraph
    for that with `adelete_thread`, because those tables are its schema and not ours.
    """
    async with db.connection() as conn:
        record = await (
            await conn.execute(
                DELETE_BID,
                {
                    "bid_id": bid_id,
                    "company_id": company_id,
                    "statuses": sorted(status.value for status in DELETABLE_STATUSES),
                },
            )
        ).fetchone()
    return record is not None


async def attach_documents(
    db: ConnectionSource, *, company_id: str, bid_id: str, document_ids: Sequence[str]
) -> None:
    """Attach unattached documents to the bid; every id must take, or none should have.

    The router checked the rows a moment ago, so a shortfall here means a concurrent start
    claimed one of them. That is a `BidStateError`, not a silent partial bid.

    The check runs inside the transaction, which is what makes the sentence above true.
    Pooled connections are `autocommit=True`, so raising after the statement would leave the
    rows that *did* match cited by a bid the router then marks `failed` -- a half-made
    analysis holding some of its pack. That is merely untidy since ADR-0103, where it used to
    be permanent: `ATTACH_DOCUMENTS` required `bid_id is null`, so a partially attached
    document could never be attached to anything again.
    """
    if not document_ids:
        raise BidStateError("a bid needs at least one document to parse")
    async with db.connection() as conn, conn.transaction():
        cursor = await conn.execute(
            ATTACH_DOCUMENTS,
            {"company_id": company_id, "bid_id": bid_id, "document_ids": _uuids(document_ids)},
        )
        if cursor.rowcount != len(document_ids):
            raise BidStateError(
                f"only {cursor.rowcount} of {len(document_ids)} documents could be attached "
                f"to bid {bid_id}: one was claimed by another bid first"
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
        buyer=_optional_str(record.get("buyer")),
        deadline=record.get("deadline"),
        deadline_utc_offset_minutes=_optional_int(record.get("deadline_utc_offset_minutes")),
        open_items=int(record.get("open_items") or 0),
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
        pages=int(record["pages"]),
        unread_pages=tuple(int(page) for page in record.get("unread_pages") or ()),
        searchable=_optional_bool(record.get("searchable")),
    )


def _optional_bool(value: object) -> bool | None:
    """`None` when the statement did not select the column, never a default that reads true."""
    return None if value is None else bool(value)


def _optional_decision(value: object) -> Decision | None:
    """`bids.decision` as the contract knows it, or `None` for a word it no longer does."""
    try:
        return Decision(value)
    except ValueError:
        return None


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _optional_int(value: object) -> int | None:
    return None if value is None else int(value)  # type: ignore[call-overload]


def _uuids(ids: Sequence[str]) -> list[uuid.UUID]:
    """Typed for `= any(%s)`: psycopg sends a list of `str` as `text[]`, which Postgres
    will not compare with a `uuid` column; a list of `UUID` goes as `uuid[]`."""
    return [uuid.UUID(identifier) for identifier in ids]


def _require_one_row(rowcount: int, bid_id: str) -> None:
    if rowcount != 1:
        raise BidNotFoundError(f"bid {bid_id} does not exist for this company")
