"""Backfill the tender corpus for bids analysed before anything was writing it.

    DATABASE_URL=… uv run python scripts/index_existing_bids.py              # dry run
    DATABASE_URL=… uv run python scripts/index_existing_bids.py --apply
    DATABASE_URL=… uv run python scripts/index_existing_bids.py --bid <uuid> --apply

**What it is for.** `tender_chunks` is written by `parse_docs._index_one`, which landed in
`a55d14b` on 2026-09-15. Every bid analysed before that was parsed, extracted from, checked
and reviewed **without a searchable copy of its documents ever being kept** — so its matrix is
complete and `tender_rag_search` over it returns nothing, for every question, for ever. A
bidder found that on 2026-09-17 by asking the chat who the buyer was (ADR-0098).

Re-running such a bid would fix it and would re-run the agent: extraction, per-requirement
checking, a verdict, and a review someone has already done. This does the one step that was
missing — parse, chunk, scan, embed, write — and touches nothing else. The matrix, the
verdict, the reviewer's decisions and the run's history are not read and not written.

**What it costs.** Embeddings only: `text-embedding-3-small` at ~$0.027 per million tokens,
so a 25-page pack is a fraction of a cent. No extraction model, no chat model, no verdict.

**Whose key pays.** The company's own, through `settings_for_company`, exactly as an upload or
a run would (S5.4, ADR-0091). A company with no key saved is reported and skipped rather than
quietly charged to the application key — falling back is the behaviour that ADR exists to
remove, and a backfill is not the place to make an exception to it.

**It is safe to run twice.** `ChunkingTenderIndexer` replaces a document's rows for the bid
before inserting (`replace_tender_chunks`), so a second run neither doubles a corpus nor
charges twice for a bid that is already done — such a bid simply does not appear in the
selection, because it now has chunks.

**Dry run by default**, and the dry run costs nothing at all: it lists the bids and the
documents it would index without fetching a byte or embedding a word. `--apply` is the only
thing that writes.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, LiteralString

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    # `[tool.uv] package = false`, so `crossbid` is importable only via the project root.
    sys.path.insert(0, str(BACKEND_DIR))

from crossbid.agent.nodes.parse_docs import storage_fetcher  # noqa: E402
from crossbid.company_keys import NoProviderKeyError, settings_for_company  # noqa: E402
from crossbid.db import Database, DatabaseError  # noqa: E402
from crossbid.ingestion.chunker import Chunker  # noqa: E402
from crossbid.ingestion.embeddings import ChunkVectorStore, EmbeddingsClient  # noqa: E402
from crossbid.ingestion.injection_review import (  # noqa: E402
    ModelInjectionConfirmer,
    confirm_every_finding,
)
from crossbid.ingestion.parser import ParserError  # noqa: E402
from crossbid.ingestion.pymupdf_parser import PyMuPDFParser  # noqa: E402
from crossbid.ingestion.storage import company_document_store  # noqa: E402
from crossbid.ingestion.tender_index import ChunkingTenderIndexer  # noqa: E402
from crossbid.models.tender import DocumentKind  # noqa: E402
from crossbid.readmodel.bids import bid_documents  # noqa: E402
from crossbid.settings import Settings, SettingsError, load_settings  # noqa: E402

INPUT_ERROR: Final = 2

UNINDEXED_BIDS_SQL: Final[LiteralString] = """
select bids.id::text                as bid_id,
       bids.company_id::text        as company_id,
       bids.ted_publication_number  as notice_number,
       bids.title                   as title,
       bids.created_at              as created_at,
       count(documents.id)          as documents
from bids
join documents on documents.bid_id = bids.id
where documents.kind = any(%(kinds)s)
  and not exists (
      select 1 from tender_chunks where tender_chunks.bid_id = bids.id
  )
group by bids.id, bids.company_id, bids.ted_publication_number, bids.title, bids.created_at
order by bids.created_at
"""
"""Bids holding a document a search could have read, and no chunk to read it from.

