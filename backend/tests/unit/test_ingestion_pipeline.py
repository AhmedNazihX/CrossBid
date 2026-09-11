"""S2.2.3 — the upload state machine: `uploaded → parsed → embedded → ready`, or `failed`.

Offline. The real `DocumentPipeline` and the real `Chunker` (over a character encoder, so no
BPE table is fetched) run over fakes for Storage, the parser, the embeddings client, the chunk
writer and the `documents` read model. The read-model fake keeps every transition in the
order it was written, which is what the story is about: a poller must see `parsed` while the
embeddings request is still in flight, not a single jump to `ready` at the end.

The failure tests are adversarial on purpose. Each fake exception message carries a URL, a
key-shaped string and a traceback marker; the assertion is that none of it reaches the row.
`FAILURE_REASONS` is the closed list of sentences the pipeline may write, and every failed
row is checked against it.

`InMemoryRecords` and the other fakes are imported by `test_documents_router.py`, which runs
the same pipeline behind the HTTP layer; they live here because this is the module that
defines what they stand in for.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from crossbid.ingestion.chunker import Chunker
from crossbid.ingestion.embeddings import ChunkStoreError, EmbeddedChunk, EmbeddingsError
from crossbid.ingestion.parser import DocumentSource, ParsedDocument, ParsedPage, ParserError
from crossbid.ingestion.pipeline import (
    EMBED_FAILED_REASON,
    EMBEDDED_KINDS,
    FAILURE_REASONS,
    NO_READABLE_TEXT_REASON,
    SAVE_FAILED_REASON,
    STORE_FAILED_REASON,
    UNEXPECTED_FAILURE_REASON,
    UNREADABLE_REASON,
    DocumentPipeline,
    Upload,
)
from crossbid.ingestion.storage import DEFAULT_CONTENT_TYPE, StorageError, object_key
from crossbid.models import DocumentKind
from crossbid.readmodel.documents import DocumentRecord, DocumentStatus, ReadModelError

COMPANY_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
OTHER_COMPANY_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
FIXED_START = datetime(2026, 9, 11, 9, 0, tzinfo=UTC)
DIMENSIONS = 4
CHUNK_TOKENS = 64
OVERLAP_TOKENS = 8

PDF_BYTES = b"%PDF-1.7\n%fake body for the parser fake\n"
ORIGINAL_FILENAME = "Nachweis ISO 27001 (2026) Ümlaut.pdf"
"""Spaces, brackets and an umlaut: the key must not resemble it, the row must equal it."""

LEAKY_MESSAGE = (
    "Traceback (most recent call last): https://abcdefghijklmnopqrst.supabase.co/storage/v1 "
    "Authorization: Bearer sk-or-v1-LEAKED-OPENROUTER-KEY"
)
"""Everything a failure reason must never carry: a traceback marker, a URL and a key."""
LEAK_MARKERS = ("Traceback", "https://", "sk-or-", "Bearer")


# ---------------------------------------------------------------------------- fakes


class CharacterEncoder:
    """One token per character, so the real `Chunker` runs without tiktoken's download."""

    def encode(self, text: str) -> list[int]:
        return [ord(character) for character in text]

    def decode(self, tokens: Sequence[int]) -> str:
        return "".join(chr(token) for token in tokens)


class FakeStore:
    """`CompanyDocumentStore.upload` by shape: records the call, builds the real key."""

    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.uploads: list[dict[str, Any]] = []
        self.threads: list[threading.Thread] = []

    def upload(
        self,
        *,
        company_id: str,
        document_id: str,
        filename: str,
        content: bytes,
        content_type: str = DEFAULT_CONTENT_TYPE,
    ) -> str:
        self.threads.append(threading.current_thread())
        if self.error is not None:
            raise self.error
        key = object_key(company_id=company_id, document_id=document_id, filename=filename)
        self.uploads.append(
            {
                "company_id": company_id,
                "document_id": document_id,
                "filename": filename,
                "content": content,
                "content_type": content_type,
                "key": key,
            }
        )
        return key


