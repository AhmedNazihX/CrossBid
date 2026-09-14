"""S2.2.3 — an upload becomes `uploaded → parsed → embedded → ready`, or `failed` with a reason.

The pipeline is a deterministic state machine, not an agent: there is no decision about what
to do next, only a fixed run of steps with a status written after each one. That is what lets
the browser poll `GET /documents/{id}` and show progress rather than a spinner — every
transition is committed as it happens (`autocommit=True` on the pool), so a poller sees
`parsed` while the embeddings request is still in flight.

Two calls, because the HTTP layer needs them at different moments:

* **`accept`** runs inside the request. It mints the id, records the `uploaded` row and
  returns it, which is what the 202 answer carries. Nothing here touches the network: the
  row's `storage_path` is computed with `ingestion.storage.object_key`, the same function the
  store will use, so the key is known before a byte is stored and the two cannot disagree.
* **`process`** runs as a background task. Storage, parse, chunk, embed, write, and the
  status writes in between. Anything that raises is caught once, logged in full on the
  server, and written to the row as one of the `*_REASON` sentences — never the exception's
  own text. A pymupdf message quotes the input, a Storage message could quote a key, an httpx
  message quotes a URL; the bidder gets a sentence they can act on and nothing else.

Every collaborator is a constructor argument typed as a `Protocol`, so the unit suite runs
the real state machine over fakes and never opens a socket or a database. `build_pipeline` at
the bottom of this module is the concrete wiring — `PyMuPDFParser`, `Chunker`,
`EmbeddingsClient`, `ChunkVectorStore` — and it lives here rather than in
`routers/documents.py` because the HTTP route is no longer its only caller: S2.4.3's demo seed
drives a pipeline from a script and must drive the *same* one, or a seeded document would be
chunked by different numbers from an uploaded one. `CompanyDocumentStore` and
`DocumentsReadModel` stay arguments: the first needs Supabase credentials this module has no
business reading, and the second is what the caller already holds.

**Only company evidence is embedded at upload.** A company's evidence pack outlives any bid
and is what `company_rag_search` reads, so its vectors go into `company_chunks` here. A
tender document is uploaded *before* its bid exists — S4.3.1's flow uploads the pack and then
presses Start, and S3.1.1's `POST /bids` attaches the documents — and `tender_chunks.bid_id`
is `NOT NULL`, so there is nowhere to put its vectors yet. It is stored, parsed (the page
counts and the scanned-PDF refusal below apply to every kind) and goes `parsed → ready`; the
graph reads the file back from Storage and owns its vectors under the bid. `EMBEDDED_KINDS`
is the one place that rule is written.

**A published ESPD request takes the short path (S2.5.1).** `TENDER_ESPD_REQUEST` is the one
kind that is not a PDF: it is stored, read by `ingestion/espd.py` — hardened XML, see
`safe_xml` — and goes `parsed` (zero pages, nothing unread) straight to `ready`. It is never
handed to the PDF parser, never chunked and never embedded. It **fails** when it is not a
readable ESPD request, or when it names no criterion the eCertis register knows: both mean
the file can contribute nothing to a bid, and a `ready` row would let Start be pressed on
it. The upload route refuses the same two things earlier where it can (`routers/documents.py`
sniffs the root element), but a seed, a script or a retry reaches `process` directly, so the
check lives here as well as there.

**A document with no readable page fails, deliberately.** The parser lists an image-only page
instead of dropping it (S2.1.1), so a scanned PDF parses cleanly to N unread pages and zero
chunks. Marking that `ready` would be a lie the agent later pays for — and for a tender
document it would let Start be pressed on nothing — so the row keeps its page counts from
`parsed` and fails with a reason that says what to do.

**The synchronous steps run in a worker thread.** pymupdf and the Storage client block, and
the DE pack is 191 pages; holding the event loop for that long would stall every poll of
`GET /documents/{id}` from the browser that is waiting on exactly this run.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Protocol

from crossbid.guards.injection import InjectionFinding, scan
from crossbid.ingestion.chunker import Chunk, Chunker
from crossbid.ingestion.embeddings import (
    ChunkStoreError,
    ChunkVectorStore,
    ConnectionSource,
    EmbeddedChunk,
    EmbeddingsClient,
    EmbeddingsError,
)
from crossbid.ingestion.espd import EspdParseError, parse_espd_request
from crossbid.ingestion.parser import ParsedDocument, Parser, ParserError
from crossbid.ingestion.pymupdf_parser import PyMuPDFParser
from crossbid.ingestion.storage import DEFAULT_CONTENT_TYPE, StorageError, object_key
from crossbid.models import DocumentKind
from crossbid.readmodel.documents import DocumentRecord
from crossbid.settings import Settings

logger = logging.getLogger(__name__)

EMBEDDED_KINDS: Final = frozenset({DocumentKind.COMPANY_EVIDENCE})
"""The kinds whose vectors are written at upload; see the module docstring for the rest."""

STORE_FAILED_REASON: Final = "The file could not be stored. Please upload it again."
UNREADABLE_REASON: Final = (
    "The file could not be read as a PDF. Re-export it as a PDF and upload it again."
)
NO_READABLE_TEXT_REASON: Final = (
    "No page of this PDF has readable text, so it looks scanned. Text recognition is not "
    "supported; re-export the document with a text layer and upload it again."
)
EMBED_FAILED_REASON: Final = (
    "The document text could not be indexed because the embeddings service did not answer. "
    "Try again later."
)
NOT_AN_ESPD_REQUEST_REASON: Final = (
    "This file could not be read as an ESPD request (DUME). Upload the buyer's own ESPD "
    "request XML, or upload the document as a tender document instead."
)
NO_ESPD_CRITERIA_REASON: Final = (
    "This ESPD request names no criterion from the EU register, so nothing in it can be "
    "checked. Upload the ESPD request the buyer published for this tender."
)
SAVE_FAILED_REASON: Final = "The document text could not be saved. Try again later."
UNEXPECTED_FAILURE_REASON: Final = "Processing failed unexpectedly. Try again later."

FAILURE_REASONS: Final[tuple[str, ...]] = (
    STORE_FAILED_REASON,
    UNREADABLE_REASON,
    NO_READABLE_TEXT_REASON,
    NOT_AN_ESPD_REQUEST_REASON,
    NO_ESPD_CRITERIA_REASON,
    EMBED_FAILED_REASON,
    SAVE_FAILED_REASON,
    UNEXPECTED_FAILURE_REASON,
)
"""Every sentence `process` can write to `failure_reason`. Closed on purpose: a test asserts
the row never carries anything outside this list, which is how "no stack trace, no key, no
URL" is proven rather than hoped."""


