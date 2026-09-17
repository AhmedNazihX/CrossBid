"""S2.2.3 — the `documents` table: one row per upload, and the status a bidder polls.

This is a projection in the sense `docs/project-plan.md` gives the word: the API writes it as
the ingestion pipeline moves, and the browser reads it through `routers/documents.py`. Nothing
here is derived from a LangGraph checkpoint — a document's lifecycle ends before any graph
starts — so unlike `bids` there is no second source of truth to disagree with.

**Every statement carries its tenant scope in its own text.** The API connects as Supabase's
`postgres` role, which has `BYPASSRLS = true`, so row-level security would be silently inert
and the `company_id = %(company_id)s` written into each constant below is the *only* thing
between two companies (ADR-0009). The constants are `Final[LiteralString]` with no
interpolation at all — not even of the column list, which is why it is written out six
times. `LiteralString` is what psycopg's `execute` accepts and what pyright enforces, so a
statement assembled at run time cannot be passed; an f-string would turn a literal into a
plain `str` and forfeit exactly that guarantee. `SCOPED_STATEMENTS` lists the seven so one test
asserts the scope on all of them, and another asserts their column lists are identical.

**One statement is deliberately not scoped, and is named for it.**
`FAIL_INTERRUPTED_DOCUMENTS_SQL` runs once at startup over every company's rows, the
way `bids.SELECT_UNFINISHED_BIDS` does. It answers a question about the process rather
than about a tenant, it is never reachable from a request, and it returns a count rather
than a row.

Two things a reader might otherwise take for oversights:

* **A read for another company's id returns `None`, never an error.** The router turns that
  into HTTP 404. A distinct "forbidden" answer would confirm that the document exists, which
  is the leak S2.2.2 is about; the read model does not know the difference and must not.
* **`bid_id` is not an argument of `insert`.** A document is uploaded before the bid it will
  belong to exists — S4.3.1's flow uploads the pack and then presses Start — and S3.1.1's
  `POST /bids` attaches the documents by id. The column is read back on every record so the
  browser can show the link once it is set; it is never written from here.

The status values are defined here rather than in `crossbid/models/`, next to the column
they constrain, because nothing below the read model reads them.
`migrations/0002_documents_status.sql` carries the matching check constraint and
`tests/unit/test_documents_readmodel.py` asserts the two lists are identical (0001's parity
guard only scans its own file).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from enum import StrEnum
from typing import Any, Final, LiteralString, Protocol, Self

from psycopg import AsyncConnection
from psycopg.rows import DictRow
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from crossbid.models import DocumentKind
from crossbid.readmodel.pagination import Page, PageCursor

logger = logging.getLogger(__name__)


class DocumentStatus(StrEnum):
    """How far an upload has got. The browser polls it, so the names are user-visible.

    Linear on the happy path: `UPLOADED` (the row exists; the bytes may still be on their way
    to Storage) → `PARSED` (every page is accounted for, unread ones listed) → `EMBEDDED`
    (chunks and vectors are in the chunk table) → `READY` (the agent may use it). `FAILED` is
    terminal and always carries a `failure_reason`.
    """

    UPLOADED = "uploaded"
    PARSED = "parsed"
    EMBEDDED = "embedded"
    READY = "ready"
    FAILED = "failed"


class ReadModelError(RuntimeError):
    """A row could not be written or read back. Never carries a key, a URL or a DSN."""


class DocumentRecord(BaseModel):
    """One `documents` row, as the pipeline writes it and the router reads it.

    Frozen: a transition returns a new record from the database's `returning` clause rather
    than editing the one in hand, so what the caller holds is always what the row says.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: uuid.UUID
    company_id: uuid.UUID
    bid_id: uuid.UUID | None = Field(
        default=None, description="Null until S3.1.1 attaches the document to a bid"
    )
    kind: DocumentKind
    name: str = Field(min_length=1, description="The filename the bidder chose, verbatim")
    storage_path: str = Field(min_length=1, description="The sanitised Storage key (S2.2.2)")
    status: DocumentStatus
    failure_reason: str | None = None
    pages: int = Field(ge=0, description="Total pages once parsed; 0 before that")
    unread_pages: tuple[int, ...] = Field(
        default=(), description="Pages with no text layer, listed rather than dropped (S2.1.1)"
    )
    flagged_chunks: tuple[int, ...] = Field(
        default=(),
        description=(
            "Chunk numbers the injection guard withheld (S2.3.1). Listed rather than "
            "silently dropped: a document whose text was partly kept out of the corpus is "
            "something a reviewer has to be told about, because it changes what 'no "
            "evidence found' means for it."
        ),
    )
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _failed_needs_a_reason(self) -> Self:
        """Mirrors `documents_failed_needs_reason_check`; a direct SQL write bypasses this."""
        is_failed = self.status is DocumentStatus.FAILED
        if is_failed != (self.failure_reason is not None):
            raise ValueError(
                "a failed document must carry a failure_reason and no other status may"
            )
        return self


