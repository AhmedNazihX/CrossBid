"""S3.1.1 — the bid's uploaded pack becomes the `TenderDocument`s extraction reads.

The first node of the graph, and a deterministic one: a fixed list of files, one parse
each, no model call. Three decisions are worth stating.

**1. The node reads rows and bytes through seams, never a pool or a bucket.** The plan's
rule is that nodes call `readmodel/` and `ingestion/` rather than running SQL or opening
connections themselves, and the tests' rule is that nothing opens a socket. So the node is a
callable object built from three collaborators — a `load_documents` coroutine (the read
model's `bid_documents`), a `DocumentFetcher` (Storage, via a signed URL), and a `Parser`
(pymupdf by default, Docling later) — and `storage_fetcher` is the one place the real
Storage wiring lives.

**2. A file that cannot be read is reported, not hidden, and does not stop the run.** Two
cases, kept apart because a reviewer does different things about them. A file that opens
but has pages with no text layer arrives whole: `ParsedDocument.unread_pages` lists them,
`sections_of` skips them, and extraction reports a document with none left as
`UNREADABLE_DOCUMENT`. A file that does not open as a PDF at all (`ParserError`) becomes an
`UNPARSEABLE_DOCUMENT` problem and the run goes on with the rest — one bad upload out of 28
must not lose the bid (S3.4.4). A file that Storage will not hand over is different again:
that is infrastructure, not input, so it raises and the runner marks the bid `failed`.

**3. Parsing runs in a worker thread.** pymupdf is synchronous and the DE pack is 191 pages;
holding the event loop for that long would stall every poll of `GET /bids/{id}` from the
browser that is waiting on exactly this run. Files are parsed one after another — the
constraint is the pool of one process, not latency, and 28 files parse in seconds.

**4. A published ESPD request is read here and turned into requirements here (S2.5.1).** The
one document in a pack that is not a PDF, and the only input in the whole system that states
eCertis criterion ids rather than implying them. It never reaches the PDF parser and never
becomes a `TenderDocument` — it has no pages, so there would be nothing for extraction to
section — and instead its criteria come back as `Requirement`s with their
`ecertis_criterion_id` already set, which is what makes `check_reqs` look up national
evidence for them. The mapping is a table in `agent/espd_requirements.py`; no model is asked
anything. A DUME that will not read is reported exactly like a PDF that will not open, and
a criterion the register does not know is reported as `INVALID_CRITERION_ID` rather than
dropped in silence.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime, time
from typing import Final, Optional

import httpx
from langchain_core.runnables import RunnableConfig

from crossbid.agent.espd_requirements import requirements_from_espd
from crossbid.agent.notice_requirements import requirements_from_notice
from crossbid.agent.state import (
    BidState,
    ExtractionProblem,
    ExtractionProblemReason,
    ParseUpdate,
    TenderDocument,
    bidder_language_of,
)
from crossbid.ingestion.chunker import Chunker
from crossbid.ingestion.embeddings import ChunkVectorStore, EmbeddingsClient
from crossbid.ingestion.espd import EspdParseError, parse_espd_request
from crossbid.ingestion.injection_review import (
    ModelInjectionConfirmer,
    confirm_every_finding,
)
from crossbid.ingestion.parser import Parser, ParserError
from crossbid.ingestion.pymupdf_parser import PyMuPDFParser
from crossbid.ingestion.storage import (
    CompanyDocumentStore,
    StorageError,
    company_document_store,
)
from crossbid.ingestion.tender_index import ChunkingTenderIndexer, TenderIndexer
from crossbid.models.requirement import Requirement
from crossbid.models.ted import TedNotice
from crossbid.models.tender import DocumentKind
from crossbid.readmodel.bids import (
    BidDocumentRow,
    ConnectionSource,
    bid_documents,
    set_bid_deadline_if_unset,
)
from crossbid.reference.ted_client import TED_REQUEST_TIMEOUT_S, TedSearchClient
from crossbid.settings import Settings

logger = logging.getLogger(__name__)

FETCH_TIMEOUT_SECONDS: Final = 60.0
"""Per file. A tender PDF is megabytes, not gigabytes; a minute is generous."""

DocumentLoader = Callable[[str, str], Awaitable[Sequence[BidDocumentRow]]]
"""`(company_id, bid_id) -> the bid's documents`. The read model's `bid_documents`, bound
to a `Database`, is the real one."""

DocumentFetcher = Callable[[str, BidDocumentRow], Awaitable[bytes]]

DeadlineRecorder = Callable[[str, str, "TedNotice"], Awaitable[None]]
"""`(company_id, bid_id, notice)` — writes TED's deadline onto the bid (S3.2.2)."""

