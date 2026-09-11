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

`InMemoryRecords` and the other fakes live in `conftest.py`, because `test_documents_router.py`
runs the same pipeline behind the HTTP layer and asserts on the same transitions. One
definition, or the two stories stop adding up.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable

import pytest

from crossbid.ingestion.embeddings import ChunkStoreError, EmbeddingsError
from crossbid.ingestion.parser import ParserError
from crossbid.ingestion.pipeline import (
    EMBED_FAILED_REASON,
    EMBEDDED_KINDS,
    FAILURE_REASONS,
    NO_READABLE_TEXT_REASON,
    SAVE_FAILED_REASON,
    STORE_FAILED_REASON,
    UNEXPECTED_FAILURE_REASON,
    UNREADABLE_REASON,
    Upload,
)
from crossbid.ingestion.storage import DEFAULT_CONTENT_TYPE, StorageError, object_key
from crossbid.models import DocumentKind
from crossbid.readmodel.documents import DocumentRecord, DocumentStatus, ReadModelError
from tests.conftest import (
    DIMENSIONS,
    LEAK_MARKERS,
    LEAKY_MESSAGE,
    ORIGINAL_FILENAME,
    PDF_BYTES,
    FakeChunkWriter,
    FakeEmbedder,
    FakeParser,
    FakeStore,
    Harness,
    InMemoryRecords,
    harness,
    upload,
)

COMPANY_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
OTHER_COMPANY_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")


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
