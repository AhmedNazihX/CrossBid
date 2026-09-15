"""ADR-0057's fix, against the real database and the real embeddings endpoint. Marked `live`.

**What this proves that no offline test can.** `tender_chunks` had no writer for three
increments and every unit test passed throughout, because each one inserted the rows it then
retrieved. The claim that failed in production was never "the query is right" — it was
"something puts rows there", and only a run against a real Postgres, a real Storage object
and the real embeddings endpoint can say so.

So this test does the whole chain on one document: read the row, fetch the PDF from Storage,
parse it, chunk it, scan it, embed it, write it, and then retrieve it with a query in the
document's own language. A green run means a bid's tender pack is searchable; that is the
sentence that was false until ADR-0057.

**It finds its own subject and skips when there is none.** Document ids are environment
facts, so hard-coding the Frankfurt ones would make this pass for one developer and fail for
everyone else. It takes the most recent `tender_document` in `ready` and skips if the project
has none.

**It cleans up after itself.** `replace_tender_chunks` is delete-then-insert, so re-running
this leaves one copy rather than two — but a test that quietly seeds a demo database is a
test that lies about the state it found, so the rows it wrote are removed at the end. If you
*want* the bid left searchable, index it deliberately rather than by running a test.

Cost is a fraction of a cent: one embeddings call per chunk batch at $0.027/1M tokens, and
one for the query. It opens a real pool, so it needs `DATABASE_URL`, and it skips without it.
"""

from __future__ import annotations

import uuid

import pytest

from crossbid.agent.nodes.parse_docs import storage_fetcher
from crossbid.db import Database
from crossbid.ingestion.chunker import Chunker
from crossbid.ingestion.embeddings import ChunkVectorStore, EmbeddingsClient
from crossbid.ingestion.injection_review import confirm_every_finding
from crossbid.ingestion.pymupdf_parser import PyMuPDFParser
from crossbid.ingestion.storage import company_document_store
from crossbid.ingestion.tender_index import ChunkingTenderIndexer
from crossbid.models.tender import DocumentKind
from crossbid.readmodel.bids import BidDocumentRow
from crossbid.readmodel.documents import DocumentStatus
from crossbid.settings import Settings, SettingsError, load_settings

pytestmark = [pytest.mark.live, pytest.mark.anyio]

FIND_A_TENDER_DOCUMENT = """
select d.id, d.company_id, d.bid_id, d.name, d.storage_path
from documents d
where d.kind = 'tender_document' and d.status = 'ready' and d.bid_id is not null
order by d.created_at desc
limit 1
"""

COUNT_CHUNKS = """
select count(*) as n from tender_chunks
where company_id = %(company_id)s and bid_id = %(bid_id)s and document_id = %(document_id)s
"""

DELETE_CHUNKS = """
delete from tender_chunks
where company_id = %(company_id)s and bid_id = %(bid_id)s and document_id = %(document_id)s
"""


def settings_or_skip() -> Settings:
    try:
        settings = load_settings()
    except SettingsError as exc:  # pragma: no cover - environment, not logic
        pytest.skip(f"settings are not configured: {exc}")
    if settings.env.openrouter_api_key is None:  # pragma: no cover - environment
        pytest.skip("OPENROUTER_API_KEY is not set")
    if settings.env.database_url is None:  # pragma: no cover - environment
        pytest.skip("DATABASE_URL is not set")
    return settings


async def test_a_real_tender_document_becomes_retrievable() -> None:
    # Arrange
    settings = settings_or_skip()
    assert settings.env.database_url is not None
    db = await Database.connect(settings.env.database_url.get_secret_value())
    scope: dict[str, object] = {}
    try:
        async with db.connection() as connection, connection.cursor() as cursor:
            await cursor.execute(FIND_A_TENDER_DOCUMENT)
            row = await cursor.fetchone()
        if row is None:  # pragma: no cover - depends on the project's data
            pytest.skip("no tender_document in `ready` to index")

        scope = {
            "company_id": row["company_id"],
            "bid_id": row["bid_id"],
            "document_id": row["id"],
        }
        store = company_document_store(settings)
        content = await storage_fetcher(store)(
            str(row["company_id"]),
            BidDocumentRow(
                id=str(row["id"]),
                name=row["name"],
                storage_path=row["storage_path"],
                kind=DocumentKind.TENDER_DOCUMENT,
                status=DocumentStatus.READY,
                bid_id=str(row["bid_id"]),
                pages=0,
            ),
        )
        parsed = PyMuPDFParser().parse(content, document_id=str(row["id"]))
        ingestion = settings.runtime.ingestion
        index = ChunkingTenderIndexer(
            chunker=Chunker(
                chunk_tokens=ingestion.chunk_tokens, overlap_tokens=ingestion.chunk_overlap
            ),
            embedder=EmbeddingsClient(settings),
            writer=ChunkVectorStore(db),
            confirm=confirm_every_finding,
        )

        # Act
        written = await index(
            company_id=uuid.UUID(str(row["company_id"])),
            bid_id=uuid.UUID(str(row["bid_id"])),
            parsed=parsed,
        )

        # Assert -- the rows are really there, which is the claim that was false
        assert written > 0, "a readable tender document produced no passages"
        async with db.connection() as connection, connection.cursor() as cursor:
            await cursor.execute(COUNT_CHUNKS, scope)
            counted = await cursor.fetchone()
        assert counted is not None and counted["n"] == written

        # Assert -- and they come back out, which is what `tender_rag_search` needs
        hits = await ChunkVectorStore(db).search_tender_chunks(
            company_id=uuid.UUID(str(row["company_id"])),
            bid_id=uuid.UUID(str(row["bid_id"])),
            embedding=await EmbeddingsClient(settings).embed_query(
                "exigences et critères de sélection du marché"
            ),
            limit=3,
        )
        assert hits, "rows were written and nothing could be retrieved"
        assert all(hit.text.strip() for hit in hits)
    finally:
        if scope:
            async with db.connection() as connection, connection.cursor() as cursor:
                await cursor.execute(DELETE_CHUNKS, scope)
        await db.close()
