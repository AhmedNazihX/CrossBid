"""S2.2.1 — the embeddings client and the tenant-scoped vector store, both offline.

`httpx.MockTransport` drives the HTTP half, so the real request building, header assembly,
`raise_for_status` and retry policy run while every response is scripted here. The SQL half
runs against a recording connection that remembers the statement text and the bound
parameters, because those two strings *are* the tenant isolation: the API connects as a
`BYPASSRLS` role, so a missing `company_id` predicate has no second line of defence
(ADR-0009). Asserting the SQL is therefore a security test, not a style test.

Every payload is hand-built. ADR-0007 recorded three ordering and merge bugs that survived
a live rebuild of real eCertis data and only surfaced under constructed input; a real
OpenRouter response happens to arrive with `data` already sorted by `index`, so a client
that ignored `index` entirely would pass against it and silently mispair a German chunk
with a French chunk's vector the first time the provider batched differently.
"""

from __future__ import annotations

import contextlib
import inspect
import json
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from pgvector import Vector

from crossbid.ingestion.chunker import Chunk
from crossbid.ingestion.embeddings import (
    COMPANY_INSERT_SQL,
    COMPANY_SEARCH_SQL,
    DEFAULT_SEARCH_LIMIT,
    MAX_ATTEMPTS,
    OPENROUTER_EMBEDDINGS_PATH,
    SEARCH_STATEMENTS,
    TENANT_PREDICATE,
    TENDER_INSERT_SQL,
    TENDER_SEARCH_SQL,
    ChunkMatch,
    ChunkStoreError,
    ChunkVectorStore,
    EmbeddedChunk,
    EmbeddingsClient,
    EmbeddingsError,
    embed_chunks,
)
from crossbid.llm import OPENROUTER_BASE_URL
from crossbid.settings import ModelRole, Settings
from tests.conftest import (
    FAKE_OPENROUTER_KEY,
    FakeConnectionSource,
)

COMPANY_ID = UUID("11111111-1111-4111-8111-111111111111")
OTHER_COMPANY_ID = UUID("22222222-2222-4222-8222-222222222222")
BID_ID = UUID("33333333-3333-4333-8333-333333333333")
DOCUMENT_ID = UUID("44444444-4444-4444-8444-444444444444")

MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "0001_init.sql"

EXACT_IN_FLOAT32 = [0.5, 0.25, 0.125]
"""Powers of two, so a bound vector compares equal by eye: `Vector` narrows to `float4`,
which turns 0.1 into 0.10000000149011612."""

Handler = Callable[[httpx.Request], httpx.Response]


# ------------------------------------------------------------------------------ fixtures


@pytest.fixture
def settings(offline_settings: Settings) -> Settings:
    """`conftest`'s offline settings, under the name this module reads best with."""
    return offline_settings


@pytest.fixture
def dimensions(settings: Settings) -> int:
    return settings.runtime.ingestion.embed_dimensions


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Records the backoff instead of waiting it out, via the seam `_sleep` exists for."""
    recorded: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        recorded.append(seconds)

    monkeypatch.setattr(EmbeddingsClient, "_sleep", staticmethod(fake_sleep))
    return recorded


def build_client(
    settings: Settings, handler: Handler, **kwargs: Any
) -> tuple[EmbeddingsClient, list[httpx.Request]]:
    """A client whose transport is `handler`, plus the list of requests it has seen."""
    seen: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    http = httpx.AsyncClient(
        base_url=OPENROUTER_BASE_URL, transport=httpx.MockTransport(recording)
    )
    return EmbeddingsClient(settings, client=http, **kwargs), seen


def vector(fill: float, dimensions: int) -> list[float]:
    """A full-width vector whose every component is `fill`, so it is identifiable by eye."""
    return [fill] * dimensions


def embeddings_payload(rows: Sequence[tuple[int, Sequence[float]]]) -> dict[str, Any]:
    """An OpenAI-shaped `/embeddings` body, in exactly the row order given."""
    return {
        "object": "list",
        "data": [
            {"object": "embedding", "index": index, "embedding": list(values)}
            for index, values in rows
        ],
        "model": "openai/text-embedding-3-small",
    }


def answer_in_reverse(dimensions: int) -> Handler:
    """Echoes one vector per input, numbered by position but sent last-index-first.

    The adversarial case: a client that trusts arrival order instead of `index` pairs
    every text with the wrong vector and still sees a well-formed response.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        texts = _sent_input(request)
        rows = [(index, vector(float(index), dimensions)) for index in range(len(texts))]
        return httpx.Response(200, json=embeddings_payload(list(reversed(rows))))

    return handler


