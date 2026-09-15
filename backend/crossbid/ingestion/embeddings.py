"""S2.2.1 — text becomes vectors, and vectors become a tenant-scoped nearest neighbour.

Two halves that are useless apart, so one module.

**`EmbeddingsClient`** posts to OpenRouter's `/embeddings`. The slug comes from
`settings.default.yaml` (`models.embed`), never from a literal here. OpenRouter has no
`/models` listing for embeddings, so the usable set could only be found by probing: exactly
three answer on this account, and `openai/text-embedding-3-small` is the configured default
*because* its 1536 dimensions fit under pgvector's 2000-dimension index cap — which is what
makes the HNSW indexes in `migrations/0001_init.sql` possible at all (ADR-0004).

That is also why every returned vector is measured against
`runtime.ingestion.embed_dimensions` before it is handed back. The two alternatives
(`text-embedding-3-large` at 3072, `qwen/qwen3-embedding-8b` at 4096) would be accepted by
OpenRouter and rejected by the `vector(1536)` column — a loud failure. The quiet one is
worse: a corpus half-embedded by one model and half by another still compares without error
and ranks nonsense first. One integer comparison per row buys that away.

**`ChunkVectorStore`** writes and searches `company_chunks` and `tender_chunks`, joining
`documents` on the way out so that every match carries the file name a citation needs. Every
statement is a module constant with the tenant predicate already in its text, so no code
path can build an unscoped query — `company_id = %(company_id)s` is not an argument a
caller may leave out, and `SEARCH_STATEMENTS` exists so a test can assert that across all
of them. That matters more here than it looks: the API connects as Supabase's `postgres`
role, which has `BYPASSRLS = true`, so row-level security policies would be silently inert.
Application-level filtering is the *only* line of defence and one missing `WHERE` clause is
a cross-tenant leak (ADR-0009).

The store depends on the `ConnectionSource` protocol rather than on `crossbid.db`, so it
can be exercised with a recording connection and never has to reach a real Postgres to be
tested.
"""

from __future__ import annotations

import asyncio
import json
import math
import uuid
from collections.abc import Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from itertools import batched
from types import MappingProxyType, TracebackType
from typing import Any, Final, LiteralString, Protocol

import httpx
from pgvector import Vector
from psycopg import AsyncConnection
from psycopg.rows import DictRow
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from crossbid.ingestion.chunker import Chunk
from crossbid.llm import OPENROUTER_BASE_URL
from crossbid.settings import ModelRole, Settings

OPENROUTER_EMBEDDINGS_PATH: Final = "embeddings"
"""Relative to `OPENROUTER_BASE_URL`, which `crossbid.llm` already owns (one base URL)."""

REQUEST_TIMEOUT_S: Final = 60.0
MAX_ATTEMPTS: Final = 3
RETRY_BACKOFF_S: Final = 2.0
"""Sleeps 2s then 4s before giving up, the same shape as `EcertisRestClient`."""

RETRYABLE_STATUS_CODES: Final = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
"""Only these are retried. A 400/401/404 will not become a 200 on the third try, and 404 is
precisely how this account's data policy refuses an unusable slug (ADR-0005) — retrying it
turns a clear configuration error into a slow one."""

DEFAULT_BATCH_SIZE: Final = 64
"""Texts per request. `text-embedding-3-small` accepts 8191 tokens *per input* and the
chunker emits ~800, so 64 chunks is roughly 50k tokens in one body: large enough that a
191-page pack is a handful of requests, small enough that one retry re-sends little."""

DEFAULT_SEARCH_LIMIT: Final = 5
MIN_SEARCH_LIMIT: Final = 1
MIN_BATCH_SIZE: Final = 1
MIN_ATTEMPTS: Final = 1


class EmbeddingsError(RuntimeError):
    """OpenRouter did not return usable vectors. Never carries the API key."""


class ChunkStoreError(RuntimeError):
    """A vector or a row was not usable. Raised before anything reaches Postgres."""


# ------------------------------------------------------------------------ wire schema


