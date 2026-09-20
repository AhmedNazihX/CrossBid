"""The tender pack's vectors, written under the bid that owns them.

**The gap this closes.** `tender_chunks` has existed since `0001_init.sql` and
`insert_tender_chunks` since S2.2.1, and until now nothing called it: `tender_rag_search`
searched a table that was permanently empty, and so answered "nothing found" to every
question anyone ever asked it -- inside `check_reqs`, where it is one of four tools, and
inside the chat (S3.5.1), where the tender half of "ask the tender" depends on it entirely.
The failure was invisible in exactly the way this codebase is worst at catching: the tool
worked, its tests passed, its answer was well-formed, and it was empty.

**Why it happens here and not at upload.** `ingestion/pipeline.py` explains the split and it
was always right: `parse_docs` already holds every document parsed, so the vectors are one
step from the text that produced them, and nothing has to read the file back twice.

The *original* reason was narrower and no longer applies -- `tender_chunks.bid_id` was
`NOT NULL`, and a tender document is uploaded before its bid exists, so at upload there was
nowhere to put the vectors. Migration 0012 removed that column (ADR-0103). Indexing stays here
anyway, because embedding at upload would pay for every document a bidder never starts a bid
with; the reuse guard below is what makes the *second* analysis free.

**Flagged chunks are withheld, and the same PDF is still fully extracted.** This corpus is
read by a RAG tool and pasted into prompts as evidence, which is precisely the path ADR-0049
withholds on -- a flagged chunk retrieved into a check prompt is the attack working. The
*pages* of that same document still go to `extract_reqs` in full, reported rather than
dropped, because dropping them would let an attacker delete the requirement they least want
checked. One document, two paths, two answers, and `ingestion/guarding.py` is where the rule
is written once for both corpora.

**Indexing is idempotent.** A process that dies before `parse_docs` finishes runs it again
from the start, so every write goes through `replace_tender_chunks`: delete this document's
rows for this bid, then insert, in one transaction. Without it the second attempt would
double the corpus and every retrieval would return each passage twice.

**A document that fails to index does not fail the bid.** It is reported as an extraction
problem and the run goes on, for the same reason S3.1.1 keeps going when one file of
twenty-eight will not open: a bid that has already been paid for must not be lost to one
document, and a reviewer who is told which document is missing can judge what the gap is
worth. What must never happen is silence -- which is exactly what the missing writer did.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Sequence
from typing import Protocol

from crossbid.ingestion.chunker import Chunk
from crossbid.ingestion.embeddings import EmbeddedChunk, Embedder, embed_chunks
from crossbid.ingestion.guarding import partition_by_guard, review_flagged
from crossbid.ingestion.injection_review import InjectionConfirmer
from crossbid.ingestion.parser import ParsedDocument

logger = logging.getLogger(__name__)


class Chunking(Protocol):
    """`Chunker.chunk`, declared here like this module's other seams rather than imported
    from `pipeline.py` — the two indexers are siblings, not one built on the other."""

    def chunk(self, document: ParsedDocument) -> Sequence[Chunk]: ...


class TenderChunkWriter(Protocol):
    """The slice of `ChunkVectorStore` this needs. See `replace_tender_chunks` for why."""

    async def count_tender_chunks(
        self, *, company_id: uuid.UUID, document_id: uuid.UUID
    ) -> int: ...

    async def replace_tender_chunks(
        self,
        *,
        company_id: uuid.UUID,
        document_id: uuid.UUID,
        chunks: Sequence[EmbeddedChunk],
    ) -> int: ...


class TenderIndexer(Protocol):
    """What `parse_docs` calls once per parsed tender document."""

    async def __call__(
        self, *, company_id: uuid.UUID, bid_id: uuid.UUID, parsed: ParsedDocument
    ) -> int: ...


class ChunkingTenderIndexer:
    """Chunk, scan, review, embed, replace. Holds no per-document state."""

    def __init__(
        self,
        *,
        chunker: Chunking,
        embedder: Embedder,
        writer: TenderChunkWriter,
        confirm: InjectionConfirmer,
        force: bool = False,
    ) -> None:
        self._chunker = chunker
        self._embedder = embedder
        self._writer = writer
        self._confirm = confirm
        self._force = force
        """Index even when the document already has passages.

        For the one case the reuse guard must not win: a chunker or embedding model changed
        and the stored vectors are stale. `scripts/index_pack.py` sets it; nothing in a
        request path does."""

    async def __call__(
        self, *, company_id: uuid.UUID, bid_id: uuid.UUID, parsed: ParsedDocument
    ) -> int:
        """Index one document and return how many passages the bid can now retrieve.

        **A document is embedded once, not once per analysis (ADR-0103).** Its passages are
        keyed by document, so a second bid citing the same file retrieves the first one's
        corpus. Re-embedding would cost real money for byte-identical vectors, and on a
        200-page pack it is most of what a run spends.
        """
        document_id = uuid.UUID(parsed.document_id)
        if not self._force:
            existing = await self._writer.count_tender_chunks(
                company_id=company_id, document_id=document_id
            )
            if existing:
                logger.info(
                    "bid %s document %s already indexed: reusing %d passage(s)",
                    bid_id,
                    document_id,
                    existing,
                )
                return existing
        # In a worker thread for the reason `pipeline.py` gives: chunking is synchronous
        # and a pack is hundreds of pages, and this runs inside a bid whose browser is
        # polling `GET /bids/{id}` every two seconds.
        chunks = await asyncio.to_thread(self._chunker.chunk, parsed)
        _, suspected = partition_by_guard(chunks)
        kept, withheld = await review_flagged(chunks, suspected, self._confirm, document_id)
        for number, finding in withheld:
            logger.warning(
                "bid %s document %s chunk %d withheld from the tender corpus: %s — %r",
                bid_id,
                document_id,
                number,
                ", ".join(signal.value for signal in finding.signals),
                finding.excerpt,
            )
        written = await self._writer.replace_tender_chunks(
            company_id=company_id,
            document_id=document_id,
            chunks=await embed_chunks(self._embedder, kept),
        )
        logger.info(
            "bid %s document %s indexed: %d passage(s) retrievable, %d withheld",
            bid_id,
            document_id,
            written,
            len(withheld),
        )
        return written