def _sent_input(request: httpx.Request) -> list[str]:
    payload = json.loads(request.read())
    assert isinstance(payload["input"], list), payload
    return payload["input"]


def scripted(*responses: httpx.Response) -> Handler:
    """Plays `responses` in order, then repeats the last one forever."""
    queue: Iterator[httpx.Response] = iter(responses)
    last: list[httpx.Response] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        with contextlib.suppress(StopIteration):
            last.append(next(queue))
        return last[-1]

    return handler


def store(
    rows: Sequence[Mapping[str, Any]] = (),
) -> tuple[ChunkVectorStore, FakeConnectionSource]:
    source = FakeConnectionSource(rows)
    return ChunkVectorStore(source), source


def match_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": 7,
        "document_id": DOCUMENT_ID,
        "document_name": "ISO_27001_Zertifikat.pdf",
        "page": 12,
        "pages": [12, 13],
        "text": "Wir sind nach ISO 27001 zertifiziert.",
        "token_count": 9,
        "distance": 0.0123,
    }
    return row | overrides


def chunk(index: int = 0, text: str = "ISO 27001", pages: tuple[int, ...] = (3,)) -> Chunk:
    return Chunk(
        document_id="de-pack",
        index=index,
        pages=pages,
        text=text,
        token_count=len(text.split()),
    )


# =================================================================== EmbeddingsClient


@pytest.mark.anyio
async def test_input_order_survives_a_response_that_arrives_reversed(
    settings: Settings, dimensions: int
) -> None:
    """The whole point of `index`: text *i* must get the vector labelled *i*."""
    # Arrange
    client, seen = build_client(settings, answer_in_reverse(dimensions))

    # Act
    async with client:
        vectors = await client.embed_texts(["first", "second", "third"])

    # Assert
    assert len(seen) == 1
    assert [values[0] for values in vectors] == [0.0, 1.0, 2.0]


@pytest.mark.anyio
async def test_batches_are_split_and_rejoined_in_input_order(
    settings: Settings, dimensions: int
) -> None:
    """Five texts at a batch size of two: three requests, one flat result, order intact."""
    # Arrange
    texts = [f"text-{position}" for position in range(5)]
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        batch = _sent_input(request)
        offset = texts.index(batch[0])
        calls.append(len(batch))
        rows = [
            (index, vector(float(offset + index), dimensions)) for index in range(len(batch))
        ]
        return httpx.Response(200, json=embeddings_payload(list(reversed(rows))))

    client, seen = build_client(settings, handler, batch_size=2)

    # Act
    async with client:
        vectors = await client.embed_texts(texts)

    # Assert
    assert len(seen) == 3
    assert calls == [2, 2, 1]
    assert [values[0] for values in vectors] == [0.0, 1.0, 2.0, 3.0, 4.0]


@pytest.mark.anyio
async def test_request_carries_the_configured_slug_and_the_bearer_key(
    settings: Settings, dimensions: int
) -> None:
    # Arrange
    client, seen = build_client(settings, answer_in_reverse(dimensions))

    # Act
    async with client:
        await client.embed_query("Informationssicherheit")

    # Assert
    request = seen[0]
    assert request.method == "POST"
    assert request.url.path.endswith(f"/{OPENROUTER_EMBEDDINGS_PATH}")
    assert request.headers["authorization"] == f"Bearer {FAKE_OPENROUTER_KEY}"
    body = json.loads(request.read())
    assert body["model"] == settings.runtime.models.for_role(ModelRole.EMBED)
    assert body["input"] == ["Informationssicherheit"]


@pytest.mark.anyio
async def test_embed_query_returns_one_full_width_vector(
    settings: Settings, dimensions: int
) -> None:
    # Arrange
    client, _seen = build_client(settings, answer_in_reverse(dimensions))

    # Act
    async with client:
        values = await client.embed_query("Informationssicherheit")

    # Assert
    assert len(values) == dimensions