class FakeParser:
    """A `Parser` that answers with configured page texts, or raises."""

    name = "fake"

    def __init__(self, pages: Sequence[str], *, error: Exception | None = None) -> None:
        self.pages = tuple(pages)
        self.error = error
        self.sources: list[DocumentSource] = []
        self.threads: list[threading.Thread] = []

    def parse(self, source: DocumentSource, *, document_id: str) -> ParsedDocument:
        self.threads.append(threading.current_thread())
        self.sources.append(source)
        if self.error is not None:
            raise self.error
        return ParsedDocument(
            document_id=document_id,
            parser_name=self.name,
            pages=tuple(
                ParsedPage(page_number=number, text=text)
                for number, text in enumerate(self.pages, start=1)
            ),
        )


class FakeEmbedder:
    """`EmbeddingsClient` by shape. `observe` runs at call time, to catch the row mid-flight."""

    def __init__(
        self,
        *,
        error: Exception | None = None,
        extra_vectors: int = 0,
        observe: Callable[[], object] | None = None,
    ) -> None:
        self.error = error
        self.extra_vectors = extra_vectors
        self.observe = observe
        self.calls: list[list[str]] = []
        self.observed: list[object] = []
        self.closed = 0

    async def embed_texts(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        self.calls.append(list(texts))
        if self.observe is not None:
            self.observed.append(self.observe())
        if self.error is not None:
            raise self.error
        count = len(texts) + self.extra_vectors
        return tuple((float(index),) * DIMENSIONS for index in range(count))

    async def aclose(self) -> None:
        self.closed += 1


class FakeChunkWriter:
    """`ChunkVectorStore.insert_company_chunks` by shape."""

    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.inserts: list[dict[str, Any]] = []

    async def insert_company_chunks(
        self, *, company_id: uuid.UUID, document_id: uuid.UUID, chunks: Sequence[EmbeddedChunk]
    ) -> int:
        if self.error is not None:
            raise self.error
        self.inserts.append(
            {"company_id": company_id, "document_id": document_id, "chunks": tuple(chunks)}
        )
        return len(chunks)


@dataclass
class InMemoryRecords:
    """The `documents` read model over a dict, remembering every transition in order.

    Scoped like the real one: a transition on a row that is not this company's raises
    `ReadModelError`, and `get` for another company's id is `None`. Timestamps advance one
    second per write so `updated_at` is checkable without a real clock.
    """

    rows: dict[uuid.UUID, DocumentRecord] = field(default_factory=dict)
    history: list[DocumentRecord] = field(default_factory=list)
    """Every row exactly as written, in order. `rows` keeps only the latest per id."""
    fail_on: frozenset[str] = frozenset()
    writes: int = 0

    def _now(self) -> datetime:
        self.writes += 1
        return FIXED_START + timedelta(seconds=self.writes)

    def _write(self, record: DocumentRecord) -> DocumentRecord:
        self.rows[record.id] = record
        self.history.append(record)
        return record

    def _own(
        self, method: str, company_id: uuid.UUID, document_id: uuid.UUID
    ) -> DocumentRecord:
        if method in self.fail_on:
            raise ReadModelError(f"{method} refused: {LEAKY_MESSAGE}")
        found = self.rows.get(document_id)
        if found is None or found.company_id != company_id:
            raise ReadModelError(f"document {document_id} does not exist for this company")
        return found

    async def insert(
        self,
        *,
        company_id: uuid.UUID,
        document_id: uuid.UUID,
        kind: DocumentKind,
        name: str,
        storage_path: str,
    ) -> DocumentRecord:
        if "insert" in self.fail_on:
            raise ReadModelError(f"insert refused: {LEAKY_MESSAGE}")
        now = self._now()
        return self._write(
            DocumentRecord(
                id=document_id,
                company_id=company_id,
                kind=kind,
                name=name,
                storage_path=storage_path,
                status=DocumentStatus.UPLOADED,
                pages=0,
                created_at=now,
                updated_at=now,
            )
        )

    async def mark_parsed(
        self,
        *,
        company_id: uuid.UUID,
        document_id: uuid.UUID,
        pages: int,
        unread_pages: Sequence[int],
    ) -> DocumentRecord:
        found = self._own("mark_parsed", company_id, document_id)
        return self._write(
            found.model_copy(
                update={
                    "status": DocumentStatus.PARSED,
                    "pages": pages,
                    "unread_pages": tuple(unread_pages),
                    "updated_at": self._now(),
                }
            )
        )

    async def mark_embedded(
        self, *, company_id: uuid.UUID, document_id: uuid.UUID
    ) -> DocumentRecord:
        return self._advance("mark_embedded", company_id, document_id, DocumentStatus.EMBEDDED)

    async def mark_ready(
        self, *, company_id: uuid.UUID, document_id: uuid.UUID
    ) -> DocumentRecord:
        return self._advance("mark_ready", company_id, document_id, DocumentStatus.READY)

    async def mark_failed(
        self, *, company_id: uuid.UUID, document_id: uuid.UUID, reason: str
    ) -> DocumentRecord:
        found = self._own("mark_failed", company_id, document_id)
        return self._write(
            found.model_copy(
                update={
                    "status": DocumentStatus.FAILED,
                    "failure_reason": reason,
                    "updated_at": self._now(),
                }
            )
        )

    async def get(
        self, *, company_id: uuid.UUID, document_id: uuid.UUID
    ) -> DocumentRecord | None:
        found = self.rows.get(document_id)
        return found if found is not None and found.company_id == company_id else None

    async def list(self, *, company_id: uuid.UUID) -> tuple[DocumentRecord, ...]:
        own = [record for record in self.rows.values() if record.company_id == company_id]
        return tuple(sorted(own, key=lambda record: record.created_at, reverse=True))

    def _advance(
        self,
        method: str,
        company_id: uuid.UUID,
        document_id: uuid.UUID,
        status: DocumentStatus,
    ) -> DocumentRecord:
        found = self._own(method, company_id, document_id)
        return self._write(
            found.model_copy(update={"status": status, "updated_at": self._now()})
        )

    def history_of(self, document_id: uuid.UUID) -> list[DocumentRecord]:
        return [record for record in self.history if record.id == document_id]

    def statuses_of(self, document_id: uuid.UUID) -> list[DocumentStatus]:
        return [record.status for record in self.history_of(document_id)]


@dataclass
class Harness:
    """One pipeline and every fake it was built from, so a test can look at any of them."""

    store: FakeStore
    parser: FakeParser
    embedder: FakeEmbedder
    writer: FakeChunkWriter
    records: InMemoryRecords
    pipeline: DocumentPipeline


def harness(
    *,
    pages: Sequence[str] = ("Seite eins: ISO 27001 Zertifikat.", "Seite zwei: Umsatz 2025."),
    store: FakeStore | None = None,
    parser: FakeParser | None = None,
    embedder: FakeEmbedder | None = None,
    writer: FakeChunkWriter | None = None,
    records: InMemoryRecords | None = None,
) -> Harness:
    """The pipeline over fakes. Pass a fake to make one collaborator fail or observe."""
    store = store if store is not None else FakeStore()
    parser = parser if parser is not None else FakeParser(pages)
    embedder = embedder if embedder is not None else FakeEmbedder()
    writer = writer if writer is not None else FakeChunkWriter()
    records = records if records is not None else InMemoryRecords()
    pipeline = DocumentPipeline(
        store=store,
        parser=parser,
        chunker=Chunker(
            chunk_tokens=CHUNK_TOKENS, overlap_tokens=OVERLAP_TOKENS, encoder=CharacterEncoder()
        ),
        embedder=embedder,
        chunk_writer=writer,
        records=records,
    )
    return Harness(store, parser, embedder, writer, records, pipeline)


def upload(filename: str = ORIGINAL_FILENAME, content: bytes = PDF_BYTES) -> Upload:
    return Upload(filename=filename, content_type=DEFAULT_CONTENT_TYPE, content=content)


async def run(
    h: Harness, *, kind: DocumentKind = DocumentKind.COMPANY_EVIDENCE, up: Upload | None = None
) -> DocumentRecord:
    """`accept` then `process`, as the router does across the 202 boundary."""
    up = up if up is not None else upload()
    accepted = await h.pipeline.accept(company_id=COMPANY_ID, kind=kind, upload=up)
    return await h.pipeline.process(accepted, up)


# ------------------------------------------------------------------------------ accept


@pytest.mark.anyio
async def test_accept_records_the_uploaded_row_without_touching_storage() -> None:
    # Arrange
    h = harness()

    # Act
    record = await h.pipeline.accept(
        company_id=COMPANY_ID, kind=DocumentKind.COMPANY_EVIDENCE, upload=upload()
    )

    # Assert
    assert record.status is DocumentStatus.UPLOADED
    assert record.company_id == COMPANY_ID
    assert record.kind is DocumentKind.COMPANY_EVIDENCE
    assert record.bid_id is None
    assert h.records.statuses_of(record.id) == [DocumentStatus.UPLOADED]
    assert h.store.uploads == [] and h.parser.sources == []


@pytest.mark.anyio
async def test_accept_keeps_the_original_filename_and_sanitises_only_the_key() -> None:
    """The row is what the bidder sees; the key is what Storage gets (S2.2.2)."""
    # Act
    h = harness()
    record = await h.pipeline.accept(
        company_id=COMPANY_ID, kind=DocumentKind.COMPANY_EVIDENCE, upload=upload()
    )

    # Assert
    assert record.name == ORIGINAL_FILENAME
    assert record.storage_path == object_key(
        company_id=str(COMPANY_ID), document_id=str(record.id), filename=ORIGINAL_FILENAME
    )
    assert record.storage_path.startswith(f"{COMPANY_ID}/{record.id}/")
    assert " " not in record.storage_path and "(" not in record.storage_path
    assert "Ü" not in record.storage_path


@pytest.mark.anyio
async def test_accept_mints_a_fresh_id_per_upload() -> None:
    h = harness()
    kind = DocumentKind.COMPANY_EVIDENCE

    first = await h.pipeline.accept(company_id=COMPANY_ID, kind=kind, upload=upload())
    second = await h.pipeline.accept(company_id=COMPANY_ID, kind=kind, upload=upload())

    assert first.id != second.id
    assert len(h.records.rows) == 2


# -------------------------------------------------------------------------- happy path


@pytest.mark.anyio
async def test_company_evidence_moves_through_every_status_in_order() -> None:
    # Act
    h = harness()
    final = await run(h)

    # Assert
    assert final.status is DocumentStatus.READY
    assert h.records.statuses_of(final.id) == [
        DocumentStatus.UPLOADED,
        DocumentStatus.PARSED,
        DocumentStatus.EMBEDDED,
        DocumentStatus.READY,
    ]
    assert final.failure_reason is None
    assert final.updated_at > final.created_at


@pytest.mark.anyio
async def test_the_store_gets_the_bytes_under_the_key_the_row_already_names() -> None:
    """The key is computed before a byte moves, so the row and the object cannot disagree."""
    h = harness()
    final = await run(h)

    (uploaded,) = h.store.uploads
    assert uploaded["content"] == PDF_BYTES
    assert uploaded["content_type"] == DEFAULT_CONTENT_TYPE
    assert uploaded["filename"] == ORIGINAL_FILENAME
    assert uploaded["key"] == final.storage_path


@pytest.mark.anyio
async def test_parsed_is_visible_while_the_embeddings_request_is_in_flight() -> None:
    """Each transition is written as it happens; a poller sees progress, not a spinner."""
    # Arrange
    records = InMemoryRecords()
    embedder = FakeEmbedder(observe=lambda: [row.status for row in records.history])
    h = harness(records=records, embedder=embedder)

    # Act
    await run(h)

    # Assert
    (seen_at_embed_time,) = embedder.observed
    assert seen_at_embed_time == [DocumentStatus.UPLOADED, DocumentStatus.PARSED]


@pytest.mark.anyio
async def test_chunks_and_vectors_are_paired_and_written_under_the_company() -> None:
    # Act
    h = harness()
    final = await run(h)

    # Assert
    (insert,) = h.writer.inserts
    assert insert["company_id"] == COMPANY_ID
    assert insert["document_id"] == final.id
    chunks = insert["chunks"]
    assert len(chunks) >= 1
    assert [chunk.chunk.text for chunk in chunks] == h.embedder.calls[0]
    assert all(len(chunk.embedding) == DIMENSIONS for chunk in chunks)
    assert all(chunk.chunk.document_id == str(final.id) for chunk in chunks)
    assert h.parser.sources == [PDF_BYTES]


@pytest.mark.anyio
async def test_only_company_evidence_is_embedded_at_upload() -> None:
    """Tender vectors need a bid (`tender_chunks.bid_id` is NOT NULL), and there is none yet."""
    assert frozenset({DocumentKind.COMPANY_EVIDENCE}) == EMBEDDED_KINDS


@pytest.mark.anyio
@pytest.mark.parametrize("kind", [DocumentKind.TENDER_DOCUMENT, DocumentKind.TENDER_NOTICE])
async def test_a_tender_document_is_parsed_then_ready_and_never_embedded(
    kind: DocumentKind,
) -> None:
    # Act
    h = harness()
    final = await run(h, kind=kind)

    # Assert
    assert final.status is DocumentStatus.READY
    assert h.records.statuses_of(final.id) == [
        DocumentStatus.UPLOADED,
        DocumentStatus.PARSED,
        DocumentStatus.READY,
    ]
    assert h.embedder.calls == [] and h.writer.inserts == []
    assert len(h.store.uploads) == 1, "the file is stored for the graph to fetch (S3.1.1)"


@pytest.mark.anyio
async def test_parsing_and_storing_run_off_the_event_loop() -> None:
    """pymupdf and the Storage client are synchronous; a 191-page pack must not stall polls."""
    h = harness()
    await run(h)

    assert h.parser.threads and h.store.threads
    assert all(thread is not threading.main_thread() for thread in h.parser.threads)
    assert all(thread is not threading.main_thread() for thread in h.store.threads)


# ------------------------------------------------------------------------ unread pages


@pytest.mark.anyio
async def test_unread_pages_are_counted_on_the_row_and_left_out_of_the_chunks() -> None:
    """The story's second criterion: the count is shown; S2.1.1: nothing is dropped silently."""
    # Arrange
    h = harness(pages=("Seite eins.", "", "Seite drei.", "\n\n", "Seite fünf."))

    # Act
    final = await run(h)

    # Assert
    assert final.pages == 5
    assert final.unread_pages == (2, 4)
    (insert,) = h.writer.inserts
    cited = {page for chunk in insert["chunks"] for page in chunk.chunk.pages}
    assert cited == {1, 3, 5}


@pytest.mark.anyio
async def test_the_page_counts_are_written_with_parsed_not_at_the_end() -> None:
    h = harness(pages=("Seite eins.", ""))

    final = await run(h)

    uploaded_row, parsed_row, *_rest = h.records.history_of(final.id)
    assert uploaded_row.pages == 0 and uploaded_row.unread_pages == ()
    assert parsed_row.status is DocumentStatus.PARSED
    assert parsed_row.pages == 2 and parsed_row.unread_pages == (2,)


# ------------------------------------------------------------------------------ failure


@pytest.mark.anyio
async def test_a_failing_parse_marks_failed_with_a_readable_reason_and_logs_the_cause(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Arrange
    h = harness(parser=FakeParser((), error=ParserError(LEAKY_MESSAGE)))

    # Act
    with caplog.at_level(logging.ERROR, logger="crossbid.ingestion.pipeline"):
        final = await run(h)

    # Assert -- the row
    assert final.status is DocumentStatus.FAILED
    assert final.failure_reason == UNREADABLE_REASON
    assert h.records.statuses_of(final.id) == [DocumentStatus.UPLOADED, DocumentStatus.FAILED]
    assert h.embedder.calls == [] and h.writer.inserts == []

    # Assert -- the log carries the exception in full, once
    (entry,) = caplog.records
    assert entry.exc_info is not None
    assert isinstance(entry.exc_info[1], ParserError)
    assert str(final.id) in entry.getMessage()
    assert "ParserError" in entry.getMessage()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("build", "reason"),
    [
        (
            lambda: harness(store=FakeStore(error=StorageError(LEAKY_MESSAGE))),
            STORE_FAILED_REASON,
        ),
        (
            lambda: harness(parser=FakeParser((), error=ParserError(LEAKY_MESSAGE))),
            UNREADABLE_REASON,
        ),
        (lambda: harness(pages=("", "\n\n  \n")), NO_READABLE_TEXT_REASON),
        (
            lambda: harness(embedder=FakeEmbedder(error=EmbeddingsError(LEAKY_MESSAGE))),
            EMBED_FAILED_REASON,
        ),
        (
            lambda: harness(writer=FakeChunkWriter(error=ChunkStoreError(LEAKY_MESSAGE))),
            SAVE_FAILED_REASON,
        ),
        (
            lambda: harness(embedder=FakeEmbedder(error=RuntimeError(LEAKY_MESSAGE))),
            UNEXPECTED_FAILURE_REASON,
        ),
        (lambda: harness(embedder=FakeEmbedder(extra_vectors=1)), UNEXPECTED_FAILURE_REASON),
    ],
    ids=[
        "storage",
        "parser",
        "no-readable-text",
        "embeddings",
        "chunk-store",
        "unexpected",
        "vector-count-mismatch",
    ],
)
async def test_each_failure_becomes_one_of_the_closed_reasons_and_leaks_nothing(
    build: Callable[[], Harness], reason: str, caplog: pytest.LogCaptureFixture
) -> None:
    # Act
    h = build()
    with caplog.at_level(logging.ERROR, logger="crossbid.ingestion.pipeline"):
        final = await run(h)

    # Assert
    assert final.status is DocumentStatus.FAILED
    assert final.failure_reason == reason
    assert reason in FAILURE_REASONS
    assert final.failure_reason is not None
    assert not any(marker in final.failure_reason for marker in LEAK_MARKERS)
    assert len(caplog.records) == 1 and caplog.records[0].exc_info is not None


@pytest.mark.anyio
async def test_a_scanned_pdf_fails_but_keeps_its_page_counts() -> None:
    """Every page unread: `parsed` is written first, so the row says what was looked at."""
    h = harness(pages=("", "   "))

    final = await run(h)

    assert final.status is DocumentStatus.FAILED
    assert final.failure_reason == NO_READABLE_TEXT_REASON
    assert final.pages == 2 and final.unread_pages == (1, 2)
    assert h.records.statuses_of(final.id) == [
        DocumentStatus.UPLOADED,
        DocumentStatus.PARSED,
        DocumentStatus.FAILED,
    ]


@pytest.mark.anyio
async def test_a_scanned_tender_document_fails_too() -> None:
    """A tender pack with no text would let S4.3.1 enable Start on nothing."""
    h = harness(pages=("",))

    final = await run(h, kind=DocumentKind.TENDER_DOCUMENT)

    assert final.status is DocumentStatus.FAILED
    assert final.failure_reason == NO_READABLE_TEXT_REASON


def test_every_failure_reason_is_a_sentence_a_bidder_can_act_on() -> None:
    assert len(FAILURE_REASONS) == len(set(FAILURE_REASONS))
    for reason in FAILURE_REASONS:
        assert reason.endswith("."), reason
        assert not any(marker in reason for marker in LEAK_MARKERS), reason


@pytest.mark.anyio
async def test_a_failing_failure_write_propagates_rather_than_vanishing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`process` swallows a document failure into the row, never a database failure."""
    h = harness(
        parser=FakeParser((), error=ParserError("boom")),
        records=InMemoryRecords(fail_on=frozenset({"mark_failed"})),
    )

    with (
        caplog.at_level(logging.ERROR, logger="crossbid.ingestion.pipeline"),
        pytest.raises(ReadModelError, match="mark_failed refused"),
    ):
        await run(h)


@pytest.mark.anyio
async def test_a_failing_transition_write_is_itself_reported_as_a_failure() -> None:
    """The read model raising mid-run is unexpected; the row still ends `failed`."""
    h = harness(records=InMemoryRecords(fail_on=frozenset({"mark_embedded"})))

    final = await run(h)

    assert final.status is DocumentStatus.FAILED
    assert final.failure_reason == UNEXPECTED_FAILURE_REASON


# ------------------------------------------------------------------------------ aclose


@pytest.mark.anyio
async def test_aclose_releases_the_embedder_once() -> None:
    h = harness()

    await h.pipeline.aclose()

    assert h.embedder.closed == 1