`not exists` rather than a `left join … having count = 0`: the question is whether the bid has
*any* chunk, and the planner can stop at the first one. `kind = any(...)` keeps ESPD requests
out of the count — a published DUME is XML, `parse_docs` skips it before parsing, and a bid
whose only document is one has nothing to index and should not be listed as work.
"""

INDEXABLE_KINDS: Final = (DocumentKind.TENDER_DOCUMENT.value, DocumentKind.TENDER_NOTICE.value)
"""What `parse_docs` parses and indexes. The same list the selection above filters on."""


@dataclass(frozen=True, slots=True)
class Unindexed:
    """One bid with documents and no corpus."""

    bid_id: str
    company_id: str
    notice_number: str | None
    """`bids.ted_publication_number`, which is null for a bid not started from a notice."""
    title: str
    created_at: str
    documents: int

    @property
    def label(self) -> str:
        """What to print: the notice number where there is one, the title otherwise."""
        return self.notice_number or self.title


async def unindexed_bids(db: Database, *, bid_id: str | None) -> tuple[Unindexed, ...]:
    """Every bid that has something to index and nothing indexed, oldest first."""
    async with db.connection() as conn:
        cursor = await conn.execute(UNINDEXED_BIDS_SQL, {"kinds": list(INDEXABLE_KINDS)})
        rows = await cursor.fetchall()
    found = tuple(
        Unindexed(
            bid_id=row["bid_id"],
            company_id=row["company_id"],
            notice_number=row["notice_number"],
            title=row["title"],
            created_at=str(row["created_at"]),
            documents=int(row["documents"]),
        )
        for row in rows
    )
    if bid_id is None:
        return found
    return tuple(bid for bid in found if bid.bid_id == bid_id)


async def index_one_bid(db: Database, base: Settings, bid: Unindexed) -> tuple[int, int]:
    """Parse, chunk, scan, embed and write every indexable document of one bid.

    Returns the passages written and the documents that could not be read. A document that
    will not parse is reported and the rest of the bid goes on, which is the same trade
    `parse_docs` makes: half a corpus retrieves, and none does not.
    """
    settings = await settings_for_company(db, base, company_id=bid.company_id)
    ingestion = settings.runtime.ingestion
    rows = await bid_documents(db, company_id=bid.company_id, bid_id=bid.bid_id)
    parser = PyMuPDFParser()
    fetch = storage_fetcher(company_document_store(settings))
    written = 0
    unreadable = 0

    async with EmbeddingsClient(settings) as embedder:
        index = ChunkingTenderIndexer(
            chunker=Chunker(
                chunk_tokens=ingestion.chunk_tokens, overlap_tokens=ingestion.chunk_overlap
            ),
            embedder=embedder,
            writer=ChunkVectorStore(db),
            confirm=(
                ModelInjectionConfirmer(settings)
                if settings.runtime.confirm_flagged_chunks
                else confirm_every_finding
            ),
        )
        for row in rows:
            if row.kind.value not in INDEXABLE_KINDS:
                print(f"    - {row.name}: {row.kind.value}, nothing to index")
                continue
            content = await fetch(bid.company_id, row)
            try:
                parsed = await asyncio.to_thread(parser.parse, content, document_id=row.id)
            except ParserError:
                unreadable += 1
                print(f"    ! {row.name}: will not parse")
                continue
            passages = await index(
                company_id=uuid.UUID(bid.company_id),
                bid_id=uuid.UUID(bid.bid_id),
                parsed=parsed,
            )
            written += passages
            print(f"    + {row.name}: {passages} passage(s)")
    return written, unreadable


async def run(*, apply: bool, bid_id: str | None) -> int:
    settings = load_settings()
    dsn = settings.env.database_url
    if dsn is None:
        print("DATABASE_URL is not set — point it at the database to backfill", file=sys.stderr)
        return INPUT_ERROR

    db = await Database.connect(dsn.get_secret_value())
    try:
        bids = await unindexed_bids(db, bid_id=bid_id)
        if not bids:
            print("Nothing to do: every bid with documents already has a corpus.")
            return 0

        print(f"{len(bids)} bid(s) with documents and no searchable copy of them:\n")
        for bid in bids:
            print(
                f"  {bid.label}  bid {bid.bid_id}  "
                f"{bid.documents} document(s)  analysed {bid.created_at}"
            )
        if not apply:
            print("\nDry run: nothing was fetched, embedded or written. Re-run with --apply.")
            return 0

        print()
        total = 0
        for bid in bids:
            print(f"  {bid.label} ({bid.bid_id}):")
            try:
                written, unreadable = await index_one_bid(db, settings, bid)
            except NoProviderKeyError as exc:
                # Reported, never charged to the application key (ADR-0091).
                print(f"    ! skipped: {exc}")
                continue
            total += written
            if written == 0:
                print("    ! nothing was indexed; this bid still cannot be searched")
            elif unreadable:
                print(f"    {unreadable} document(s) could not be read; the rest is searchable")
        print(f"\n{total} passage(s) written.")
        return 0
    finally:
        await db.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Fetch, parse, embed and write. Without it nothing is read and nothing costs.",
    )
    parser.add_argument("--bid", default=None, help="Only this bid id.")
    args = parser.parse_args(argv)
    try:
        return asyncio.run(run(apply=args.apply, bid_id=args.bid))
    except (SettingsError, DatabaseError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return INPUT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