@pytest.mark.anyio
async def test_no_texts_opens_no_request(settings: Settings) -> None:
    # Arrange
    client, seen = build_client(settings, scripted(httpx.Response(500)))

    # Act
    async with client:
        vectors = await client.embed_texts([])

    # Assert
    assert vectors == ()
    assert seen == []


@pytest.mark.anyio
async def test_blank_text_is_refused_before_the_request(settings: Settings) -> None:
    """OpenRouter answers 400 for an empty input; saying so here names the offending row."""
    # Arrange
    client, seen = build_client(settings, scripted(httpx.Response(200, json={})))

    # Act / Assert
    async with client:
        with pytest.raises(EmbeddingsError, match=r"blank.*\b1\b"):
            await client.embed_texts(["real text", "   "])
    assert seen == []


@pytest.mark.anyio
async def test_a_vector_of_the_wrong_width_is_refused(settings: Settings) -> None:
    """A silent dimension change would corrupt the whole index (ADR-0004)."""
    # Arrange
    payload = embeddings_payload([(0, [0.5, 0.5, 0.5])])
    client, _seen = build_client(settings, scripted(httpx.Response(200, json=payload)))

    # Act / Assert
    async with client:
        with pytest.raises(EmbeddingsError, match="1536 dimensions"):
            await client.embed_query("Informationssicherheit")


@pytest.mark.anyio
async def test_a_missing_row_is_refused(settings: Settings, dimensions: int) -> None:
    # Arrange
    payload = embeddings_payload([(0, vector(0.1, dimensions))])
    client, _seen = build_client(settings, scripted(httpx.Response(200, json=payload)))

    # Act / Assert
    async with client:
        with pytest.raises(EmbeddingsError, match="2 inputs"):
            await client.embed_texts(["one", "two"])


@pytest.mark.anyio
async def test_a_duplicate_index_is_refused(settings: Settings, dimensions: int) -> None:
    """Two rows both claiming `index: 0` would leave one input silently unembedded."""
    # Arrange
    payload = embeddings_payload([(0, vector(0.1, dimensions)), (0, vector(0.2, dimensions))])
    client, _seen = build_client(settings, scripted(httpx.Response(200, json=payload)))

    # Act / Assert
    async with client:
        with pytest.raises(EmbeddingsError, match=r"indices \[0, 0\]"):
            await client.embed_texts(["one", "two"])


@pytest.mark.anyio
async def test_an_unexpected_body_shape_is_refused(settings: Settings) -> None:
    # Arrange
    payload = {"data": [{"index": 0, "vector": [0.1]}]}
    client, _seen = build_client(settings, scripted(httpx.Response(200, json=payload)))

    # Act / Assert
    async with client:
        with pytest.raises(EmbeddingsError, match="unexpected shape"):
            await client.embed_query("hello")


@pytest.mark.anyio
async def test_malformed_json_is_refused(settings: Settings) -> None:
    # Arrange
    client, _seen = build_client(
        settings, scripted(httpx.Response(200, content=b"not json at all"))
    )

    # Act / Assert
    async with client:
        with pytest.raises(EmbeddingsError, match="malformed JSON"):
            await client.embed_query("hello")


@pytest.mark.anyio
async def test_a_json_array_body_is_refused(settings: Settings) -> None:
    # Arrange
    client, _seen = build_client(settings, scripted(httpx.Response(200, json=[1, 2, 3])))

    # Act / Assert
    async with client:
        with pytest.raises(EmbeddingsError, match="returned list"):
            await client.embed_query("hello")


# ------------------------------------------------------------------------ retry policy


@pytest.mark.anyio
async def test_a_rate_limit_is_retried_then_succeeds(
    settings: Settings, dimensions: int, sleeps: list[float]
) -> None:
    # Arrange
    payload = embeddings_payload([(0, vector(0.4, dimensions))])
    handler = scripted(httpx.Response(429), httpx.Response(200, json=payload))
    client, seen = build_client(settings, handler)

    # Act
    async with client:
        values = await client.embed_query("hello")

    # Assert
    assert len(values) == dimensions
    assert len(seen) == 2
    assert sleeps == [pytest.approx(2.0)]


@pytest.mark.anyio
async def test_a_transport_error_is_retried(
    settings: Settings, dimensions: int, sleeps: list[float]
) -> None:
    # Arrange
    attempts: list[int] = []
    payload = embeddings_payload([(0, vector(0.4, dimensions))])

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) == 1:
            raise httpx.ConnectError("connection refused")
        return httpx.Response(200, json=payload)

    client, _seen = build_client(settings, handler)

    # Act
    async with client:
        values = await client.embed_query("hello")

    # Assert
    assert len(values) == dimensions
    assert len(attempts) == 2
    assert sleeps == [pytest.approx(2.0)]


