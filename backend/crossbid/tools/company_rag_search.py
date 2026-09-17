"""S2.4.2 — semantic search over the bidder's own documents.

The evidence side of the compliance matrix: certificates, balance sheets, insurance
policies, references, CVs — whatever the company uploaded as `company_evidence`. Scoped by
company and by nothing else, because a bidder's own corpus is not a property of the bid it
is being read for; the same ISO certificate answers every tender the company runs.

The description below is written for the model, not for us. Its load-bearing sentence is the
last one: the two RAG tools are near-twins, and a model that searches the tender pack for the
company's insurance cover finds the *requirement* and reports it as evidence. Naming the
sibling is what makes the choice legible from either side.
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
    build_rag_tool,
    embeddings_client,
    require_connection_source,
    scope_uuid,
)

CORPUS: Final = "the company's own documents"

MANIFEST: Final = ToolManifest(
    name="company_rag_search",
    description=(
        "Search the bidding company's OWN documents — certificates, insurance policies, "
        "balance sheets, references, CVs, quality and security accreditations — for "
        "evidence about the company itself. Use it to find out whether the company can "
        "prove something a tender asks for. Returns the best-matching passages with the "
        "document name, the page, a verbatim quote and a similarity score, best first. "
        "It never returns tender text: to read what the buyer requires, use "
        "tender_rag_search."
    ),
    external=True,
    default_enabled=True,
)


class CompanySearchArgs(RagSearchArgs):
    """`RagSearchArgs` with the query described in terms of this corpus."""

    query: str = Field(
        min_length=1,
        description=(
            "The evidence you are looking for in the company's documents, as a phrase or "
            "a sentence — 'professional indemnity insurance cover', 'Nachweis "
            "Berufshaftpflichtversicherung', 'ISO 27001 certificate scope'. This is a "
            "semantic search over document text, not a keyword filter."
        ),
    )


ARGS_SCHEMA: Final = CompanySearchArgs
"""Named so the registry (S1.4.1) can read a module's schema without knowing its class."""


def build_tool(context: ToolContext, *, embedder: EmbeddingsClient | None = None) -> BaseTool:
    """Bind the tool to one company. The scope is resolved now, not per call."""
    store = ChunkVectorStore(require_connection_source(context, tool=MANIFEST.name))
    company_id = scope_uuid(context.company_id, field="company_id", tool=MANIFEST.name)

    async def search(embedding: Sequence[float], limit: int) -> tuple[ChunkMatch, ...]:
        return await store.search_company_chunks(
            company_id=company_id, embedding=embedding, limit=limit
        )

    async def corpus_is_empty() -> bool:
        return await store.company_corpus_is_empty(company_id=company_id)

    return build_rag_tool(
        manifest=MANIFEST,
        args_schema=ARGS_SCHEMA,
        corpus=CORPUS,
        search=search,
        corpus_is_empty=corpus_is_empty,
        embedder=embeddings_client(context, embedder),
    )