class NoReadableTextError(RuntimeError):
    """Every page parsed as unread, so there is nothing to chunk or embed."""


class NoEspdCriteriaError(RuntimeError):
    """The file is an ESPD request, but names no criterion the eCertis register knows."""


# --------------------------------------------------------------------------- collaborators


class DocumentStore(Protocol):
    """The one call the pipeline makes on `ingestion.storage.CompanyDocumentStore`."""

    def upload(
        self,
        *,
        company_id: str,
        document_id: str,
        filename: str,
        content: bytes,
        content_type: str = DEFAULT_CONTENT_TYPE,
    ) -> str: ...


class Chunking(Protocol):
    """`ingestion.chunker.Chunker`, by shape."""

    def chunk(self, document: ParsedDocument) -> tuple[Chunk, ...]: ...


class Embedder(Protocol):
    """`ingestion.embeddings.EmbeddingsClient`, by shape. `aclose` because the client owns an
    HTTP connection pool and the pipeline is the last to use it in a background task."""

    async def embed_texts(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]: ...

    async def aclose(self) -> None: ...


class ChunkWriter(Protocol):
    """`ingestion.embeddings.ChunkVectorStore`, the one insert the pipeline needs."""

    async def insert_company_chunks(
        self, *, company_id: uuid.UUID, document_id: uuid.UUID, chunks: Sequence[EmbeddedChunk]
    ) -> int: ...


