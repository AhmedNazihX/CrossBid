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
from collections.abc import Awaitable, Callable, Sequence
from typing import Final, Optional

import httpx
from langchain_core.runnables import RunnableConfig

from crossbid.agent.espd_requirements import requirements_from_espd
from crossbid.agent.state import (
    BidState,
    ExtractionProblem,
    ExtractionProblemReason,
    ParseUpdate,
    TenderDocument,
)
from crossbid.ingestion.espd import EspdParseError, parse_espd_request
from crossbid.ingestion.parser import Parser, ParserError
from crossbid.ingestion.pymupdf_parser import PyMuPDFParser
from crossbid.ingestion.storage import (
    CompanyDocumentStore,
    StorageError,
    company_document_store,
)
from crossbid.models.requirement import Requirement
from crossbid.models.tender import DocumentKind
from crossbid.readmodel.bids import BidDocumentRow, ConnectionSource, bid_documents
from crossbid.settings import Settings

logger = logging.getLogger(__name__)

FETCH_TIMEOUT_SECONDS: Final = 60.0
"""Per file. A tender PDF is megabytes, not gigabytes; a minute is generous."""

DocumentLoader = Callable[[str, str], Awaitable[Sequence[BidDocumentRow]]]
"""`(company_id, bid_id) -> the bid's documents`. The read model's `bid_documents`, bound
to a `Database`, is the real one."""

DocumentFetcher = Callable[[str, BidDocumentRow], Awaitable[bytes]]
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
    ) -> None:
        self._load_documents = load_documents
        self._fetch = fetch
        self._parser: Parser = PyMuPDFParser() if parser is None else parser

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
                found, reported = await self._read_espd(company_id, row, bid_id, language)
                requirements.extend(found)
                problems.extend(reported)
                continue
            parsed = await self._parse_one(company_id, row, language)
            if parsed is None:
                reason = ExtractionProblemReason.UNPARSEABLE_DOCUMENT
                problems.append(ExtractionProblem(reason=reason, document_name=row.name))
                continue
            documents.append(parsed)
            if parsed.parsed.unread_pages:
                logger.warning(
                    "Bid %s: %s has %d page(s) with no text layer: %s",
                    bid_id,
                    row.name,
                    len(parsed.parsed.unread_pages),
                    parsed.parsed.unread_pages,
                )
        update: ParseUpdate = {"documents": documents, "extraction_problems": problems}
        if requirements:
            # Only when there are some: the channel appends, and an empty list written here
            # would still be a write, one superstep before extraction adds its own rows.
            update["requirements"] = requirements
        return update

    async def _read_espd(
        self, company_id: str, row: BidDocumentRow, bid_id: str, language: str
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
            request, bid_id=bid_id, document_name=row.name, source_lang=language
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

    return DocumentParser(load_documents=load, fetch=storage_fetcher(bucket))


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