NoticeFetcher = Callable[[str], Awaitable["TedNotice | None"]]
"""Given a TED publication number, the notice or `None` (S3.2.2).

A seam rather than a direct client call: every unit test in this package runs offline, and
a node that reached the network on construction could not be one of them. The graph passes
the real one; `None` means the graph was built without TED, which is also what an operator
who has switched the search off is asking for."""
"""`(company_id, document) -> the file's bytes`. `storage_fetcher` is the real one."""


class DocumentFetchError(RuntimeError):
    """Storage did not hand over a document. Names the document, never the URL or key."""


class DocumentParser:
    """The `parse_docs` node: `(state, config) -> partial state`.

    A callable object for the same reason `RequirementExtractor` is one: the collaborators
    have to come from somewhere, and the graph calls every node with `(state, config)`.
    Holds no per-run state, so one instance serves every concurrent bid.
    """

    def __init__(
        self,
        *,
        load_documents: DocumentLoader,
        fetch: DocumentFetcher,
        parser: Parser | None = None,
        fetch_notice: NoticeFetcher | None = None,
        record_deadline: DeadlineRecorder | None = None,
        index: TenderIndexer | None = None,
    ) -> None:
        self._load_documents = load_documents
        self._fetch = fetch
        self._parser: Parser = PyMuPDFParser() if parser is None else parser
        self._fetch_notice = fetch_notice
        self._record_deadline = record_deadline
        self._index = index

    @property
    def parser(self) -> Parser:
        return self._parser

    async def __call__(
        self,
        state: BidState,
        # `Optional[...]`, not `RunnableConfig | None`: LangGraph matches this annotation as
        # a *string* under postponed annotations, and the modern spelling is silently never
        # injected (CLAUDE.md). Unused here, but part of the node contract.
        config: Optional[RunnableConfig] = None,  # noqa: UP045
    ) -> ParseUpdate:
        """Every document of the bid, parsed, plus a problem for each that would not open."""
        bid_id, company_id, language = _identity_of(state)
        rows = await self._load_documents(company_id, bid_id)
        if not rows:
            raise ValueError(f"bid {bid_id} has no documents attached: nothing to parse")

        documents: list[TenderDocument] = []
        problems: list[ExtractionProblem] = []
        requirements: list[Requirement] = []
        for row in rows:
            if row.kind is DocumentKind.TENDER_ESPD_REQUEST:
                found, reported = await self._read_espd(
                    company_id, row, bid_id, language, bidder_language_of(state)
                )
                requirements.extend(found)
                problems.extend(reported)
                continue
            parsed = await self._parse_one(company_id, row, language)
            if parsed is None:
                reason = ExtractionProblemReason.UNPARSEABLE_DOCUMENT
                problems.append(ExtractionProblem(reason=reason, document_name=row.name))
                continue
            documents.append(parsed)
            problems.extend(await self._index_one(company_id, bid_id, row, parsed))
            if parsed.parsed.unread_pages:
                logger.warning(
                    "Bid %s: %s has %d page(s) with no text layer: %s",
                    bid_id,
                    row.name,
                    len(parsed.parsed.unread_pages),
                    parsed.parsed.unread_pages,
                )
        requirements.extend(await self._read_notice(state, company_id, bid_id))
        update: ParseUpdate = {"documents": documents, "extraction_problems": problems}
        if requirements:
            # Only when there are some: the channel appends, and an empty list written here
            # would still be a write, one superstep before extraction adds its own rows.
            update["requirements"] = requirements
        return update

    async def _index_one(
        self,
        company_id: str,
        bid_id: str,
        row: BidDocumentRow,
        parsed: TenderDocument,
    ) -> tuple[ExtractionProblem, ...]:
        """Write the document's passages into `tender_chunks`, under this bid.

        Without this the bid has no tender corpus at all and `tender_rag_search` answers
        "nothing found" to every question — inside `check_reqs`, and inside the chat where
        the tender half of "ask the tender" rests on it entirely. That was the state of the
        system until this method existed; see `ingestion/tender_index.py`.

        A failure is reported and the run continues. Indexing spends money on embeddings and
        touches the network, so it is the kind of step that fails for reasons the bidder did
        not cause, and losing a paid run to one of them would be the wrong trade — S3.1.1
        already made that call for a file that will not open. What a reviewer must not get
        is silence: `INDEXING_FAILED` names the document whose passages are missing, so a
        thin answer about *that* document has a visible cause.
        """
        if self._index is None:
            return ()
        try:
            await self._index(
                company_id=uuid.UUID(company_id),
                bid_id=uuid.UUID(bid_id),
                parsed=parsed.parsed,
            )
        except Exception:
            logger.exception(
                "Bid %s: %s could not be indexed; it will not be retrievable", bid_id, row.name
            )
            return (
                ExtractionProblem(
                    reason=ExtractionProblemReason.INDEXING_FAILED,
                    document_name=row.name,
                ),
            )
        return ()

    async def _read_notice(
        self, state: BidState, company_id: str, bid_id: str
    ) -> tuple[Requirement, ...]:
        """The buyer's structured notice fields as requirements (S3.2.2), or nothing.

        **Nothing is the common answer and never an error.** Most notices state no selection
        criteria — 14-17 % of CPV-72 ones do — and TED may be unreachable, and a bid whose
        pack has already been uploaded must not fail because a public search API is slow.
        The pack is the source of record; this is the buyer's own words where they exist, in
        addition to it.

        No fetcher configured means the graph was built without one, which is the case in
        every offline test and in a deployment that has switched TED off.
        """
        if self._fetch_notice is None:
            return ()
        notice_number = state.get("notice_number", "")
        if not notice_number:
            return ()
        try:
            notice = await self._fetch_notice(notice_number)
        # Deliberately broad: a public search API is not allowed to end a run whose pack
        # has already been uploaded and whose extraction is about to be paid for.
        except Exception:
            logger.warning(
                "Bid %s: the TED notice %s could not be read; continuing on the pack alone",
                bid_id,
                notice_number,
                exc_info=True,
            )
            return ()
        if notice is None:
            logger.info("Bid %s: TED has no notice %s", bid_id, notice_number)
            return ()
        await self._store_deadline(company_id, bid_id, notice)
        return requirements_from_notice(notice, bid_id=bid_id)

    async def _store_deadline(self, company_id: str, bid_id: str, notice: TedNotice) -> None:
        """The deadline on the bid, for the dashboard's countdown (S3.2.2).

        Guarded the same way the fetch is: the read-model write is not allowed to end a run
        either. The write itself refuses to overwrite a deadline the bidder already gave,
        because theirs carries an hour and TED's never does (`set_bid_deadline_if_unset`).
        """
        if self._record_deadline is None or notice.deadline is None:
            return
        try:
            await self._record_deadline(company_id, bid_id, notice)
        except Exception:
            logger.warning(
                "Bid %s: TED's deadline could not be written to the bid", bid_id, exc_info=True
            )

    async def _read_espd(
        self,
        company_id: str,
        row: BidDocumentRow,
        bid_id: str,
        language: str,
        bidder_language: str,
    ) -> tuple[tuple[Requirement, ...], tuple[ExtractionProblem, ...]]:
        """A published DUME as requirements, plus what it could not contribute.

        The parse is CPU work on a file a bidder uploaded, and it is bounded by
        `safe_xml`'s size cap rather than by the document's ambitions; a 145 KB form takes
        milliseconds, so it runs inline rather than in a thread the way pymupdf does.
        """
        content = await self._fetch(company_id, row)
        try:
            request = parse_espd_request(content)
        except EspdParseError as exc:
            # The message names the refusal, never the file's content (ADR-0008).
            logger.warning("Bid document %s (%s) is not readable: %s", row.id, row.name, exc)
            reason = ExtractionProblemReason.UNPARSEABLE_DOCUMENT
            return (), (ExtractionProblem(reason=reason, document_name=row.name),)

        found = requirements_from_espd(
            request,
            bid_id=bid_id,
            document_name=row.name,
            source_lang=language,
            bidder_language=bidder_language,
        )
        logger.info(
            "Bid %s: %s declares %d ESPD criterion/criteria the register knows",
            bid_id,
            row.name,
            len(found),
        )
        # One problem per criterion that could not be mapped — the ids themselves stay in
        # the log, because a problem carries no document-derived text (ADR-0008).
        missing = request.dropped_criterion_count + len(request.criteria) - len(found)
        reason = ExtractionProblemReason.INVALID_CRITERION_ID
        return found, tuple(
            ExtractionProblem(reason=reason, document_name=row.name) for _ in range(missing)
        )

    async def _parse_one(
        self, company_id: str, row: BidDocumentRow, language: str
    ) -> TenderDocument | None:
        """One file as a `TenderDocument`, or `None` when it would not open as a PDF.

        A fetch failure is *not* caught: Storage refusing a file is an outage, and a run
        that quietly went on without half its pack would park at `awaiting_review` looking
        complete.
        """
        content = await self._fetch(company_id, row)
        try:
            parsed = await asyncio.to_thread(self._parser.parse, content, document_id=row.id)
        except ParserError:
            logger.exception("Bid document %s (%s) could not be parsed", row.id, row.name)
            return None
        return TenderDocument(parsed=parsed, name=row.name, language=language)