class ConnectionSource(Protocol):
    """Something that lends a pooled connection; `crossbid.db.Database` satisfies it.

    The same three lines as `ingestion.embeddings.ConnectionSource`, restated rather than
    imported so the read model does not depend on the ingestion package for a type. The one
    shared home would be `crossbid.db`, which the story does not own.
    """

    def connection(self) -> AbstractAsyncContextManager[AsyncConnection[DictRow]]: ...


# ------------------------------------------------------------------------- statements

DOCUMENT_COLUMNS: Final[LiteralString] = (
    "id, company_id, bid_id, kind, name, storage_path, status, failure_reason, "
    "pages, unread_pages, flagged_chunks, created_at, updated_at"
)
"""Every column `DocumentRecord` reads. Written out verbatim in each statement below rather
than spliced in, so the statements stay literals (module docstring); a test asserts that each
of them contains this exact text, which is what keeps the six copies from drifting."""

INSERT_DOCUMENT_SQL: Final[LiteralString] = """
insert into documents (id, company_id, kind, name, storage_path, status)
values (%(id)s, %(company_id)s, %(kind)s, %(name)s, %(storage_path)s, 'uploaded')
returning id, company_id, bid_id, kind, name, storage_path, status, failure_reason,
pages, unread_pages, flagged_chunks, created_at, updated_at
"""
"""The first status is written, not left to the column default, so the statement says what
the row will read back. `where` is not needed: the tenant is the row being created."""

MARK_PARSED_SQL: Final[LiteralString] = """
update documents
set status = 'parsed', pages = %(pages)s, unread_pages = %(unread_pages)s, updated_at = now()
where id = %(document_id)s and company_id = %(company_id)s
returning id, company_id, bid_id, kind, name, storage_path, status, failure_reason,
pages, unread_pages, flagged_chunks, created_at, updated_at
"""

MARK_STATUS_SQL: Final[LiteralString] = """
update documents
set status = %(status)s, updated_at = now()
where id = %(document_id)s and company_id = %(company_id)s
returning id, company_id, bid_id, kind, name, storage_path, status, failure_reason,
pages, unread_pages, flagged_chunks, created_at, updated_at
"""
"""`embedded` and `ready`, the two transitions that carry nothing but the new status.
`failed` has its own statement because the check constraint demands a reason with it."""

SET_FLAGGED_CHUNKS_SQL: Final[LiteralString] = """
update documents
set flagged_chunks = %(flagged_chunks)s, updated_at = now()
where id = %(document_id)s and company_id = %(company_id)s
returning id, company_id, bid_id, kind, name, storage_path, status, failure_reason,
pages, unread_pages, flagged_chunks, created_at, updated_at
"""
"""S2.3.1 — the chunk numbers the injection guard refused.

**It does not touch `status`, and that is deliberate.** Every kind is scanned, including the
tender documents that are never embedded at upload, so folding this into `mark_embedded`
would have walked a tender pack through a status it never reaches — and the poller a bidder
is watching reports that status. The numbers exist only after chunking, which is why this is
not part of `mark_parsed` either."""

MARK_FAILED_SQL: Final[LiteralString] = """
update documents
set status = 'failed', failure_reason = %(reason)s, updated_at = now()
where id = %(document_id)s and company_id = %(company_id)s
returning id, company_id, bid_id, kind, name, storage_path, status, failure_reason,
pages, unread_pages, flagged_chunks, created_at, updated_at
"""