@pytest.mark.anyio
async def test_retries_are_exhausted_with_growing_backoff(
    settings: Settings, sleeps: list[float]
) -> None:
    # Arrange
    client, seen = build_client(settings, scripted(httpx.Response(503)))

    # Act / Assert
    async with client:
        with pytest.raises(EmbeddingsError, match=f"{MAX_ATTEMPTS} attempts"):
            await client.embed_query("hello")
    assert len(seen) == MAX_ATTEMPTS
    assert sleeps == [pytest.approx(2.0), pytest.approx(4.0)]


@pytest.mark.anyio
async def test_a_permanent_status_is_not_retried(
    settings: Settings, sleeps: list[float]
) -> None:
    """A 401 or a 404 will not become a 200; ADR-0005's unusable slug answers 404."""
    # Arrange
    client, seen = build_client(settings, scripted(httpx.Response(404)))

    # Act / Assert
    async with client:
        with pytest.raises(EmbeddingsError, match="404"):
            await client.embed_query("hello")
    assert len(seen) == 1
    assert sleeps == []


@pytest.mark.anyio
async def test_max_attempts_is_configurable(settings: Settings, sleeps: list[float]) -> None:
    # Arrange
    client, seen = build_client(settings, scripted(httpx.Response(503)), max_attempts=2)

    # Act / Assert
    async with client:
        with pytest.raises(EmbeddingsError):
            await client.embed_query("hello")
    assert len(seen) == 2


@pytest.mark.anyio
async def test_a_failure_message_never_carries_the_key(
    settings: Settings, sleeps: list[float]
) -> None:
    # Arrange
    client, _seen = build_client(settings, scripted(httpx.Response(500)))

    # Act
    async with client:
        with pytest.raises(EmbeddingsError) as raised:
            await client.embed_query("hello")

    # Assert
    assert FAKE_OPENROUTER_KEY not in str(raised.value)
    assert FAKE_OPENROUTER_KEY not in repr(raised.value)


def test_a_bad_batch_size_is_refused(settings: Settings) -> None:
    # Act / Assert
    with pytest.raises(ValueError, match="batch_size"):
        EmbeddingsClient(settings, batch_size=0)


def test_a_bad_attempt_count_is_refused(settings: Settings) -> None:
    # Act / Assert
    with pytest.raises(ValueError, match="max_attempts"):
        EmbeddingsClient(settings, max_attempts=0)


@pytest.mark.anyio
async def test_an_injected_client_is_not_closed(settings: Settings, dimensions: int) -> None:
    """The caller that owns the `AsyncClient` owns its lifetime."""
    # Arrange
    http = httpx.AsyncClient(
        base_url=OPENROUTER_BASE_URL,
        transport=httpx.MockTransport(answer_in_reverse(dimensions)),
    )
    client = EmbeddingsClient(settings, client=http)

    # Act
    async with client:
        await client.embed_query("hello")

    # Assert
    assert http.is_closed is False
    await http.aclose()


@pytest.mark.anyio
async def test_a_client_it_built_itself_is_closed(settings: Settings) -> None:
    """No transport is injected here, so nothing is sent — only the lifecycle is exercised."""
    # Arrange
    client = EmbeddingsClient(settings)

    # Act
    async with client:
        pass

    # Assert
    assert client.http.is_closed is True
    assert str(client.http.base_url).startswith(OPENROUTER_BASE_URL)


# ----------------------------------------------------------------------- embed_chunks


@pytest.mark.anyio
async def test_embed_chunks_pairs_each_chunk_with_its_own_vector(
    settings: Settings, dimensions: int
) -> None:
    # Arrange
    chunks = (chunk(0, "ISO 27001"), chunk(1, "Umsatz"), chunk(2, "Referenzen"))
    client, _seen = build_client(settings, answer_in_reverse(dimensions))

    # Act
    async with client:
        embedded = await embed_chunks(client, chunks)

    # Assert
    assert [row.chunk.index for row in embedded] == [0, 1, 2]
    assert [row.embedding[0] for row in embedded] == [0.0, 1.0, 2.0]


