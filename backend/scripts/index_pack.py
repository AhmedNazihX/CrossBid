"""S7.1 — seed a throwaway Postgres with a tender pack's vectors, so retrieval can be scored.

    DATABASE_URL=postgresql://crossbid:crossbid@localhost:55432/crossbid_eval \
      uv run python scripts/index_pack.py de fr en

**Why a throwaway and not Frankfurt.** A retrieval figure measured against one person's
Supabase project is a claim nobody else can check, and it drifts as that project's data
changes — the same weakness that made the 2026-09-13 cost figure stale. Indexed here, the
corpus is rebuilt from committed fixtures by anyone with Docker, which is what makes the
number in `REPORT.md` reproducible. CI already runs a `pgvector/pgvector:pg16` service for
`make test-db`; this uses the same image.

**It spends almost nothing.** Embedding is the only model call: `text-embedding-3-small` at
~$0.027 per million tokens, so all three packs together are about a cent. No extraction, no
chat — those are separate scripts. Re-running is safe and cheap: `replace_tender_chunks`
deletes a document's rows for the bid before inserting, so a second run neither doubles the
corpus nor costs more than the first.

**The corpus is built the way the product builds it, not the way a test would.** The same
`Chunker` sizes from the same settings block, the same `EmbeddingsClient`, the same
`ChunkingTenderIndexer`, and the same injection guard — because a retrieval score measured
over a corpus chunked differently from the shipping one would describe a system nobody runs.
That is also why flagged chunks are withheld here exactly as they are in a real bid
(ADR-0049): the retrieval eval should see the corpus a bidder's questions actually reach.

Ids are derived with `uuid5` from the pack name, so the company, the bid and every document
are the same on every run and a question set can name a bid id that will still exist
tomorrow.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from collections.abc import Sequence
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    # `[tool.uv] package = false`, so `crossbid` is importable only via the project root.
    sys.path.insert(0, str(BACKEND_DIR))

from crossbid.db import Database, DatabaseError  # noqa: E402
from crossbid.demo.company import PACK_DIR as COMPANY_PACK_DIR  # noqa: E402
from crossbid.demo.company import load_pack  # noqa: E402
from crossbid.eval.packrun import PACKS, TenderPack, pack_paths  # noqa: E402
from crossbid.ingestion.chunker import Chunker  # noqa: E402
from crossbid.ingestion.embeddings import ChunkVectorStore, EmbeddingsClient  # noqa: E402
from crossbid.ingestion.injection_review import (  # noqa: E402
    ModelInjectionConfirmer,
    confirm_every_finding,
)
from crossbid.ingestion.parser import ParserError  # noqa: E402
from crossbid.ingestion.pipeline import Upload, build_pipeline  # noqa: E402
from crossbid.ingestion.pymupdf_parser import PyMuPDFParser  # noqa: E402
from crossbid.ingestion.tender_index import ChunkingTenderIndexer  # noqa: E402
from crossbid.models.company import CompanyProfile  # noqa: E402
from crossbid.models.tender import DocumentKind  # noqa: E402
from crossbid.readmodel.bids import attach_documents, create_bid  # noqa: E402
from crossbid.readmodel.companies import CompaniesReadModel  # noqa: E402
from crossbid.readmodel.documents import DocumentsReadModel  # noqa: E402
from crossbid.settings import Settings, SettingsError, load_settings  # noqa: E402

EVAL_NAMESPACE = uuid.UUID("6f1b6f1e-8b6b-5a1e-9c2a-4d6e5f0a1b2c")
"""A fixed namespace so every derived id is stable across runs and machines."""

INPUT_ERROR = 2


def ids_for(pack: TenderPack) -> tuple[uuid.UUID, uuid.UUID]:
    """The company and bid this pack is always indexed under."""
    return (
        uuid.uuid5(EVAL_NAMESPACE, f"company:{pack.name}"),
        uuid.uuid5(EVAL_NAMESPACE, f"bid:{pack.name}"),
    )


QUALIFIED = "demo"
UNDER_QUALIFIED = "small"

SMALL_TURNOVER = 820_000.0
SMALL_STAFF_FTE = 6.0
SMALL_STAFF_RELEVANT = 4.0


def _profile(pack: TenderPack, which: str) -> CompanyProfile:
    """The bidder, at one of two sizes.

    `demo` is the committed demo pack's own profile — the fictional German GmbH whose figures
    were written to clear the DE tender's minimums (turnover 3.42M / 3.985M / 4.31M against a
    3.0M demand). `small` is the same company scaled down below every one of them.

    **The scaling is the whole no-go experiment.** Thresholds are compared arithmetically
    against these fields, not judged by a model, so a company under the minimum produces an
    `unsupported` mandatory row, a blocking gap and a `no_go` — as agent output rather than as
    a staged screenshot. Nothing else about the two runs differs: same tender, same evidence
    documents, same models. The evidence pack is deliberately *not* reduced, so the run also
    shows what the agent does when a company's documents say something its profile does not.
    """
    profile = load_pack().profile
    if which == QUALIFIED:
        return profile
    return profile.model_copy(
        update={
            "name": f"{profile.name} (klein)",
            "staff_fte": SMALL_STAFF_FTE,
            "staff_fte_relevant": SMALL_STAFF_RELEVANT,
            # A tuple, not a list: `CompanyProfile.turnover` is typed `tuple[...]` and a
            # list round-trips through the jsonb column with a serializer warning.
            "turnover": tuple(
                entry.model_copy(update={"amount": SMALL_TURNOVER})
                for entry in profile.turnover
            ),
        }
    )


async def _seed_scope(
    database: Database, settings: Settings, pack: TenderPack, which: str
) -> tuple[uuid.UUID, uuid.UUID, list[tuple[uuid.UUID, Path]]]:
    """Company, bid and document rows — everything `tender_chunks` has a foreign key to."""
    company_id, bid_id = ids_for(pack)
    companies = CompaniesReadModel(database)
    profile = _profile(pack, which)
    if (
        await companies.create(company_id=company_id, owner_user_id=company_id, profile=profile)
        is None
    ):
        # A second run: `create` is `on conflict do nothing`, so the row is whatever the last
        # run wrote. `--profile` has to be able to change it, or the no-go experiment would
        # silently score the qualified company.
        await companies.save(company_id=company_id, profile=profile)

    documents = DocumentsReadModel(database)
    files = [path for path in pack_paths(pack.directory(BACKEND_DIR)) if path.suffix == ".pdf"]
    rows: list[tuple[uuid.UUID, Path]] = []
    for path in files:
        document_id = uuid.uuid5(EVAL_NAMESPACE, f"doc:{pack.name}:{path.name}")
        if await documents.get(company_id=company_id, document_id=document_id) is None:
            await documents.insert(
                company_id=company_id,
                document_id=document_id,
                kind=DocumentKind.TENDER_DOCUMENT,
                name=path.name,
                storage_path=f"{company_id}/{path.stem}/{path.name}",
            )
            await documents.mark_ready(company_id=company_id, document_id=document_id)
        rows.append((document_id, path))

    existing = await _bid_exists(database, bid_id)
    if not existing:
        bid = await create_bid(
            database,
            company_id=str(company_id),
            notice_number=pack.notice_number,
            title=pack.title,
            source_language=pack.source_language,
            bidder_language=pack.bidder_language,
        )
        await _rename_bid(database, old=bid.id, new=bid_id)
        await attach_documents(
            database,
            company_id=str(company_id),
            bid_id=str(bid_id),
            document_ids=[str(document_id) for document_id, _ in rows],
        )
    return company_id, bid_id, rows


async def _bid_exists(database: Database, bid_id: uuid.UUID) -> bool:
    async with database.connection() as conn:
        cursor = await conn.execute("select 1 from bids where id = %(id)s", {"id": bid_id})
        return await cursor.fetchone() is not None


async def _rename_bid(database: Database, *, old: str, new: uuid.UUID) -> None:
    """`create_bid` mints its own id; the eval needs a derived one it can name in a fixture."""
    async with database.connection() as conn:
        await conn.execute(
            "update bids set id = %(new)s, thread_id = %(thread)s where id = %(old)s",
            {"new": new, "thread": f"bid-{new}", "old": uuid.UUID(old)},
        )


class LocalStore:
    """`pipeline.DocumentStore` for a corpus that is already on disk.

    The pipeline stores the bytes and then reads them back from the `content` it was handed,
    so the store's only job here is to answer with the key the row will carry. Nothing is
    uploaded: the eval corpus is rebuilt from committed fixtures, and a throwaway database
    that needed a Storage bucket would stop being reproducible by anyone with Docker.
    """

    def upload(
        self,
        *,
        company_id: str,
        document_id: str,
        filename: str,
        content: bytes,
        content_type: str = "application/pdf",
    ) -> str:
        return f"{company_id}/{document_id}/{filename}"


async def _index_company_evidence(
    database: Database, settings: Settings, company_id: uuid.UUID
) -> int:
    """The bidder's own ten documents, chunked and embedded into `company_chunks`.

    Without these `company_rag_search` searches an empty table and every requirement comes
    back unsupported for the wrong reason — the same failure `tender_chunks` had for three
    increments (ADR-0057). A no-go produced that way would be an artefact of an empty corpus
    rather than a finding about the company.

    The real `DocumentPipeline` runs: the same chunk sizes, the same embedder, the same
    injection scan. A corpus built any other way would not be the one a bidder's questions
    reach.
    """
    pipeline = build_pipeline(
        settings,
        source=database,
        store=LocalStore(),
        records=DocumentsReadModel(database),
    )
    try:
        written = 0
        for path in sorted((COMPANY_PACK_DIR / "documents").glob("*.pdf")):
            # Scoped by company: `documents.id` is the primary key across every tenant, and
            # each pack's company gets its own copy of the same ten files. Keyed on the
            # filename alone they collide the moment a second pack is indexed.
            document_id = uuid.uuid5(EVAL_NAMESPACE, f"evidence:{company_id}:{path.name}")
            upload = Upload(
                filename=path.name,
                content_type="application/pdf",
                content=path.read_bytes(),
            )
            record = await pipeline.accept(
                company_id=company_id,
                kind=DocumentKind.COMPANY_EVIDENCE,
                upload=upload,
                document_id=document_id,
            )
            record = await pipeline.process(record, upload)
            written += 1
            flagged = len(record.flagged_chunks)
            note = f", {flagged} chunk(s) withheld" if flagged else ""
            print(f"  evidence {path.name}: {record.status.value}{note}")
        return written
    finally:
        await pipeline.aclose()


def _indexer(settings: Settings, database: Database) -> ChunkingTenderIndexer:
    """The production assembly from `build_parse_docs`, read from the same settings block."""
    ingestion = settings.runtime.ingestion
    return ChunkingTenderIndexer(
        chunker=Chunker(
            chunk_tokens=ingestion.chunk_tokens, overlap_tokens=ingestion.chunk_overlap
        ),
        embedder=EmbeddingsClient(settings),
        writer=ChunkVectorStore(database),
        confirm=(
            ModelInjectionConfirmer(settings)
            if settings.runtime.confirm_flagged_chunks
            else confirm_every_finding
        ),
    )


async def _index(database: Database, settings: Settings, pack: TenderPack, which: str) -> int:
    company_id, bid_id, rows = await _seed_scope(database, settings, pack, which)
    indexer = _indexer(settings, database)
    parser = PyMuPDFParser()
    passages = 0
    for document_id, path in rows:
        try:
            parsed = parser.parse(path.read_bytes(), document_id=str(document_id))
        except ParserError as exc:
            print(f"  {path.name}: will not parse ({exc}); skipped", file=sys.stderr)
            continue
        written = await indexer(company_id=company_id, bid_id=bid_id, parsed=parsed)
        passages += written
    print(f"{pack.name}: {passages} passages over {len(rows)} documents")
    print(f"  company {company_id}\n  bid     {bid_id}")
    return passages


async def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__ and __doc__.splitlines()[0])
    parser.add_argument("packs", nargs="+", choices=sorted(PACKS))
    parser.add_argument(
        "--profile",
        choices=(QUALIFIED, UNDER_QUALIFIED),
        default=QUALIFIED,
        help="which size of bidder to seed; 'small' is the no-go experiment",
    )
    parser.add_argument(
        "--with-evidence",
        action="store_true",
        help="also index the demo company's ten evidence documents, so check_reqs has a corpus",
    )
    args = parser.parse_args(argv)
    try:
        settings = load_settings()
    except SettingsError as exc:
        print(f"settings: {exc}", file=sys.stderr)
        return INPUT_ERROR

    dsn = settings.env.database_url
    if dsn is None:
        print("DATABASE_URL is not set — point it at the throwaway pgvector", file=sys.stderr)
        return INPUT_ERROR
    database = await Database.connect(dsn.get_secret_value())
    try:
        for name in args.packs:
            pack = PACKS[name]
            await _index(database, settings, pack, args.profile)
            if args.with_evidence:
                company_id, _ = ids_for(pack)
                count = await _index_company_evidence(database, settings, company_id)
                print(f"{pack.name}: {count} evidence document(s) indexed")
    except DatabaseError as exc:
        print(f"database: {exc}", file=sys.stderr)
        return INPUT_ERROR
    finally:
        await database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
