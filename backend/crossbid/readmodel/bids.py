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
    {DocumentKind.TENDER_DOCUMENT, DocumentKind.TENDER_NOTICE}
)
"""What a bid may be started from. A company's own evidence pack is never parsed as a
tender, however it was uploaded."""


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
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def summary(self) -> BidSummary:
        """The dashboard's shape, from `models/`. Verdict fields stay `None` until F3.4."""
        return BidSummary(
            id=self.id,
            company_id=self.company_id,
            ted_publication_number=self.notice_number,
            title=self.title,
            source_language=self.source_language,
            status=self.status,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


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
    b.status, b.failure_reason, b.problems, b.created_at, b.updated_at,
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


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _uuids(ids: Sequence[str]) -> list[uuid.UUID]:
    """Typed for `= any(%s)`: psycopg sends a list of `str` as `text[]`, which Postgres
    will not compare with a `uuid` column; a list of `UUID` goes as `uuid[]`."""
    return [uuid.UUID(identifier) for identifier in ids]


def _require_one_row(rowcount: int, bid_id: str) -> None:
    if rowcount != 1:
        raise BidNotFoundError(f"bid {bid_id} does not exist for this company")
