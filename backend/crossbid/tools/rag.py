"""S2.4.2 — what the two retrieval tools share: a hit, a result, and the factory.

`company_rag_search` and `tender_rag_search` differ in one line each — which store method
they call and which corpus they describe to the model — so everything else lives here. The
alternative, one parameterised `rag_search(corpus=...)` tool, was rejected: the corpus would
then be an *argument the model chooses*, and a model that picks the wrong one reads the
tender pack as if it were the bidder's evidence. Two tools with two descriptions make that
choice at build time, where it is ours.

Five decisions a reader should not have to reconstruct.

**1. The result is a typed object and a rendering, not prose.** `build_rag_tool` returns a
`content_and_artifact` tool: the model reads `RagSearchResult.render()` and the
`RagSearchResult` itself rides along on the `ToolMessage.artifact`, so S3.3.1 builds an
`Evidence` from the retrieved row rather than from the model's retelling of it. The artifact
only materialises when the tool is invoked with a tool call, which is how `ToolNode` invokes
it; a bare `ainvoke` still returns the rendered text.

**2. A retrieved passage is untrusted document text, and it is wrapped.** This is the same
exposure `extract_reqs` has — text from a PDF arriving in the model's context — so it gets
the same defence: every hit goes inside one `wrap_as_data` block with a one-time tag, and
the `DOCUMENT` header the wrapper writes is the only authority for the name and page a
citation may use (S2.3.2, ADR-0009). A tool that pasted the chunk in plain would make the
retrieval path the one hole in that rule.

**3. The store returns a cosine *distance*; the model is given a *similarity*.** They are
not renamed into each other: `ChunkMatch.distance` keeps its name and its direction, and
`similarity_from_distance` is the single place where `1 - distance` happens. "Higher is
better" is what a model reasons about correctly without being told a convention.

**4. The quote is cut to `Evidence`'s limit here, not at citation time.** A chunk is ~800
tokens and `Evidence.quote` caps at 2 000 characters, so a long chunk would produce a hit
that cannot become a citation. It is truncated to a prefix — still a verbatim substring of
the page, which is what makes a citation checkable — and `truncated` says so, to the model
in the rendering and to S3.3.1 on the object. No ellipsis is appended: a marker inside the
quote would make the quote no longer verbatim.

**5. The scope is resolved at build time and closed over.** `company_id` (and `bid_id`) are
parsed into UUIDs before the tool exists, so a malformed scope fails where a developer sees
it rather than inside a ReAct loop, and the model never gets an argument that could widen
the search. `limit` is the only knob it holds, and it is bounded by the schema.

The `EmbeddingsClient` is injectable and the tool does not own it: S3.3.1 builds one per run
and hands the same client to every tool, so one HTTP pool is opened and closed per bid. The
default — building one — exists so the registry can construct a tool from a context alone;
a client built that way is closed by garbage collection, which is acceptable for a one-off
call and not for a run.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING, Final

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, ConfigDict, Field, field_validator

from crossbid.guards.wrap import DataBlock, wrap_as_data
from crossbid.ingestion.embeddings import (
    DEFAULT_SEARCH_LIMIT,
    MIN_SEARCH_LIMIT,
    ChunkMatch,
    EmbeddingsClient,
)
from crossbid.models.matrix import MAX_QUOTE_CHARS, Evidence
from crossbid.tools.manifest import ToolContext, ToolManifest

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters to the type checker
    from crossbid.db import ConnectionSource

MAX_RESULTS: Final = 10
"""The most passages one call may return. The budget is what sets it: F3.3 allows four tool
calls per requirement over a few hundred requirements, and ten ~800-token chunks is already
most of a context window's worth of quoted German. Five (the store's default) is what the
model gets when it does not ask."""

SCORE_DECIMALS: Final = 3
"""Three decimals distinguish 0.812 from 0.804 and stop there: the fourth digit of a cosine
similarity is noise the model would otherwise be invited to reason about."""


class RagToolError(RuntimeError):
    """A retrieval tool could not be built or run. Never carries a key, a DSN or a row."""


class RagSearchArgs(BaseModel):
    """What the model may choose. Two fields, both bounded — nothing that widens the scope.

    Subclassed by each tool so the `query` description can name its corpus; the shape is
    shared because "what to look for, and how many passages" is the same question twice.
    """

    model_config = ConfigDict(extra="forbid")

    query: str = Field(
        min_length=1,
        description=(
            "What to look for, as a phrase or a sentence. This is a semantic search over "
            "document text, not a keyword filter, so describe the evidence you need rather "
            "than guessing a single word, and search in the language the documents are "
            "written in when you know it."
        ),
    )
    limit: int = Field(
        default=DEFAULT_SEARCH_LIMIT,
        ge=MIN_SEARCH_LIMIT,
        le=MAX_RESULTS,
        description="How many passages to return, best first.",
    )

    @field_validator("query")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        """Whitespace is not a query: the provider answers 400 and the run loses a call."""
        if not value.strip():
            raise ValueError("query must not be blank")
        return value


def similarity_from_distance(distance: float) -> float:
    """Cosine distance (`<=>`, 0 identical, 2 opposite) as cosine similarity.

    The one place the conversion happens, and it is exactly `1 - distance` — not a rescaled
    or clamped "relevance", which would be a number no one can check against the index.
    """
    return 1.0 - distance


class RagHit(BaseModel):
    """One retrieved passage, in the shape a citation needs.

    Frozen, and every field is what the row said: nothing here is the model's paraphrase,
    which is the whole point of handing S3.3.1 the object instead of the rendering.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: str
    document_name: str
    page: int = Field(ge=1, description="Where the passage starts — where a reviewer is sent")
    pages: tuple[int, ...] = Field(default=(), description="Every page the passage spans")
    quote: str = Field(max_length=MAX_QUOTE_CHARS)
    truncated: bool = Field(
        default=False, description="True when the chunk was longer than a citation may be"
    )
    score: float = Field(description="Cosine similarity; higher is better, 1.0 is identical")

    @classmethod
    def from_match(cls, match: ChunkMatch) -> RagHit:
        quote = match.text[:MAX_QUOTE_CHARS]
        return cls(
            document_id=str(match.document_id),
            document_name=match.document_name,
            page=match.page,
            pages=match.pages,
            quote=quote,
            truncated=len(quote) < len(match.text),
            score=similarity_from_distance(match.distance),
        )

    def as_evidence(self) -> Evidence:
        """The matrix row's citation, with no re-derivation. Total by construction: the
        quote was cut to `Evidence`'s limit when the hit was built."""
        return Evidence(
            document_id=self.document_id,
            document_name=self.document_name,
            page=self.page,
            quote=self.quote,
        )

    def as_block(self) -> DataBlock:
        """The passage as untrusted data, labelled with the name a citation will carry."""
        return DataBlock(
            text=self.quote, label=self.document_name, pages=self.pages or (self.page,)
        )