@pytest.mark.anyio
async def test_embed_chunks_of_nothing_is_nothing(settings: Settings) -> None:
    # Arrange
    client, seen = build_client(settings, scripted(httpx.Response(500)))

    # Act
    async with client:
        assert await embed_chunks(client, ()) == ()

    # Assert
    assert seen == []


# ================================================================== ChunkVectorStore
#
# The scope assertions below are the ADR-0009 tests. They are deliberately about the
# statement *text*: with `BYPASSRLS` there is nothing behind them.


def test_every_search_statement_carries_the_tenant_predicate() -> None:
    """A new search cannot be added without a `company_id` filter and still pass."""
    # Assert
    assert SEARCH_STATEMENTS, "the invariant is vacuous with no statements to check"
    for sql in SEARCH_STATEMENTS:
        assert TENANT_PREDICATE in sql, sql
        assert "%(company_id)s" in sql


def test_every_search_statement_scopes_the_chunk_table_itself() -> None:
    """The join brought a second `company_id` into scope, so the predicate is qualified.

    `documents` has its own `company_id`, `id`, `name` and `pages`. An unqualified
    `company_id = ...` would not be ambiguous *to a reader* but is ambiguous to Postgres,
    and the qualified form also pins which table's tenant column the filter is on --
    filtering `documents.company_id` while reading another tenant's chunks would be a leak
    that still returned rows (ADR-0009).
    """
    # Assert
    for sql, table in (
        (COMPANY_SEARCH_SQL, "company_chunks"),
        (TENDER_SEARCH_SQL, "tender_chunks"),
    ):
        assert f"where {table}.{TENANT_PREDICATE}" in sql, sql
        assert "join documents" in sql, sql
        assert "documents.name as document_name" in sql, sql


def test_no_statement_interpolates_a_value() -> None:
    """Every binding is a named placeholder; nothing is formatted into the SQL."""
    # Assert
    for sql in (*SEARCH_STATEMENTS, COMPANY_INSERT_SQL, TENDER_INSERT_SQL):
        assert "{" not in sql and "}" not in sql, sql
        assert "+" not in sql, sql


def test_the_search_operator_matches_the_index_the_migration_declares() -> None:
    """`<=>` is cosine distance; anything else would leave the HNSW index unused."""
    # Arrange
    migration = MIGRATION.read_text(encoding="utf-8")

    # Assert
    assert "using hnsw (embedding vector_cosine_ops)" in migration
    for sql in SEARCH_STATEMENTS:
        assert "<=>" in sql, sql


def test_search_signatures_make_an_unscoped_call_impossible() -> None:
    """`company_id` (and `bid_id`) are keyword-only and have no default, so they cannot
    be forgotten: the call does not type-check and does not run."""
    # Arrange
    required = {
        ChunkVectorStore.search_company_chunks: {"company_id"},
        ChunkVectorStore.search_tender_chunks: {"company_id", "bid_id"},
        ChunkVectorStore.insert_company_chunks: {"company_id"},
        ChunkVectorStore.insert_tender_chunks: {"company_id", "bid_id"},
    }

    # Assert
    for method, names in required.items():
        parameters = inspect.signature(method).parameters
        for name in names:
            parameter = parameters[name]
            assert parameter.kind is inspect.Parameter.KEYWORD_ONLY, name
            assert parameter.default is inspect.Parameter.empty, name


@pytest.mark.anyio
async def test_company_search_binds_the_company_scope() -> None:
    # Arrange
    vector_store, source = store([match_row()])

    # Act
    matches = await vector_store.search_company_chunks(
        company_id=COMPANY_ID, embedding=EXACT_IN_FLOAT32
    )

    # Assert
    statement = source.only
    assert statement.sql == COMPANY_SEARCH_SQL
    assert statement.params["company_id"] == COMPANY_ID
    assert statement.params["embedding"] == Vector(EXACT_IN_FLOAT32)
    assert statement.params["limit"] == DEFAULT_SEARCH_LIMIT
    assert "bid_id" not in statement.params
    assert matches == (
        ChunkMatch(
            id=7,
            document_id=DOCUMENT_ID,
            document_name="ISO_27001_Zertifikat.pdf",
            page=12,
            pages=(12, 13),
            text="Wir sind nach ISO 27001 zertifiziert.",
            token_count=9,
            distance=0.0123,
        ),
    )
    assert source.borrows == 1