FAIL_INTERRUPTED_DOCUMENTS_SQL: Final[LiteralString] = """
update documents
set status = 'failed', failure_reason = %(reason)s, updated_at = now()
where status in ('uploaded', 'parsed')
  and updated_at < now() - make_interval(secs => %(stale_seconds)s)
"""
"""Every company's documents that a restart left mid-pipeline, marked terminal.

Unscoped on purpose -- see the module docstring. `embedded` is excluded although it is also
not terminal: it means the chunks are written and only `mark_ready` is outstanding, which is
one statement, so a row sitting there is a bug rather than an interruption and should not be
quietly buried. The age test is what keeps the sweep off a document that is being processed
right now by a worker that is still alive.

`make_interval` rather than an interpolated interval literal: the constant has to stay a
`LiteralString` for psycopg and for pyright, and an f-string would forfeit exactly that.
"""

SELECT_DOCUMENT_SQL: Final[LiteralString] = """
select id, company_id, bid_id, kind, name, storage_path, status, failure_reason,
pages, unread_pages, flagged_chunks, created_at, updated_at
from documents
where id = %(document_id)s and company_id = %(company_id)s
"""

DELETE_DOCUMENT_SQL: Final[LiteralString] = """
delete from documents
where id = %(document_id)s and company_id = %(company_id)s and bid_id is null
returning id
"""
"""Scoped by company *and* by `bid_id is null`, so the statement itself is the guarantee.

The router refuses an attached document with a 409 before it gets here, which is what gives
the bidder a sentence to act on. This clause is the same rule written where a race cannot get
around it: a bid started between the router's read and this write finds no row to delete, the
delete reports nothing deleted, and the file stays with the run that cites it.

`company_chunks` and `tender_chunks` cascade on `documents (id)` (migration 0001), so the
document's text leaves the corpus with it and no orphaned embedding can be retrieved after."""

LIST_DOCUMENTS_SQL: Final[LiteralString] = """
select id, company_id, bid_id, kind, name, storage_path, status, failure_reason,
pages, unread_pages, flagged_chunks, created_at, updated_at
from documents
where company_id = %(company_id)s
order by created_at desc, id desc
limit %(limit)s
"""
"""The first page (M13). It had no limit at all, which is a query whose cost is a function of
how long the account has been used: a bidder who has run twenty packs asked for six hundred
rows on a page that shows the newest few.

`id desc` rather than the `id` it used to end with, so the tie-break runs the same way as the
`(created_at, id) <` comparison below. It only ever reorders rows that share a microsecond,
and it is what makes the cursor exact rather than nearly right."""

LIST_DOCUMENTS_AFTER_SQL: Final[LiteralString] = """
select id, company_id, bid_id, kind, name, storage_path, status, failure_reason,
pages, unread_pages, flagged_chunks, created_at, updated_at
from documents
where company_id = %(company_id)s
  and (created_at, id) < (%(after_created_at)s, %(after_id)s)
order by created_at desc, id desc
limit %(limit)s
"""
"""Every page after the first. Written out in full rather than assembled from the one above,
for the reason the module docstring gives: a `LiteralString` is what keeps a statement from
being built at run time, and an f-string would forfeit it. The row comparison is a single
tuple test, which Postgres answers from the `(company_id, created_at, id)` ordering rather
than by scanning to an offset."""

SCOPED_STATEMENTS: Final[tuple[LiteralString, ...]] = (
    INSERT_DOCUMENT_SQL,
    MARK_PARSED_SQL,
    SET_FLAGGED_CHUNKS_SQL,
    MARK_STATUS_SQL,
    MARK_FAILED_SQL,
    SELECT_DOCUMENT_SQL,
    LIST_DOCUMENTS_SQL,
    LIST_DOCUMENTS_AFTER_SQL,
)
"""Every statement in the module. The test asserts each one binds `company_id`."""

TENANT_PARAMETER: Final = "company_id = %(company_id)s"
"""What the scope looks like in a `where` clause; the insert binds the same parameter as a
value, which is the one place it is the row's own column rather than a filter."""


# ---------------------------------------------------------------------------- writer


