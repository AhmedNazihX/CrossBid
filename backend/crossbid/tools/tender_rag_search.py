"""S2.4.2 — semantic search over one bid's tender pack.

The requirement side: the buyer's own documents, as uploaded for this bid. Scoped by
company *and* by bid, and the bid half is not optional. A `ToolContext` with no `bid_id` is
refused at build time rather than quietly dropping the predicate, because a tender search
without one would read every bid the company has ever run and answer a question about this
tender with another tender's text — a wrong answer that looks exactly like a right one.
Refusing at build time also means the failure lands in the run that misconfigured the tool,
not in the ReAct loop three hundred requirements later.

Why the extraction pass does not make this redundant: `extract_reqs` (S3.2.1) reads the pack
once and emits typed requirements with a quote and a page each. `check_reqs` (S3.3.1) then
needs the *surroundings* of a requirement — the threshold table two pages on, the annex that
says which form the proof must be on — which the requirement row does not carry. That is
what this searches for.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from langchain_core.tools import BaseTool
from pydantic import Field

from crossbid.ingestion.embeddings import ChunkMatch, ChunkVectorStore, EmbeddingsClient
from crossbid.tools.manifest import ToolContext, ToolManifest
from crossbid.tools.rag import (
    RagSearchArgs,
    RagToolError,
    build_rag_tool,
    embeddings_client,
    require_connection_source,
    scope_uuid,
)

CORPUS: Final = "this bid's tender pack"

MANIFEST: Final = ToolManifest(
    name="tender_rag_search",
    description=(
        "Search THIS tender's procurement documents — the contract notice, the terms of "
        "reference, the annexes and forms the buyer published — for what the buyer asks "
        "for. Use it to read the exact wording around a requirement: thresholds, deadlines, "
        "which form a proof must be submitted on, what counts as an equivalent. Returns the "
        "best-matching passages with the document name, the page, a verbatim quote and a "
        "similarity score, best first. It never returns the bidding company's own evidence: "
        "to find out what the company can prove, use company_rag_search."
    ),
    external=True,
    default_enabled=True,
)


class TenderSearchArgs(RagSearchArgs):
    """`RagSearchArgs` with the query described in terms of this corpus."""

    query: str = Field(
        min_length=1,
        description=(
            "What the buyer's documents should be searched for, as a phrase or a sentence "
            "— 'minimum annual turnover', 'Eignungsnachweise Referenzen letzte drei Jahre', "
            "'form for the declaration of honour'. This is a semantic search over document "
            "text, not a keyword filter; search in the tender's own language when you know "
            "it."
        ),
    )


ARGS_SCHEMA: Final = TenderSearchArgs
"""Named so the registry (S1.4.1) can read a module's schema without knowing its class."""


def build_tool(context: ToolContext, *, embedder: EmbeddingsClient | None = None) -> BaseTool:
    """Bind the tool to one company and one bid, or refuse to build it at all."""
    if context.bid_id is None:
        raise RagToolError(
            f"'{MANIFEST.name}' was built with no bid_id. A tender search without one "
            "would read every bid's pack in the company, so it is refused rather than "
            "widened."
        )
    store = ChunkVectorStore(require_connection_source(context, tool=MANIFEST.name))
    company_id = scope_uuid(context.company_id, field="company_id", tool=MANIFEST.name)
    bid_id = scope_uuid(context.bid_id, field="bid_id", tool=MANIFEST.name)

    async def search(embedding: Sequence[float], limit: int) -> tuple[ChunkMatch, ...]:
        return await store.search_tender_chunks(
            company_id=company_id, bid_id=bid_id, embedding=embedding, limit=limit
        )

    return build_rag_tool(
        manifest=MANIFEST,
        args_schema=ARGS_SCHEMA,
        corpus=CORPUS,
        search=search,
        embedder=embeddings_client(context, embedder),
    )