async def fetch_notice(notice_number: str) -> TedNotice | None:
    """The bid's own notice, by publication number. Exactly one match or none.

    **Module level, not a closure inside `build_parse_docs`.** It captures nothing from the
    builder, and as a closure the one thing worth asserting about it — that the HTTP client
    it opens is closed again (M22) — could not be reached from a test without standing up
    Storage, a database and a pack.

    The client is closed on the way out; each one holds a connection pool and a TLS context
    until the garbage collector runs. `to_thread` because the client is synchronous and this
    is an async node, which is the reason `routers/tenders.py` gives for the same call.
    """
    with httpx.Client(timeout=TED_REQUEST_TIMEOUT_S) as http:
        return await asyncio.to_thread(
            TedSearchClient(http).search_by_publication_number,
            notice_number,
            language=None,
        )


def build_parse_docs(
    settings: Settings, db: ConnectionSource, *, store: CompanyDocumentStore | None = None
) -> DocumentParser:
    """The node as the graph wires it (S3.1.1): the read model's rows, Storage's bytes.

    `company_document_store` refuses to build when Storage is not configured
    (`StorageError` naming the variables), so this raises rather than returning a node that
    would fail its first run; the caller decides whether that stops startup or answers 503.
    `store` is the seam for a caller that already holds one, and for tests.
    """
    bucket = company_document_store(settings) if store is None else store

    async def load(company_id: str, bid_id: str) -> Sequence[BidDocumentRow]:
        return await bid_documents(db, company_id=company_id, bid_id=bid_id)

    async def record_deadline(company_id: str, bid_id: str, notice: TedNotice) -> None:
        if notice.deadline is None:  # pragma: no cover - the caller checks first
            return
        written = await set_bid_deadline_if_unset(
            db,
            company_id=company_id,
            bid_id=bid_id,
            deadline=datetime.combine(notice.deadline, time.min, tzinfo=UTC),
            deadline_utc_offset_minutes=notice.deadline_utc_offset_minutes,
        )
        logger.info(
            "Bid %s: TED's deadline %s",
            bid_id,
            "written to the bid" if written else "not used; the bidder had given one",
        )

    ingestion = settings.runtime.ingestion
    return DocumentParser(
        load_documents=load,
        fetch=storage_fetcher(bucket),
        fetch_notice=fetch_notice,
        record_deadline=record_deadline,
        # The same chunk sizes the upload pipeline uses, from the same settings block: a
        # tender corpus chunked by different numbers from the company corpus would make two
        # retrievals over one bid incomparable, which is the reason `build_pipeline` reads
        # them from here too.
        index=ChunkingTenderIndexer(
            chunker=Chunker(
                chunk_tokens=ingestion.chunk_tokens, overlap_tokens=ingestion.chunk_overlap
            ),
            embedder=EmbeddingsClient(settings),
            writer=ChunkVectorStore(db),
            confirm=(
                ModelInjectionConfirmer(settings)
                if settings.runtime.confirm_flagged_chunks
                else confirm_every_finding
            ),
        ),
    )