NO_RESULTS: Final = (
    "No passages in {corpus} matched this search. That is an answer about the documents, "
    "not an error: say the requirement cannot be evidenced from them rather than assuming "
    "the evidence exists elsewhere."
)

EMPTY_CORPUS: Final = (
    "No search of {corpus} can return anything: nothing has been indexed for it, so it holds "
    "no passages at all. This is not an answer about what the documents say — say that they "
    "are not available to search, and do not conclude anything about their content."
)
"""Said when the corpus is empty rather than when the search missed, because the two have
different causes and opposite meanings to a bidder.

A bid run before `a55d14b` (2026-09-15) has no `tender_chunks` rows: `parse_docs` parsed and
extracted from its documents but nothing wrote the retrieval corpus. Every search of such a
bid returned `NO_RESULTS`, which reads as "your tender does not mention this" — so a full
matrix sat beside a chat that said the documents were silent on everything. The sentence a
bidder needed was that there was nothing to search."""

RESULTS_HEADER: Final = (
    "{count} {noun} from {corpus}, best first. `score` is cosine similarity, where 1.0 is "
    "identical and 0.0 unrelated:\n{lines}\n"
    "The passages follow in that order inside one data block. The DOCUMENT header above a "
    "passage is the only authority for the file name and page you cite it by."
)

RESULT_LINE: Final = "  [{index}] score {score}{truncated}"
TRUNCATED_SUFFIX: Final = (
    "  (passage truncated at the citation limit; it continues in the document)"
)