class _WireEmbedding(BaseModel):
    """One row of an OpenAI-shaped `data` array. Extra keys (`object`) are ignored."""

    index: int = Field(ge=0)
    embedding: tuple[float, ...] = Field(min_length=1)


class _WireEmbeddingsResponse(BaseModel):
    data: tuple[_WireEmbedding, ...]


# ------------------------------------------------------------------ embeddings client


class EmbeddingsClient:
    """OpenRouter `/embeddings`, batched, retried, and dimension-checked.

    Async because both callers are: the ingestion route embeds an uploaded pack, and the
    RAG tools embed a query inside the graph. Constructing it opens no connection.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.AsyncClient | None = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_attempts: int = MAX_ATTEMPTS,
    ) -> None:
        if batch_size < MIN_BATCH_SIZE:
            raise ValueError(f"batch_size must be at least {MIN_BATCH_SIZE}, got {batch_size}")
        if max_attempts < MIN_ATTEMPTS:
            raise ValueError(
                f"max_attempts must be at least {MIN_ATTEMPTS}, got {max_attempts}"
            )

        self._model = settings.runtime.models.for_role(ModelRole.EMBED)
        self._dimensions = settings.runtime.ingestion.embed_dimensions
        self._batch_size = batch_size
        self._max_attempts = max_attempts
        # Per-request rather than baked into the client, so that an injected client --
        # every test uses one -- exercises the same authenticated request as production
        # instead of quietly sending an unauthenticated one.
        self._headers: Mapping[str, str] = MappingProxyType(
            {
                "Authorization": f"Bearer {settings.env.openrouter_api_key.get_secret_value()}",
                "Accept": "application/json",
            }
        )
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=OPENROUTER_BASE_URL, timeout=REQUEST_TIMEOUT_S
        )

    @property
    def model(self) -> str:
        """The configured slug, so a caller can log or display it without re-reading YAML."""
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def http(self) -> httpx.AsyncClient:
        """Exposed for lifecycle assertions; nothing outside should send with it."""
        return self._client

    async def __aenter__(self) -> EmbeddingsClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Closes only a client this object built. An injected one belongs to its owner."""
        if self._owns_client:
            await self._client.aclose()

    async def embed_query(self, text: str) -> tuple[float, ...]:
        """One search string as one vector — the retrieval side of S2.2.1."""
        return (await self.embed_texts([text]))[0]

    async def embed_texts(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        """One vector per text, **in the order the texts were given**.

        Order is the correctness property here, not a nicety: the caller zips the result
        back onto its chunks, so a shuffled result files a German certificate's vector
        under a French requirement's text and nothing ever raises. The provider labels
        each row with an `index`, and that label — not arrival order — is what is trusted.
        """
        if not texts:
            return ()
        self._reject_blank(texts)

        vectors: list[tuple[float, ...]] = []
        for batch in batched(texts, self._batch_size):
            vectors.extend(await self._embed_batch(batch))
        return tuple(vectors)

    @staticmethod
    def _reject_blank(texts: Sequence[str]) -> None:
        """OpenRouter answers 400 for an empty input; naming the row is more useful."""
        blank = [position for position, text in enumerate(texts) if not text.strip()]
        if blank:
            raise EmbeddingsError(
                f"Cannot embed blank text: input rows {blank} are empty or whitespace. "
                "A chunk with no text should not have been produced."
            )

    async def _embed_batch(self, batch: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        payload = await self._post({"model": self._model, "input": list(batch)})
        return self._vectors(payload, expected=len(batch))

    def _vectors(
        self, payload: Mapping[str, Any], *, expected: int
    ) -> tuple[tuple[float, ...], ...]:
        """Validate the batch as the untrusted external input it is, then order it."""
        try:
            parsed = _WireEmbeddingsResponse.model_validate(payload)
        except ValidationError as err:
            raise EmbeddingsError(
                f"The /embeddings response for '{self._model}' has an unexpected shape: {err}"
            ) from err

        if len(parsed.data) != expected:
            raise EmbeddingsError(
                f"Asked '{self._model}' for {expected} inputs and got "
                f"{len(parsed.data)} vectors back. Refusing to guess which is which."
            )

        rows = sorted(parsed.data, key=lambda row: row.index)
        if [row.index for row in rows] != list(range(expected)):
            raise EmbeddingsError(
                f"'{self._model}' returned indices {[row.index for row in rows]} for "
                f"{expected} inputs, not 0..{expected - 1}. Pairing text to vector is "
                "impossible, and a wrong pairing never raises later."
            )

        for row in rows:
            if len(row.embedding) != self._dimensions:
                raise EmbeddingsError(
                    f"'{self._model}' returned a vector of {len(row.embedding)} "
                    f"dimensions; the corpus and the pgvector column are "
                    f"{self._dimensions} dimensions (ADR-0004). Mixing two embedding "
                    "spaces ranks nonsense first without ever failing. Re-embed the whole "
                    "corpus and migrate the column before changing the slug."
                )
        return tuple(row.embedding for row in rows)

    async def _post(self, body: Mapping[str, Any]) -> Mapping[str, Any]:
        """POST with backoff. Transient failures are retried; permanent ones are not."""
        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = await self._client.post(
                    OPENROUTER_EMBEDDINGS_PATH, json=dict(body), headers=dict(self._headers)
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as err:
                if err.response.status_code not in RETRYABLE_STATUS_CODES:
                    raise EmbeddingsError(
                        f"POST /{OPENROUTER_EMBEDDINGS_PATH} for '{self._model}' returned "
                        f"HTTP {err.response.status_code}, which will not change on a "
                        "retry. A slug listed in OpenRouter's catalogue can still be "
                        "refused by this account's data policy (ADR-0005)."
                    ) from err
                last_error = err
            except httpx.HTTPError as err:
                last_error = err
            else:
                return self._decode(response)
            if attempt < self._max_attempts:
                await self._sleep(RETRY_BACKOFF_S * attempt)

        raise EmbeddingsError(
            f"POST /{OPENROUTER_EMBEDDINGS_PATH} for '{self._model}' failed after "
            f"{self._max_attempts} attempts: {last_error}"
        ) from last_error

    def _decode(self, response: httpx.Response) -> Mapping[str, Any]:
        try:
            payload = json.loads(response.content)
        except ValueError as err:
            raise EmbeddingsError(
                f"POST /{OPENROUTER_EMBEDDINGS_PATH} returned malformed JSON: {err}"
            ) from err
        if not isinstance(payload, dict):
            raise EmbeddingsError(
                f"POST /{OPENROUTER_EMBEDDINGS_PATH} returned "
                f"{type(payload).__name__}, not an object"
            )
        return payload

    @staticmethod
    async def _sleep(seconds: float) -> None:
        """The only wall-clock wait in the module, isolated so tests can patch it away."""
        await asyncio.sleep(seconds)


# --------------------------------------------------------------- chunk + vector pairing


class EmbeddedChunk(BaseModel):
    """A chunk and the vector that stands for it. Frozen: neither half may drift."""

    model_config = ConfigDict(frozen=True)

    chunk: Chunk
    embedding: tuple[float, ...]


async def embed_chunks(
    client: EmbeddingsClient, chunks: Sequence[Chunk]
) -> tuple[EmbeddedChunk, ...]:
    """The bridge from `chunker` to the store: chunks in, chunk-vector pairs out.

    `strict=True` is the assertion, not a decoration — if the client ever returned a
    different number of vectors than there were chunks, silently pairing the shorter of
    the two is the bug this whole module is arranged to prevent.
    """
    if not chunks:
        return ()
    vectors = await client.embed_texts([chunk.text for chunk in chunks])
    return tuple(
        EmbeddedChunk(chunk=chunk, embedding=vector)
        for chunk, vector in zip(chunks, vectors, strict=True)
    )


# ------------------------------------------------------------------- the vector store


class ConnectionSource(Protocol):
    """Something that lends a pooled connection. `crossbid.db.Database` satisfies it.

    Part of the contract is not in the signature and belongs written down: the connection
    must already know the `vector` type, which `crossbid.db`'s pool does by calling
    `pgvector.psycopg.register_vector_async` once per connection in its configure hook.
    Registration reads `pg_type`, so it needs a live connection and cannot be done here
    per query without four catalogue round trips on every search.
    """

    def connection(self) -> AbstractAsyncContextManager[AsyncConnection[DictRow]]: ...


class ChunkMatch(BaseModel):
    """One retrieved chunk, the document it belongs to, and how far it sat from the query.

    `document_name` comes from the join rather than from a second query per hit: a citation
    a reviewer can act on names a file, not a UUID (`models.matrix.Evidence` requires it),
    and five hits would otherwise be five extra round trips inside a per-requirement ReAct
    loop that runs once per requirement (S2.4.2, S3.3.1).
    """

    model_config = ConfigDict(frozen=True)

    id: int
    document_id: uuid.UUID
    document_name: str
    page: int = Field(ge=1)
    pages: tuple[int, ...]
    text: str
    token_count: int | None
    distance: float
    """Cosine distance: 0 is identical, 1 is orthogonal. Lower ranks first."""


TENANT_PREDICATE: Final = "company_id = %(company_id)s"
"""The one clause that stands between two tenants. Named so a test can assert it appears
in every search statement, and so a reader grepping for it finds all of them at once.

The `where` keyword is deliberately not part of it. Both search statements join `documents`
for the chunk's file name, and `documents` has a `company_id`, an `id`, a `name` and a
`pages` of its own -- so every column is table-qualified and the predicate reads
`company_chunks.company_id = %(company_id)s`. The qualified form still contains this one,
which is what keeps the assertion honest across the join.

It is written out again in each statement below rather than interpolated: a query built by
string composition is a query that can be built wrongly, and the test asserts the two agree.
Each statement is typed `LiteralString` for the same reason -- psycopg's `execute` accepts
nothing else, so a scope assembled at run time would not type-check.
"""

COMPANY_SEARCH_SQL: Final[LiteralString] = """
select company_chunks.id,
       company_chunks.document_id,
       documents.name as document_name,
       company_chunks.page,
       company_chunks.pages,
       company_chunks.text,
       company_chunks.token_count,
       company_chunks.embedding <=> %(embedding)s as distance
from company_chunks
join documents
  on documents.id = company_chunks.document_id
 and documents.company_id = company_chunks.company_id
where company_chunks.company_id = %(company_id)s
  and company_chunks.embedding is not null
order by company_chunks.embedding <=> %(embedding)s
limit %(limit)s
"""

TENDER_SEARCH_SQL: Final[LiteralString] = """
select tender_chunks.id,
       tender_chunks.document_id,
       documents.name as document_name,
       tender_chunks.page,
       tender_chunks.pages,
       tender_chunks.text,
       tender_chunks.token_count,
       tender_chunks.embedding <=> %(embedding)s as distance
from tender_chunks
join documents
  on documents.id = tender_chunks.document_id
 and documents.company_id = tender_chunks.company_id
where tender_chunks.company_id = %(company_id)s
  and tender_chunks.bid_id = %(bid_id)s
  and tender_chunks.embedding is not null
order by tender_chunks.embedding <=> %(embedding)s
limit %(limit)s
"""

SEARCH_STATEMENTS: Final[tuple[LiteralString, ...]] = (COMPANY_SEARCH_SQL, TENDER_SEARCH_SQL)
"""Every statement that reads chunks. `test_embeddings.py` asserts each one is scoped."""

COMPANY_INSERT_SQL: Final[LiteralString] = """
insert into company_chunks
    (company_id, document_id, page, pages, text, token_count, embedding)
values
    (%(company_id)s, %(document_id)s, %(page)s, %(pages)s, %(text)s, %(token_count)s,
     %(embedding)s)
"""

TENDER_INSERT_SQL: Final[LiteralString] = """
insert into tender_chunks
    (company_id, bid_id, document_id, page, pages, text, token_count, embedding)
values
    (%(company_id)s, %(bid_id)s, %(document_id)s, %(page)s, %(pages)s, %(text)s,
     %(token_count)s, %(embedding)s)
"""


DELETE_TENDER_CHUNKS_SQL: Final[LiteralString] = """
delete from tender_chunks
where company_id = %(company_id)s and bid_id = %(bid_id)s and document_id = %(document_id)s
"""
"""What makes indexing a tender document safe to run twice.

`parse_docs` is a graph node, and a process that dies before it finishes runs it again from
the start on resume (`resume_unfinished_runs`) -- so an insert with no delete in front of it
would give the second attempt a doubled corpus, where every retrieval returns each passage
twice and a reviewer reads the same clause as two pieces of evidence. Scoped by all three
ids, so re-indexing one document of a pack never touches its siblings.
"""


def _vector_param(embedding: Sequence[float]) -> Vector:
    """The bound parameter for a `vector` column or a `<=>` comparison.

    A `pgvector.Vector`, never a `list`: pgvector 0.5.0 registers its dumper for `Vector`
    and `numpy.ndarray` only, so a plain list would be adapted as a Postgres *array* and
    rejected. Narrowing to `float4` happens here rather than in Postgres, which is what
    the column stores anyway.
    """
    if not embedding:
        raise ChunkStoreError(
            "An embedding must have at least one dimension; got none. The vector column "
            "would reject it, but the caller has probably lost a batch."
        )
    if any(not math.isfinite(value) for value in embedding):
        raise ChunkStoreError(
            "An embedding contains NaN or infinity. Postgres stores it happily and cosine "
            "distance against it is meaningless, so the row would rank arbitrarily forever."
        )
    return Vector(list(embedding))


class ChunkVectorStore:
    """Reads and writes `company_chunks` / `tender_chunks`, always inside one tenant.

    There is no general `search(table, where=...)`: each table has its own method and its
    own module-constant statement with the scope already in the text, so "forgot the
    `WHERE`" is not a mistake this class can make. The scope arguments are keyword-only
    and have no defaults, so omitting one does not type-check and does not run.

    The join to `documents` carries `company_id` in its own `on` clause as well. It is
    redundant while the foreign keys hold -- a chunk cannot outlive its document, which
    cascades -- and it costs nothing, so a mislinked row surfaces as a missing match rather
    than as another tenant's file name in a citation.
    """

    def __init__(self, source: ConnectionSource) -> None:
        self._source = source

    async def search_company_chunks(
        self,
        *,
        company_id: uuid.UUID,
        embedding: Sequence[float],
        limit: int = DEFAULT_SEARCH_LIMIT,
    ) -> tuple[ChunkMatch, ...]:
        """The company's own evidence corpus, nearest first (S2.2.1's `company_rag_search`)."""
        return await self._search(
            COMPANY_SEARCH_SQL, {"company_id": company_id}, embedding=embedding, limit=limit
        )

    async def search_tender_chunks(
        self,
        *,
        company_id: uuid.UUID,
        bid_id: uuid.UUID,
        embedding: Sequence[float],
        limit: int = DEFAULT_SEARCH_LIMIT,
    ) -> tuple[ChunkMatch, ...]:
        """One tender's own text. Scoped by bid *and* company: a bid id is not a capability."""
        return await self._search(
            TENDER_SEARCH_SQL,
            {"company_id": company_id, "bid_id": bid_id},
            embedding=embedding,
            limit=limit,
        )

    async def insert_company_chunks(
        self,
        *,
        company_id: uuid.UUID,
        document_id: uuid.UUID,
        chunks: Sequence[EmbeddedChunk],
    ) -> int:
        """Store an evidence document's chunks. Returns how many rows were written."""
        rows = [
            self._row(embedded, company_id=company_id, document_id=document_id)
            for embedded in chunks
        ]
        return await self._insert(COMPANY_INSERT_SQL, rows)

    async def insert_tender_chunks(
        self,
        *,
        company_id: uuid.UUID,
        bid_id: uuid.UUID,
        document_id: uuid.UUID,
        chunks: Sequence[EmbeddedChunk],
    ) -> int:
        """Store a tender document's chunks. Returns how many rows were written."""
        rows = [
            self._row(embedded, company_id=company_id, document_id=document_id)
            | {"bid_id": bid_id}
            for embedded in chunks
        ]
        return await self._insert(TENDER_INSERT_SQL, rows)

    async def replace_tender_chunks(
        self,
        *,
        company_id: uuid.UUID,
        bid_id: uuid.UUID,
        document_id: uuid.UUID,
        chunks: Sequence[EmbeddedChunk],
    ) -> int:
        """Delete this document's chunks for this bid, then write these. Returns how many.

        One connection and one transaction, so a crash between the two cannot leave the bid
        with a document that has no passages at all -- which would read downstream as "this
        tender says nothing about that", the most expensive wrong answer this system can
        give. See `DELETE_TENDER_CHUNKS_SQL` for why the delete is there in the first place.
        """
        scope = {"company_id": company_id, "bid_id": bid_id, "document_id": document_id}
        rows = [
            self._row(embedded, company_id=company_id, document_id=document_id)
            | {"bid_id": bid_id}
            for embedded in chunks
        ]
        async with self._source.connection() as connection, connection.cursor() as cursor:
            await cursor.execute(DELETE_TENDER_CHUNKS_SQL, scope)
            if not rows:
                return 0
            await cursor.executemany(TENDER_INSERT_SQL, rows)
            return len(rows)

    @staticmethod
    def _row(
        embedded: EmbeddedChunk, *, company_id: uuid.UUID, document_id: uuid.UUID
    ) -> dict[str, Any]:
        """One `EmbeddedChunk` as bound parameters. Builds a new dict; mutates nothing.

        `pages` is a **list**, not the chunk's tuple: psycopg adapts a list to `integer[]`
        and a tuple to a composite *record*, so a tuple here fails against the column.
        """
        return {
            "company_id": company_id,
            "document_id": document_id,
            "page": embedded.chunk.page,
            "pages": list(embedded.chunk.pages),
            "text": embedded.chunk.text,
            "token_count": embedded.chunk.token_count,
            "embedding": _vector_param(embedded.embedding),
        }

    async def _search(
        self,
        sql: LiteralString,
        scope: Mapping[str, uuid.UUID],
        *,
        embedding: Sequence[float],
        limit: int,
    ) -> tuple[ChunkMatch, ...]:
        if limit < MIN_SEARCH_LIMIT:
            raise ChunkStoreError(f"limit must be at least {MIN_SEARCH_LIMIT}, got {limit}")
        params = {**scope, "embedding": _vector_param(embedding), "limit": limit}

        async with (
            self._source.connection() as connection,
            connection.cursor() as cursor,
        ):
            await cursor.execute(sql, params)
            rows = await cursor.fetchall()
        return tuple(_match(row) for row in rows)

    async def _insert(self, sql: LiteralString, rows: Sequence[Mapping[str, Any]]) -> int:
        """One `executemany` for the whole document, or no connection at all for none."""
        if not rows:
            return 0
        async with (
            self._source.connection() as connection,
            connection.cursor() as cursor,
        ):
            await cursor.executemany(sql, list(rows))
            written = cursor.rowcount
        return written


def _match(row: Mapping[str, Any]) -> ChunkMatch:
    """One `dict_row` as a `ChunkMatch`, or a loud failure — never a half-filled match."""
    try:
        return ChunkMatch.model_validate(dict(row))
    except ValidationError as err:
        raise ChunkStoreError(
            f"A chunk row has an unexpected shape: {err}. The read model and this query "
            "have drifted apart; re-check migrations/0001_init.sql."
        ) from err