def storage_fetcher(
    store: CompanyDocumentStore, *, client: httpx.AsyncClient | None = None
) -> DocumentFetcher:
    """The real `DocumentFetcher`: sign the document's key for its company, then GET it.

    `CompanyDocumentStore.signed_url` is the tenancy check — it refuses any key it could not
    have built for `company_id` (S2.2.2) — so a document row that somehow named another
    company's object is refused here, before a byte moves. The signed URL is a bearer
    credential for the file and appears in no message.
    """
    http = client if client is not None else httpx.AsyncClient(timeout=FETCH_TIMEOUT_SECONDS)

    async def fetch(company_id: str, document: BidDocumentRow) -> bytes:
        try:
            signed = store.signed_url(company_id=company_id, key=document.storage_path)
            response = await http.get(signed.url)
            response.raise_for_status()
        except (StorageError, httpx.HTTPError) as exc:
            raise DocumentFetchError(
                f"document {document.id} ({document.name}) could not be fetched from "
                f"storage: {type(exc).__name__}"
            ) from exc
        if not response.content:
            raise DocumentFetchError(
                f"document {document.id} ({document.name}) came back empty from storage"
            )
        return response.content

    return fetch


def _identity_of(state: BidState) -> tuple[str, str, str]:
    """`bid_id`, `company_id` and `source_language`, or a `ValueError` naming the gap.

    All three are set by the router before the run starts; a state without one is a defect
    in the caller, and a document parsed under no tenant or no language would either be
    unscopable or fail one requirement at a time in extraction.
    """
    bid_id = state.get("bid_id", "").strip()
    company_id = state.get("company_id", "").strip()
    language = state.get("source_language", "").strip()
    missing = [
        name
        for name, value in (
            ("bid_id", bid_id),
            ("company_id", company_id),
            ("source_language", language),
        )
        if not value
    ]
    if missing:
        raise ValueError(f"parse_docs needs {', '.join(missing)} in the state")
    return bid_id, company_id, language