class RagSearchResult(BaseModel):
    """What one search found, and how the model is shown it.

    A plain model with no database behind it, so S3.3.1 (and a test) can build one by hand.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    query: str
    corpus: str = Field(description="The corpus in the words the model was told about it")
    hits: tuple[RagHit, ...] = ()
    corpus_empty: bool = Field(
        default=False,
        description="The scope holds no indexed passage at all, rather than none that matched",
    )

    @classmethod
    def from_matches(
        cls,
        *,
        query: str,
        corpus: str,
        matches: Sequence[ChunkMatch],
        corpus_empty: bool = False,
    ) -> RagSearchResult:
        """Store order is kept: it is the `order by`, and re-sorting could only lose it."""
        return cls(
            query=query,
            corpus=corpus,
            hits=tuple(RagHit.from_match(m) for m in matches),
            corpus_empty=corpus_empty,
        )

    def render(self) -> str:
        """The tool message the model reads: scores outside the block, passages inside it."""
        if not self.hits:
            unfound = EMPTY_CORPUS if self.corpus_empty else NO_RESULTS
            return unfound.format(corpus=self.corpus)
        lines = "\n".join(
            RESULT_LINE.format(
                index=index,
                score=f"{hit.score:.{SCORE_DECIMALS}f}",
                truncated=TRUNCATED_SUFFIX if hit.truncated else "",
            )
            for index, hit in enumerate(self.hits, start=1)
        )
        header = RESULTS_HEADER.format(
            count=len(self.hits),
            noun="passage" if len(self.hits) == 1 else "passages",
            corpus=self.corpus,
            lines=lines,
        )
        return f"{header}\n{wrap_as_data([hit.as_block() for hit in self.hits]).text}"


ChunkSearch = Callable[[Sequence[float], int], Awaitable[tuple[ChunkMatch, ...]]]
CorpusProbe = Callable[[], Awaitable[bool]]
"""Asked only when a search found nothing: does this scope hold any indexed passage at all?"""
"""One already-scoped search. The tenant ids are closed over before this is built, so the
only things left to pass are the query vector and how many rows to take."""


def build_rag_tool(
    *,
    manifest: ToolManifest,
    args_schema: type[RagSearchArgs],
    corpus: str,
    search: ChunkSearch,
    embedder: EmbeddingsClient,
    corpus_is_empty: CorpusProbe,
) -> BaseTool:
    """Embed the query, search within the scope already bound, return text and object.

    Nothing here catches: an `EmbeddingsError` or a `ChunkStoreError` reaches the graph,
    where `ToolNode` turns it into a tool message the model can react to. Swallowing it
    would tell the model "nothing found", which is a different and much worse answer.
    """

    async def run(query: str, limit: int = DEFAULT_SEARCH_LIMIT) -> tuple[str, RagSearchResult]:
        embedding = await embedder.embed_query(query)
        matches = await search(embedding, limit)
        # Only when the search found nothing: a hit is already proof the corpus has content,
        # and the probe is a second round trip that every successful search would pay for.
        empty = await corpus_is_empty() if not matches else False
        result = RagSearchResult.from_matches(
            query=query, corpus=corpus, matches=matches, corpus_empty=empty
        )
        return result.render(), result

    return StructuredTool.from_function(
        coroutine=run,
        name=manifest.name,
        description=manifest.description,
        args_schema=args_schema,
        response_format="content_and_artifact",
    )


def require_connection_source(context: ToolContext, *, tool: str) -> ConnectionSource:
    """The database, or a loud failure at build time.

    The source must be one whose connections have had `register_vector_async` run on them —
    `crossbid.db.Database` does, in its pool's configure hook — because the search binds a
    `vector` parameter. Nothing in the type says so, so it is said here.
    """
    if context.db is None:
        raise RagToolError(
            f"'{tool}' searches the database and was built with no connection source. "
            "A retrieval tool without one could only ever answer 'nothing found'."
        )
    return context.db


def scope_uuid(value: str, *, field: str, tool: str) -> uuid.UUID:
    """A scope string as a UUID, refused early rather than bound to a query.

    The value reaches us as text from the auth layer, and psycopg would send a malformed one
    as a string against a `uuid` column — a run-time error inside the agent loop, hundreds of
    requirements in, instead of at the call that built the tool.
    """
    try:
        return uuid.UUID(value)
    except ValueError as err:
        raise RagToolError(
            f"'{tool}' was built with a {field} that is not a UUID. The scope of a search "
            "is not something to guess at."
        ) from err


def embeddings_client(
    context: ToolContext, embedder: EmbeddingsClient | None
) -> EmbeddingsClient:
    """The caller's client, then the run's, then a fresh one. See the module docstring."""
    if embedder is not None:
        return embedder
    if context.embedder is not None:
        return context.embedder
    return EmbeddingsClient(context.settings)