class DocumentsReadModel:
    """Writes and reads `documents`, always inside one tenant.

    Every scope argument is keyword-only with no default, so a call that forgets the company
    does not type-check and does not run. Each writer returns the row the database handed
    back, so the caller never has to guess what a transition did.
    """

    def __init__(self, source: ConnectionSource) -> None:
        self._source = source

    async def insert(
        self,
        *,
        company_id: uuid.UUID,
        document_id: uuid.UUID,
        kind: DocumentKind,
        name: str,
        storage_path: str,
    ) -> DocumentRecord:
        """The `uploaded` row, as `returning` handed it back."""
        row = await self._fetch_one(
            INSERT_DOCUMENT_SQL,
            {
                "id": document_id,
                "company_id": company_id,
                "kind": kind.value,
                "name": name,
                "storage_path": storage_path,
            },
        )
        return _record(_require(row, document_id, "inserted"))

    async def mark_parsed(
        self,
        *,
        company_id: uuid.UUID,
        document_id: uuid.UUID,
        pages: int,
        unread_pages: Sequence[int],
    ) -> DocumentRecord:
        """`parsed`, with the page bookkeeping the story shows on the document.

        `unread_pages` is bound as a **list**: psycopg adapts a list to `integer[]` and a
        tuple to a composite record, which the column would reject.
        """
        row = await self._fetch_one(
            MARK_PARSED_SQL,
            {
                "document_id": document_id,
                "company_id": company_id,
                "pages": pages,
                "unread_pages": list(unread_pages),
            },
        )
        return _record(_require(row, document_id, "updated"))

    async def mark_embedded(
        self, *, company_id: uuid.UUID, document_id: uuid.UUID
    ) -> DocumentRecord:
        return await self._advance(company_id, document_id, DocumentStatus.EMBEDDED)

    async def set_flagged_chunks(
        self, *, company_id: uuid.UUID, document_id: uuid.UUID, flagged_chunks: Sequence[int]
    ) -> DocumentRecord:
        """What the injection guard withheld, on the row where the bidder sees it (S2.3.1)."""
        row = await self._fetch_one(
            SET_FLAGGED_CHUNKS_SQL,
            {
                "company_id": company_id,
                "document_id": document_id,
                "flagged_chunks": list(flagged_chunks),
            },
        )
        return _record(_require(row, document_id, "updated"))

    async def mark_ready(
        self, *, company_id: uuid.UUID, document_id: uuid.UUID
    ) -> DocumentRecord:
        return await self._advance(company_id, document_id, DocumentStatus.READY)

    async def mark_failed(
        self, *, company_id: uuid.UUID, document_id: uuid.UUID, reason: str
    ) -> DocumentRecord:
        """Terminal. `reason` is shown to the bidder; the pipeline keeps internals out of it."""
        if not reason.strip():
            raise ReadModelError(
                f"document {document_id} cannot be marked failed without a reason: the "
                "bidder has to be told what to do next"
            )
        row = await self._fetch_one(
            MARK_FAILED_SQL,
            {"document_id": document_id, "company_id": company_id, "reason": reason},
        )
        return _record(_require(row, document_id, "updated"))

    async def get(
        self, *, company_id: uuid.UUID, document_id: uuid.UUID
    ) -> DocumentRecord | None:
        """One document, or `None` — for a missing id and for another company's id alike."""
        row = await self._fetch_one(
            SELECT_DOCUMENT_SQL, {"document_id": document_id, "company_id": company_id}
        )
        return None if row is None else _record(row)

    async def delete(self, *, company_id: uuid.UUID, document_id: uuid.UUID) -> bool:
        """Delete one unattached document. `False` when there was nothing to delete.

        `False` covers three cases the caller has already told apart: an unknown id, another
        company's id, and a document a bid has claimed since the caller looked.
        """
        row = await self._fetch_one(
            DELETE_DOCUMENT_SQL, {"document_id": document_id, "company_id": company_id}
        )
        return row is not None

    async def list(
        self, *, company_id: uuid.UUID, limit: int, after: PageCursor | None = None
    ) -> Page[DocumentRecord]:
        """One page of this company's documents, newest first (M13).

        `limit + 1` rows are asked for and at most `limit` are served: the extra row is how
        `Page.of` learns there is another page without a second `count(*)` over a table an
        upload is writing to.
        """
        statement, params = _page_query(company_id=company_id, limit=limit, after=after)
        async with self._source.connection() as connection:
            cursor = await connection.execute(statement, params)
            rows = await cursor.fetchall()
        return Page.of(
            [_record(row) for row in rows],
            limit=limit,
            key=lambda record: (record.created_at, record.id),
        )

    async def _advance(
        self, company_id: uuid.UUID, document_id: uuid.UUID, status: DocumentStatus
    ) -> DocumentRecord:
        row = await self._fetch_one(
            MARK_STATUS_SQL,
            {"document_id": document_id, "company_id": company_id, "status": status.value},
        )
        return _record(_require(row, document_id, "updated"))

    async def _fetch_one(
        self, sql: LiteralString, params: Mapping[str, Any]
    ) -> Mapping[str, Any] | None:
        async with self._source.connection() as connection:
            cursor = await connection.execute(sql, params)
            return await cursor.fetchone()