@pytest.mark.anyio
async def test_tender_search_binds_both_scopes() -> None:
    # Arrange
    vector_store, source = store([match_row()])

    # Act
    await vector_store.search_tender_chunks(
        company_id=COMPANY_ID, bid_id=BID_ID, embedding=[1.0], limit=3
    )

    # Assert
    statement = source.only
    assert statement.sql == TENDER_SEARCH_SQL
    assert statement.params["company_id"] == COMPANY_ID
    assert statement.params["bid_id"] == BID_ID
    assert statement.params["limit"] == 3
    assert "%(bid_id)s" in statement.sql


@pytest.mark.anyio
async def test_one_company_scope_cannot_reach_another() -> None:
    """The same corpus, two tenants: the bound id is the only thing that differs."""
    # Arrange
    vector_store, source = store([match_row()])

    # Act
    await vector_store.search_company_chunks(company_id=COMPANY_ID, embedding=[1.0])
    await vector_store.search_company_chunks(company_id=OTHER_COMPANY_ID, embedding=[1.0])

    # Assert
    assert [statement.params["company_id"] for statement in source.log] == [
        COMPANY_ID,
        OTHER_COMPANY_ID,
    ]


@pytest.mark.anyio
async def test_search_returns_nothing_when_the_corpus_is_empty() -> None:
    # Arrange
    vector_store, _source = store([])

    # Act
    matches = await vector_store.search_company_chunks(company_id=COMPANY_ID, embedding=[1.0])

    # Assert
    assert matches == ()


@pytest.mark.anyio
async def test_matches_come_back_in_the_order_the_database_ranked_them() -> None:
    """`order by` lives in the SQL, so the store must not re-sort and must not reverse."""
    # Arrange
    rows = [match_row(id=1, distance=0.01), match_row(id=2, distance=0.42)]
    vector_store, _source = store(rows)

    # Act
    matches = await vector_store.search_company_chunks(company_id=COMPANY_ID, embedding=[1.0])

    # Assert
    assert [row.id for row in matches] == [1, 2]
    assert "order by" in COMPANY_SEARCH_SQL


@pytest.mark.anyio
async def test_a_non_positive_limit_is_refused() -> None:
    # Arrange
    vector_store, source = store([])

    # Act / Assert
    with pytest.raises(ChunkStoreError, match="limit"):
        await vector_store.search_company_chunks(
            company_id=COMPANY_ID, embedding=[1.0], limit=0
        )
    assert source.borrows == 0


@pytest.mark.anyio
async def test_an_empty_embedding_is_refused() -> None:
    # Arrange
    vector_store, source = store([])

    # Act / Assert
    with pytest.raises(ChunkStoreError, match="at least one dimension"):
        await vector_store.search_company_chunks(company_id=COMPANY_ID, embedding=[])
    assert source.borrows == 0


@pytest.mark.anyio
async def test_the_embedding_is_bound_as_a_vector_not_a_list() -> None:
    """pgvector registers its dumper for `Vector` and `numpy.ndarray`, never for `list`,
    so a list would be adapted as a Postgres array and rejected. The value is narrowed to
    `float4` on the way, which is what the `vector(1536)` column stores anyway."""
    # Arrange
    vector_store, source = store([])

    # Act
    await vector_store.search_company_chunks(company_id=COMPANY_ID, embedding=[0.1])

    # Assert
    bound = source.only.params["embedding"]
    assert isinstance(bound, Vector)
    assert bound.to_text() == "[0.10000000149011612]"


@pytest.mark.anyio
async def test_a_non_finite_embedding_is_refused() -> None:
    """`NaN` compares equal to nothing, so a poisoned vector ranks arbitrarily forever."""
    # Arrange
    vector_store, source = store([])

    # Act / Assert
    with pytest.raises(ChunkStoreError, match="NaN"):
        await vector_store.search_company_chunks(
            company_id=COMPANY_ID, embedding=[0.1, float("nan")]
        )
    assert source.borrows == 0


@pytest.mark.anyio
async def test_a_row_of_the_wrong_shape_is_reported_not_swallowed() -> None:
    # Arrange
    vector_store, _source = store([match_row(page=None)])

    # Act / Assert
    with pytest.raises(ChunkStoreError, match="unexpected shape"):
        await vector_store.search_company_chunks(company_id=COMPANY_ID, embedding=[1.0])