class DocumentRecords(Protocol):
    """`readmodel.documents.DocumentsReadModel`, the writers only."""

    async def insert(
        self,
        *,
        company_id: uuid.UUID,
        document_id: uuid.UUID,
        kind: DocumentKind,
        name: str,
        storage_path: str,
    ) -> DocumentRecord: ...

    async def mark_parsed(
        self,
        *,
        company_id: uuid.UUID,
        document_id: uuid.UUID,
        pages: int,
        unread_pages: Sequence[int],
    ) -> DocumentRecord: ...

    async def mark_embedded(
        self, *, company_id: uuid.UUID, document_id: uuid.UUID
    ) -> DocumentRecord: ...

    async def set_flagged_chunks(
        self, *, company_id: uuid.UUID, document_id: uuid.UUID, flagged_chunks: Sequence[int]
    ) -> DocumentRecord: ...

    async def mark_ready(
        self, *, company_id: uuid.UUID, document_id: uuid.UUID
    ) -> DocumentRecord: ...

    async def mark_failed(
        self, *, company_id: uuid.UUID, document_id: uuid.UUID, reason: str
    ) -> DocumentRecord: ...


@dataclass(frozen=True, slots=True)
class Upload:
    """What the multipart part carried, already validated by the router."""

    filename: str
    content_type: str
    content: bytes


# -------------------------------------------------------------------------------- pipeline


def _partition_by_guard(
    chunks: Sequence[Chunk],
) -> tuple[list[Chunk], list[tuple[int, InjectionFinding]]]:
    """The chunks that may be stored, and the numbered ones the guard refused.

    Numbered by position in the document's own chunk sequence, one-based, because that is
    what `documents.flagged_chunks` means and what a reviewer counts when they go looking.
    """
    kept: list[Chunk] = []
    flagged: list[tuple[int, InjectionFinding]] = []
    for number, chunk in enumerate(chunks, start=1):
        finding = scan(chunk.text)
        if finding is None:
            kept.append(chunk)
        else:
            flagged.append((number, finding))
    return kept, flagged