INTERRUPTED_REASON: Final = (
    "Processing was interrupted when the server restarted. Please upload the file again."
)
"""What the startup sweep writes to `failure_reason`, and the one reason not written by
`ingestion/pipeline.py`.

It lives here because this module writes it, and `pipeline` imports it into its closed
`FAILURE_REASONS` list -- the other way round would be a cycle, since `pipeline` already
imports `DocumentRecord` from here. Being in that list is what makes the existing test
"a bidder never sees a stack trace, a key or a URL" cover this sentence too.
"""

DEFAULT_STALE_AFTER_SECONDS: Final = 900.0
"""How long a document may sit in a non-terminal status before the sweep calls it lost.

Fifteen minutes: comfortably longer than the slowest real upload measured (the DE pack's
largest file), and short enough that a bidder who restarts the API and reloads is told
something rather than left polling. Only ever compared against `updated_at`, so a row that is
genuinely moving keeps resetting the clock.
"""


async def fail_interrupted_documents(
    db: ConnectionSource,
    *,
    stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
) -> int:
    """Mark every document a restart left mid-pipeline as failed. Returns how many.

    Called once at startup, beside `resume_unfinished_runs`, and the asymmetry with it is the
    point: a bid run *can* be resumed, because its progress is checkpointed. A document's
    progress is not. Nothing re-parses a half-parsed upload, so before this the row sat in
    `uploaded` or `parsed` for ever while `GET /documents/{id}` was polled every two seconds
    for a state that could never arrive.

    Failing it is the honest answer rather than the tidy one: the bytes are in Storage but the
    text is not in the corpus, so the agent cannot use the file and the bidder needs to know
    that rather than to wait. `INTERRUPTED_REASON` tells them what to do about it.
    """
    async with db.connection() as connection:
        cursor = await connection.execute(
            FAIL_INTERRUPTED_DOCUMENTS_SQL,
            {"reason": INTERRUPTED_REASON, "stale_seconds": stale_after_seconds},
        )
        swept = cursor.rowcount
    if swept > 0:
        logger.warning(
            "marked %d document(s) failed: a restart interrupted them mid-pipeline", swept
        )
    return swept


def _page_query(
    *, company_id: uuid.UUID, limit: int, after: PageCursor | None
) -> tuple[LiteralString, dict[str, object]]:
    """The statement and parameters for one page, first or subsequent.

    Two constants rather than one assembled string: see `LIST_DOCUMENTS_AFTER_SQL`. The
    `limit + 1` lives here so both call sites cannot disagree about it.
    """
    if after is None:
        return LIST_DOCUMENTS_SQL, {"company_id": company_id, "limit": limit + 1}
    return LIST_DOCUMENTS_AFTER_SQL, {
        "company_id": company_id,
        "after_created_at": after.created_at,
        "after_id": after.row_id,
        "limit": limit + 1,
    }


def _require(
    row: Mapping[str, Any] | None, document_id: uuid.UUID, verb: str
) -> Mapping[str, Any]:
    """A write that touched no row: the document vanished, or the scope is wrong.

    Both are bugs in the caller (a pipeline only transitions rows it inserted), so this is
    an error and not a `None` — a quiet `None` here would let a poller wait forever.
    """
    if row is None:
        raise ReadModelError(
            f"document {document_id} was not {verb}: no row exists for it in this company"
        )
    return row


def _record(row: Mapping[str, Any]) -> DocumentRecord:
    """One `dict_row` as a `DocumentRecord`, or a loud failure — never a half-filled record."""
    try:
        return DocumentRecord.model_validate(dict(row))
    except ValidationError as err:
        raise ReadModelError(
            f"A documents row has an unexpected shape: {err}. The read model and this query "
            "have drifted apart; re-check migrations 0001_init.sql and "
            "0002_documents_status.sql."
        ) from err