# --------------------------------------------------------------------------- inserting


@pytest.mark.anyio
async def test_inserting_company_chunks_binds_every_column() -> None:
    # Arrange
    embedded = (
        EmbeddedChunk(chunk=chunk(0, "ISO 27001", (3, 4)), embedding=(0.5, 0.25)),
        EmbeddedChunk(chunk=chunk(1, "Umsatz", (5,)), embedding=(0.125, 0.0625)),
    )
    vector_store, source = store()

    # Act
    written = await vector_store.insert_company_chunks(
        company_id=COMPANY_ID, document_id=DOCUMENT_ID, chunks=embedded
    )

    # Assert
    statement = source.only
    assert statement.is_many is True
    assert statement.sql == COMPANY_INSERT_SQL
    assert written == 2
    first, second = statement.params
    assert first == {
        "company_id": COMPANY_ID,
        "document_id": DOCUMENT_ID,
        "page": 3,
        "pages": [3, 4],
        "text": "ISO 27001",
        "token_count": 2,
        "embedding": Vector([0.5, 0.25]),
    }
    assert second["page"] == 5
    assert second["pages"] == [5]


@pytest.mark.anyio
async def test_inserting_tender_chunks_binds_the_bid_as_well() -> None:
    # Arrange
    embedded = (EmbeddedChunk(chunk=chunk(), embedding=(0.5,)),)
    vector_store, source = store()

    # Act
    await vector_store.insert_tender_chunks(
        company_id=COMPANY_ID, bid_id=BID_ID, document_id=DOCUMENT_ID, chunks=embedded
    )

    # Assert
    statement = source.only
    assert statement.sql == TENDER_INSERT_SQL
    assert statement.params[0]["bid_id"] == BID_ID
    assert statement.params[0]["company_id"] == COMPANY_ID


@pytest.mark.anyio
async def test_pages_are_bound_as_a_list_not_a_tuple() -> None:
    """psycopg adapts a `list` to `integer[]` and a `tuple` to a composite record, so a
    tuple here would fail against the `pages integer[]` column at run time."""
    # Arrange
    embedded = (EmbeddedChunk(chunk=chunk(pages=(1, 2)), embedding=(0.5,)),)
    vector_store, source = store()

    # Act
    await vector_store.insert_company_chunks(
        company_id=COMPANY_ID, document_id=DOCUMENT_ID, chunks=embedded
    )

    # Assert
    assert isinstance(source.only.params[0]["pages"], list)


@pytest.mark.anyio
async def test_inserting_nothing_borrows_no_connection() -> None:
    # Arrange
    vector_store, source = store()

    # Act
    written = await vector_store.insert_company_chunks(
        company_id=COMPANY_ID, document_id=DOCUMENT_ID, chunks=()
    )
    written_tender = await vector_store.insert_tender_chunks(
        company_id=COMPANY_ID, bid_id=BID_ID, document_id=DOCUMENT_ID, chunks=()
    )

    # Assert
    assert written == 0
    assert written_tender == 0
    assert source.borrows == 0
    assert source.log == []


@pytest.mark.anyio
async def test_an_empty_embedding_is_refused_on_insert() -> None:
    # Arrange
    embedded = (EmbeddedChunk(chunk=chunk(), embedding=()),)
    vector_store, source = store()

    # Act / Assert
    with pytest.raises(ChunkStoreError, match="at least one dimension"):
        await vector_store.insert_company_chunks(
            company_id=COMPANY_ID, document_id=DOCUMENT_ID, chunks=embedded
        )
    assert source.borrows == 0


# ------------------------------------------------------------------- odds and ends


def test_the_client_reports_the_configured_slug_and_width(settings: Settings) -> None:
    """Both are read by the live integration test and by cost logging, not decoration."""
    # Act
    client = EmbeddingsClient(settings)

    # Assert
    assert client.model == settings.runtime.models.for_role(ModelRole.EMBED)
    assert client.dimensions == settings.runtime.ingestion.embed_dimensions


@pytest.mark.anyio
async def test_the_real_sleep_seam_awaits() -> None:
    """The unpatched seam, once, at zero seconds: the retry path's only wall-clock wait."""
    # Act / Assert
    assert await EmbeddingsClient._sleep(0) is None