class DocumentPipeline:
    """Runs one upload through the state machine. Holds no per-document state."""

    def __init__(
        self,
        *,
        store: DocumentStore,
        parser: Parser,
        chunker: Chunking,
        embedder: Embedder,
        chunk_writer: ChunkWriter,
        records: DocumentRecords,
    ) -> None:
        self._store = store
        self._parser = parser
        self._chunker = chunker
        self._embedder = embedder
        self._chunk_writer = chunk_writer
        self._records = records

    async def accept(
        self,
        *,
        company_id: uuid.UUID,
        kind: DocumentKind,
        upload: Upload,
        document_id: uuid.UUID | None = None,
    ) -> DocumentRecord:
        """Record the `uploaded` row and return it. No network; safe inside the request.

        The id is minted here unless the caller brings one. An upload has no id before this
        call, so `routers/documents.py` never passes one; the S2.4.3 demo seed does, because
        a `uuid5` of the filename is what lets a second run recognise the document it already
        seeded — before a byte is stored and before an embedding is paid for.
        """
        document_id = uuid.uuid4() if document_id is None else document_id
        # The key the store will write to, computed before anything is stored, so the row
        # and the object agree from the first status on. The original filename goes into
        # `name`; the key's filename is sanitised and may not resemble it (S2.2.2).
        key = object_key(
            company_id=str(company_id), document_id=str(document_id), filename=upload.filename
        )
        return await self._records.insert(
            company_id=company_id,
            document_id=document_id,
            kind=kind,
            name=upload.filename,
            storage_path=key,
        )

    async def process(self, record: DocumentRecord, upload: Upload) -> DocumentRecord:
        """Everything after the 202: store, parse, embed, and the status writes between.

        Returns the final row (`ready` or `failed`). The exception behind a failure is logged
        with its traceback here and nowhere else; the row gets a `*_REASON` sentence. Only
        the `failed` write itself may raise out of here, and then it should: a database that
        cannot record the failure is not something to hide from the task's log.
        """
        try:
            return await self._run(record, upload)
        except Exception as exc:
            reason = _reason_for(exc)
            logger.exception(
                "document %s failed (%s): %s", record.id, type(exc).__name__, reason
            )
            return await self._records.mark_failed(
                company_id=record.company_id, document_id=record.id, reason=reason
            )

    async def aclose(self) -> None:
        """Release the embedder's connection pool. Called once, after `process`."""
        await self._embedder.aclose()

    async def _run(self, record: DocumentRecord, upload: Upload) -> DocumentRecord:
        await asyncio.to_thread(
            self._store.upload,
            company_id=str(record.company_id),
            document_id=str(record.id),
            filename=upload.filename,
            content=upload.content,
            content_type=upload.content_type,
        )
        if record.kind is DocumentKind.TENDER_ESPD_REQUEST:
            return await self._accept_espd(record, upload)
        parsed = await asyncio.to_thread(
            self._parser.parse, upload.content, document_id=str(record.id)
        )
        record = await self._records.mark_parsed(
            company_id=record.company_id,
            document_id=record.id,
            pages=parsed.page_count,
            unread_pages=parsed.unread_pages,
        )
        # After `parsed`, so the row says how many pages were looked at before it failed.
        if not parsed.readable_pages:
            raise NoReadableTextError(f"document {record.id}: no page has a text layer")
        record = await self._scan_and_embed(record, parsed)
        return await self._records.mark_ready(
            company_id=record.company_id, document_id=record.id
        )

    async def _accept_espd(self, record: DocumentRecord, upload: Upload) -> DocumentRecord:
        """Validate a stored DUME and take it to `ready`. No pages, no chunks, no vectors.

        Parsing runs in a worker thread for the same reason pymupdf does: it is synchronous
        work on a file a bidder chose the size of, and the poller waiting on this row is on
        the event loop. `parse_espd_request` raises `EspdParseError` for anything that is
        not one, and `_reason_for` turns both refusals into a sentence the bidder can act on.
        """
        request = await asyncio.to_thread(parse_espd_request, upload.content)
        if not request.criteria:
            raise NoEspdCriteriaError(
                f"document {record.id}: no criterion of this ESPD request is in the register"
            )
        logger.info(
            "document %s is an ESPD request declaring %d known criterion/criteria",
            record.id,
            len(request.criteria),
        )
        # `parsed` with zero pages is the honest count for an XML form, and it keeps the
        # status sequence a poller sees the same for every kind.
        record = await self._records.mark_parsed(
            company_id=record.company_id, document_id=record.id, pages=0, unread_pages=()
        )
        return await self._records.mark_ready(
            company_id=record.company_id, document_id=record.id
        )

    async def _scan_and_embed(
        self, record: DocumentRecord, parsed: ParsedDocument
    ) -> DocumentRecord:
        """Scan every document for planted instructions; embed the ones that get embedded.

        **The scan runs for every kind, and that is the point.** Only company evidence is
        embedded at upload (`EMBEDDED_KINDS`) — a tender document's text reaches a model
        through `extract_reqs`' page sections instead, which is precisely where the
        adversarial fixtures aim. Scanning only the embedded kinds would have put the guard
        everywhere except the path the attack uses. The flagged chunk numbers are written to
        the row whatever the kind, so `documents.flagged_chunks` means the same thing for a
        tender pack as for a certificate.

        **For an embedded kind, the flagged chunk is withheld before the embedder.** The
        story asks that a flagged chunk never enter a prompt; filtering at retrieval time
        would make that a property of every caller of every RAG tool, and one forgetful
        caller would undo it. Held back before `insert_company_chunks` the text is not in
        the corpus at all — nothing for a query to find, no embedding paid for, and the
        guarantee holds for tools not yet written.

        The chunk is withheld, not the document. A 200-page pack with one planted paragraph
        is still worth reading; refusing the whole upload would hand an attacker a way to
        make a tender unanalysable by hiding four lines in it.
        """
        chunks = await asyncio.to_thread(self._chunker.chunk, parsed)
        kept, flagged = _partition_by_guard(chunks)
        for number, finding in flagged:
            logger.warning(
                "document %s chunk %d withheld: %s — %r",
                record.id,
                number,
                ", ".join(signal.value for signal in finding.signals),
                finding.excerpt,
            )
        record = await self._records.set_flagged_chunks(
            company_id=record.company_id,
            document_id=record.id,
            flagged_chunks=[number for number, _ in flagged],
        )
        if record.kind not in EMBEDDED_KINDS:
            return record
        await self._chunk_writer.insert_company_chunks(
            company_id=record.company_id,
            document_id=record.id,
            chunks=await self._embed(kept),
        )
        return await self._records.mark_embedded(
            company_id=record.company_id, document_id=record.id
        )

    async def _embed(self, chunks: Sequence[Chunk]) -> tuple[EmbeddedChunk, ...]:
        """`strict=True` is the assertion: a vector count that differs from the chunk count
        must fail here, not pair the shorter of the two (see `embeddings.embed_chunks`)."""
        vectors = await self._embedder.embed_texts([chunk.text for chunk in chunks])
        return tuple(
            EmbeddedChunk(chunk=chunk, embedding=vector)
            for chunk, vector in zip(chunks, vectors, strict=True)
        )


def _reason_for(exc: Exception) -> str:
    """The sentence the bidder sees. Chosen by exception type, never built from its text."""
    if isinstance(exc, StorageError):
        return STORE_FAILED_REASON
    if isinstance(exc, ParserError):
        return UNREADABLE_REASON
    if isinstance(exc, NoReadableTextError):
        return NO_READABLE_TEXT_REASON
    if isinstance(exc, EspdParseError):
        return NOT_AN_ESPD_REQUEST_REASON
    if isinstance(exc, NoEspdCriteriaError):
        return NO_ESPD_CRITERIA_REASON
    if isinstance(exc, EmbeddingsError):
        return EMBED_FAILED_REASON
    if isinstance(exc, ChunkStoreError):
        return SAVE_FAILED_REASON
    return UNEXPECTED_FAILURE_REASON


# --------------------------------------------------------------------------------- wiring


def build_pipeline(
    settings: Settings,
    *,
    source: ConnectionSource,
    store: DocumentStore,
    records: DocumentRecords,
) -> DocumentPipeline:
    """The production pipeline: real parser, chunker, embeddings client and vector store.

    Build one per batch of uploads and `aclose` it when the batch is done — the embeddings
    client owns an HTTP connection pool and this function does not own its lifetime. The
    chunker's encoder is left to its lazy default, so tiktoken's BPE table is fetched in
    whatever background task or script is doing the work and never inside a request.

    The chunk sizes come from `settings.runtime.ingestion` and from nowhere else, which is
    the point of the function: an upload and a seed that chunked by different numbers would
    put two incompatible corpora in one `company_chunks` table.
    """
    ingestion = settings.runtime.ingestion
    return DocumentPipeline(
        store=store,
        parser=PyMuPDFParser(),
        chunker=Chunker(
            chunk_tokens=ingestion.chunk_tokens, overlap_tokens=ingestion.chunk_overlap
        ),
        embedder=EmbeddingsClient(settings),
        chunk_writer=ChunkVectorStore(source),
        records=records,
    )
