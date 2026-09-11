"""Shared fixtures, and every fake that more than one test module needs.

Anything two modules share lives here, and **no test module imports another test module** —
`tests/unit/test_conftest_is_the_only_shared_ground.py` asserts it. The rule is not tidiness.
It is what the recording connection fake below is: the suite's tenant-scope assertions are
made against the SQL that fake records, because the API connects to Postgres as a `BYPASSRLS`
role and the `company_id` predicate in each statement is the only thing between two companies
(ADR-0009). When the same four names existed twice — one set modelling `connection.cursor()`,
another modelling `connection.execute()` — a security test asserted against whichever copy
its author happened to import, and neither copy could be strengthened for the whole suite.
A shared fake in a test module has the same failure mode waiting: the module that owns it is
free to reshape it for its own story, silently changing what somebody else's test proves.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import threading
import uuid
from collections.abc import AsyncIterator, Callable, Iterator, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from fastapi.testclient import TestClient

from crossbid.db import Database
from crossbid.ingestion.chunker import Chunker
from crossbid.ingestion.embeddings import EmbeddedChunk
from crossbid.ingestion.parser import DocumentSource, ParsedDocument, ParsedPage
from crossbid.ingestion.pipeline import DocumentPipeline, Upload
from crossbid.ingestion.storage import DEFAULT_CONTENT_TYPE, object_key
from crossbid.main import create_app
from crossbid.models import (
    CertificateHeld,
    CompanyProfile,
    DocumentKind,
    LegalForm,
    Tone,
    TurnoverYear,
)
from crossbid.readmodel.companies import profile_document
from crossbid.readmodel.documents import DocumentRecord, DocumentStatus, ReadModelError
from crossbid.reference import ecertis_client
from crossbid.settings import Settings, load_settings

BACKEND_DIR = Path(__file__).resolve().parent.parent
ECERTIS_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "ecertis"
ECERTIS_GENERATOR_PATH = BACKEND_DIR / "scripts" / "build_ecertis_cache.py"


# Distinctive so that a leak into a repr, a dump or an exception is unmistakable.
FAKE_OPENROUTER_KEY = "sk-or-v1-LEAKED-OPENROUTER-KEY"
FAKE_ENCRYPTION_KEY = "LEAKED-FERNET-ENCRYPTION-KEY="
FAKE_PASSWORD = "LEAKED-DATABASE-PASSWORD"

GOOD_DSN = f"postgresql://crossbid:{FAKE_PASSWORD}@localhost:5432/crossbid"
"""A DSN shaped like the real one. Every test that builds a pool starts from it."""

STARTUP_ENV_VARS = (
    "OPENROUTER_API_KEY",
    "APP_ENCRYPTION_KEY",
    "DATABASE_URL",
    "AUTH_MODE",
    "ENV",
    "LANGSMITH_API_KEY",
    "VERIFY_MODEL_SLUGS",
    "WEB_ORIGIN",
)


@pytest.fixture
def anyio_backend() -> str:
    """Run `@pytest.mark.anyio` tests on asyncio only; trio is not installed."""
    return "asyncio"


@pytest.fixture
def offline_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Settings the API starts with and that touch nothing outside the process.

    No `DATABASE_URL`, so `create_app` opens no pool -- CI's backend job exports one for
    the live tests, and a `TestClient` picking it up would make every route test hit
    Postgres. No dotenv layer, so a developer's real `.env` is never read.
    """
    for name in STARTUP_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_OPENROUTER_KEY)
    monkeypatch.setenv("APP_ENCRYPTION_KEY", FAKE_ENCRYPTION_KEY)
    return load_settings(env_file=None)


@pytest.fixture
def client(offline_settings: Settings) -> Iterator[TestClient]:
    """A client against a freshly built app, so no test inherits another's state.

    Entering the `with` runs the lifespan, so a route test also proves startup works.
    """
    with TestClient(create_app(offline_settings)) as test_client:
        yield test_client


# ------------------------------------------------------------------------------- eCertis


@pytest.fixture(autouse=True)
def _reset_ecertis_caches() -> Iterator[None]:
    """The cache loaders are `lru_cache`d, so one test's `DATA_DIR` must not leak.

    Autouse and on both sides of the test: a test that repoints `DATA_DIR` at a `tmp_path`
    would otherwise hand its temporary cache to whatever ran next.
    """
    ecertis_client.clear_caches()
    yield
    ecertis_client.clear_caches()


@pytest.fixture(scope="session")
def ecertis_generator() -> ModuleType:
    """`scripts/build_ecertis_cache.py` as an importable module.

    `scripts/` is not a package (and is omitted from coverage as an entry point), but the
    generator's rendering and write logic is exactly what the S1.1.1/S1.1.3 acceptance
    criteria are about, so it is loaded by path rather than left untested.
    """
    name = "build_ecertis_cache"
    spec = importlib.util.spec_from_file_location(name, ECERTIS_GENERATOR_PATH)
    assert spec is not None and spec.loader is not None, ECERTIS_GENERATOR_PATH
    module = importlib.util.module_from_spec(spec)
    # Registered before execution: the module defines a `@dataclass`, and dataclasses
    # resolve annotations through `sys.modules[cls.__module__]`.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class EcertisFixtureLoader:
    """Tiny reader so tests say `ecertis_fixture("criteria_list")`, not a path dance."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def __call__(self, name: str) -> dict[str, Any]:
        path = self._directory / f"{name}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(payload, dict), path
        return payload


@pytest.fixture(scope="session")
def ecertis_fixture() -> EcertisFixtureLoader:
    """Reads the recorded payloads in `tests/fixtures/ecertis/`. See its SOURCES.md."""
    return EcertisFixtureLoader(ECERTIS_FIXTURE_DIR)


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make retry backoff instant via the seam `EcertisRestClient._sleep` exists for."""
    monkeypatch.setattr(
        ecertis_client.EcertisRestClient, "_sleep", staticmethod(lambda _seconds: None)
    )


# ------------------------------------------------------------ the recording fake database

# One fake, not one per story. Every tenant-scope assertion in the suite is made against the
# statement text and the bound parameters this records: the API connects as a `BYPASSRLS`
# role, so the `company_id` predicate written into each statement is the only boundary
# between two companies (ADR-0009). When there were two of these — one modelling
# `connection.cursor()`, one modelling `connection.execute()` — which of them a security test
# ran through was an accident of which module its author had read, and a gap in one was
# invisible from the other.


@dataclass(frozen=True)
class RecordedStatement:
    """One statement a read model, a store or a tool sent, and what it bound to it."""

    sql: str
    params: Any
    is_many: bool = False
    """`executemany`, whose `params` is the whole sequence — the chunk writers use it."""


class FakeCursor:
    """The slice of `psycopg.AsyncCursor` this codebase drives, recording instead of running.

    Both shapes are here because production code uses both: the read models call
    `connection.execute(...)` and read one row or all of them back, while the vector store
    opens `connection.cursor()` as a context manager and `executemany`s a batch. Rows are
    scripted per source, so every statement answers with the same ones — a test that needs a
    second answer builds a second source.
    """

    def __init__(self, rows: Sequence[Mapping[str, Any]], log: list[RecordedStatement]) -> None:
        self._rows = list(rows)
        self._log = log
        self.rowcount = -1

    async def __aenter__(self) -> FakeCursor:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def execute(self, sql: str, params: Any = None) -> FakeCursor:
        self._log.append(RecordedStatement(sql=sql, params=params))
        self.rowcount = len(self._rows)
        return self

    async def executemany(self, sql: str, params_seq: Any) -> None:
        rows = list(params_seq)
        self._log.append(RecordedStatement(sql=sql, params=rows, is_many=True))
        self.rowcount = len(rows)

    async def fetchone(self) -> Mapping[str, Any] | None:
        return self._rows[0] if self._rows else None

    async def fetchall(self) -> list[Mapping[str, Any]]:
        return list(self._rows)


class FakeConnection:
    """One cursor per connection, so `cursor()` and `execute()` write to the same log."""

    def __init__(self, rows: Sequence[Mapping[str, Any]], log: list[RecordedStatement]) -> None:
        self._cursor = FakeCursor(rows, log)

    def cursor(self, **_kwargs: Any) -> FakeCursor:
        return self._cursor

    async def execute(self, sql: str, params: Any = None) -> FakeCursor:
        return await self._cursor.execute(sql, params)


class FakeConnectionSource:
    """Satisfies `ConnectionSource`, and counts how often a connection was borrowed."""

    def __init__(self, rows: Sequence[Mapping[str, Any]] = ()) -> None:
        self.log: list[RecordedStatement] = []
        self.borrows = 0
        self._rows = rows

    def connection(self) -> Any:
        source = self

        class _Borrow:
            async def __aenter__(self) -> FakeConnection:
                source.borrows += 1
                return FakeConnection(source._rows, source.log)

            async def __aexit__(self, *_exc: object) -> None:
                return None

        return _Borrow()

    @property
    def only(self) -> RecordedStatement:
        assert len(self.log) == 1, self.log
        return self.log[0]


# ---------------------------------------------------------------- the demo company

# The bidder every companies test reads and writes. Shared because the read model and the
# router prove different halves of the same story -- the row the statement returns, and the
# JSON the form gets back -- and they only add up if both start from one profile.

DEMO_COMPANY_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")

COMPANY_PROFILE = CompanyProfile(
    name="Beispiel IT Services GmbH",
    country="de",
    legal_form=LegalForm.GMBH,
    registration_number="HRB 84512",
    registration_court="Amtsgericht München",
    language="de",
    tone=Tone.PLAIN,
    staff_fte=48.0,
    staff_fte_relevant=31.5,
    turnover=(
        TurnoverYear(year=2025, amount=7_400_000.0, currency="EUR", field_of_activity="IT"),
    ),
    certificates=(
        CertificateHeld(
            name="ISO/IEC 27001:2022",
            issuer="TÜV Süd",
            number="12 345 678",
            issued_on=date(2023, 5, 1),
            expires_on=date(2026, 5, 1),
            scope="Betrieb von Rechenzentren",
        ),
    ),
)


def company_row(**overrides: Any) -> dict[str, Any]:
    """One `companies` row as `dict_row` hands it back: scalars flat, the rest in `profile`."""
    row: dict[str, Any] = {
        "id": DEMO_COMPANY_ID,
        "name": COMPANY_PROFILE.name,
        "country": COMPANY_PROFILE.country,
        "legal_form": COMPANY_PROFILE.legal_form.value,
        "language": COMPANY_PROFILE.language,
        "tone": COMPANY_PROFILE.tone.value,
        "profile": profile_document(COMPANY_PROFILE),
    }
    return row | overrides


# ------------------------------------------------------------------- the fake pool

# `Database.connect` takes a `pool_factory` seam, so these stand in for
# `AsyncConnectionPool` and nothing opens a socket. Shared because the router tests reach
# them too: each one ends by building its production dependencies over this pool, which is
# the only place `get_company_records` and friends are exercised for real.


@dataclass
class RecordingConnection:
    """Records every `execute` so a test can assert order and parameters."""

    executed: list[tuple[str, Any]] = field(default_factory=list)

    async def execute(self, query: str, params: Any = None) -> RecordingConnection:
        self.executed.append((query, params))
        return self


@dataclass
class FakePool:
    """Stands in for `AsyncConnectionPool`: records how it was built and driven."""

    conninfo: str
    kwargs: dict[str, Any]
    min_size: int
    max_size: int
    configure: Any
    open_flag: bool | None
    opened_with: dict[str, Any] | None = None
    closed: bool = False
    fail_open_with: Exception | None = None
    lent: RecordingConnection = field(default_factory=RecordingConnection)

    # `timeout` mirrors `AsyncConnectionPool.open`, which is the signature under test.
    async def open(self, *, wait: bool, timeout: float) -> None:  # noqa: ASYNC109
        if self.fail_open_with is not None:
            raise self.fail_open_with
        self.opened_with = {"wait": wait, "timeout": timeout}

    async def close(self) -> None:
        self.closed = True

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[RecordingConnection]:
        yield self.lent


class FakePoolFactory:
    """`pool_factory` seam: builds `FakePool`s and keeps the last one for assertions."""

    def __init__(self, *, fail_open_with: Exception | None = None) -> None:
        self.fail_open_with = fail_open_with
        self.built: list[FakePool] = []

    def __call__(self, conninfo: str, **kwargs: Any) -> Any:
        pool = FakePool(
            conninfo=conninfo,
            kwargs=kwargs["kwargs"],
            min_size=kwargs["min_size"],
            max_size=kwargs["max_size"],
            configure=kwargs["configure"],
            open_flag=kwargs["open"],
            fail_open_with=self.fail_open_with,
        )
        self.built.append(pool)
        return pool

    @property
    def last(self) -> FakePool:
        assert self.built, "no pool was built"
        return self.built[-1]


async def noop_configure(_conn: Any) -> None:
    """Stands in for `register_vector_async`, which needs a live connection."""


async def connect(factory: FakePoolFactory, **overrides: Any) -> Database:
    return await Database.connect(
        GOOD_DSN, pool_factory=factory, configure=noop_configure, **overrides
    )


FIXED_START = datetime(2026, 9, 11, 9, 0, tzinfo=UTC)
DIMENSIONS = 4
CHUNK_TOKENS = 64
OVERLAP_TOKENS = 8

PDF_BYTES = b"%PDF-1.7\n%fake body for the parser fake\n"
ORIGINAL_FILENAME = "Nachweis ISO 27001 (2026) Ümlaut.pdf"
"""Spaces, brackets and an umlaut: the key must not resemble it, the row must equal it."""

LEAKY_MESSAGE = (
    "Traceback (most recent call last): https://abcdefghijklmnopqrst.supabase.co/storage/v1 "
    "Authorization: Bearer sk-or-v1-LEAKED-OPENROUTER-KEY"
)
"""Everything a failure reason must never carry: a traceback marker, a URL and a key."""
LEAK_MARKERS = ("Traceback", "https://", "sk-or-", "Bearer")


# --------------------------------------------------------------- the upload pipeline

# The real `DocumentPipeline` needs six collaborators, and two stories drive it: the
# pipeline's own state machine and the router that runs it across the 202 boundary. They
# assert on the same transitions in the same order, so they are built from the same fakes
# -- `InMemoryRecords` in particular, whose `history` is what proves a poller sees
# `parsed` while the embeddings request is still in flight.


class CharacterEncoder:
    """One token per character, so the real `Chunker` runs without tiktoken's download."""

    def encode(self, text: str) -> list[int]:
        return [ord(character) for character in text]

    def decode(self, tokens: Sequence[int]) -> str:
        return "".join(chr(token) for token in tokens)


class FakeStore:
    """`CompanyDocumentStore.upload` by shape: records the call, builds the real key."""

    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.uploads: list[dict[str, Any]] = []
        self.threads: list[threading.Thread] = []

    def upload(
        self,
        *,
        company_id: str,
        document_id: str,
        filename: str,
        content: bytes,
        content_type: str = DEFAULT_CONTENT_TYPE,
    ) -> str:
        self.threads.append(threading.current_thread())
        if self.error is not None:
            raise self.error
        key = object_key(company_id=company_id, document_id=document_id, filename=filename)
        self.uploads.append(
            {
                "company_id": company_id,
                "document_id": document_id,
                "filename": filename,
                "content": content,
                "content_type": content_type,
                "key": key,
            }
        )
        return key


class FakeParser:
    """A `Parser` that answers with configured page texts, or raises."""

    name = "fake"

    def __init__(self, pages: Sequence[str], *, error: Exception | None = None) -> None:
        self.pages = tuple(pages)
        self.error = error
        self.sources: list[DocumentSource] = []
        self.threads: list[threading.Thread] = []

    def parse(self, source: DocumentSource, *, document_id: str) -> ParsedDocument:
        self.threads.append(threading.current_thread())
        self.sources.append(source)
        if self.error is not None:
            raise self.error
        return ParsedDocument(
            document_id=document_id,
            parser_name=self.name,
            pages=tuple(
                ParsedPage(page_number=number, text=text)
                for number, text in enumerate(self.pages, start=1)
            ),
        )


class FakeEmbedder:
    """`EmbeddingsClient` by shape. `observe` runs at call time, to catch the row mid-flight."""

    def __init__(
        self,
        *,
        error: Exception | None = None,
        extra_vectors: int = 0,
        observe: Callable[[], object] | None = None,
    ) -> None:
        self.error = error
        self.extra_vectors = extra_vectors
        self.observe = observe
        self.calls: list[list[str]] = []
        self.observed: list[object] = []
        self.closed = 0

    async def embed_texts(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        self.calls.append(list(texts))
        if self.observe is not None:
            self.observed.append(self.observe())
        if self.error is not None:
            raise self.error
        count = len(texts) + self.extra_vectors
        return tuple((float(index),) * DIMENSIONS for index in range(count))

    async def aclose(self) -> None:
        self.closed += 1


class FakeChunkWriter:
    """`ChunkVectorStore.insert_company_chunks` by shape."""

    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.inserts: list[dict[str, Any]] = []

    async def insert_company_chunks(
        self, *, company_id: uuid.UUID, document_id: uuid.UUID, chunks: Sequence[EmbeddedChunk]
    ) -> int:
        if self.error is not None:
            raise self.error
        self.inserts.append(
            {"company_id": company_id, "document_id": document_id, "chunks": tuple(chunks)}
        )
        return len(chunks)


@dataclass
class InMemoryRecords:
    """The `documents` read model over a dict, remembering every transition in order.

    Scoped like the real one: a transition on a row that is not this company's raises
    `ReadModelError`, and `get` for another company's id is `None`. Timestamps advance one
    second per write so `updated_at` is checkable without a real clock.
    """

    rows: dict[uuid.UUID, DocumentRecord] = field(default_factory=dict)
    history: list[DocumentRecord] = field(default_factory=list)
    """Every row exactly as written, in order. `rows` keeps only the latest per id."""
    fail_on: frozenset[str] = frozenset()
    writes: int = 0

    def _now(self) -> datetime:
        self.writes += 1
        return FIXED_START + timedelta(seconds=self.writes)

    def _write(self, record: DocumentRecord) -> DocumentRecord:
        self.rows[record.id] = record
        self.history.append(record)
        return record

    def _own(
        self, method: str, company_id: uuid.UUID, document_id: uuid.UUID
    ) -> DocumentRecord:
        if method in self.fail_on:
            raise ReadModelError(f"{method} refused: {LEAKY_MESSAGE}")
        found = self.rows.get(document_id)
        if found is None or found.company_id != company_id:
            raise ReadModelError(f"document {document_id} does not exist for this company")
        return found

    async def insert(
        self,
        *,
        company_id: uuid.UUID,
        document_id: uuid.UUID,
        kind: DocumentKind,
        name: str,
        storage_path: str,
    ) -> DocumentRecord:
        if "insert" in self.fail_on:
            raise ReadModelError(f"insert refused: {LEAKY_MESSAGE}")
        now = self._now()
        return self._write(
            DocumentRecord(
                id=document_id,
                company_id=company_id,
                kind=kind,
                name=name,
                storage_path=storage_path,
                status=DocumentStatus.UPLOADED,
                pages=0,
                created_at=now,
                updated_at=now,
            )
        )

    async def mark_parsed(
        self,
        *,
        company_id: uuid.UUID,
        document_id: uuid.UUID,
        pages: int,
        unread_pages: Sequence[int],
    ) -> DocumentRecord:
        found = self._own("mark_parsed", company_id, document_id)
        return self._write(
            found.model_copy(
                update={
                    "status": DocumentStatus.PARSED,
                    "pages": pages,
                    "unread_pages": tuple(unread_pages),
                    "updated_at": self._now(),
                }
            )
        )

    async def mark_embedded(
        self, *, company_id: uuid.UUID, document_id: uuid.UUID
    ) -> DocumentRecord:
        return self._advance("mark_embedded", company_id, document_id, DocumentStatus.EMBEDDED)

    async def mark_ready(
        self, *, company_id: uuid.UUID, document_id: uuid.UUID
    ) -> DocumentRecord:
        return self._advance("mark_ready", company_id, document_id, DocumentStatus.READY)

    async def mark_failed(
        self, *, company_id: uuid.UUID, document_id: uuid.UUID, reason: str
    ) -> DocumentRecord:
        found = self._own("mark_failed", company_id, document_id)
        return self._write(
            found.model_copy(
                update={
                    "status": DocumentStatus.FAILED,
                    "failure_reason": reason,
                    "updated_at": self._now(),
                }
            )
        )

    async def get(
        self, *, company_id: uuid.UUID, document_id: uuid.UUID
    ) -> DocumentRecord | None:
        found = self.rows.get(document_id)
        return found if found is not None and found.company_id == company_id else None

    async def list(self, *, company_id: uuid.UUID) -> tuple[DocumentRecord, ...]:
        own = [record for record in self.rows.values() if record.company_id == company_id]
        return tuple(sorted(own, key=lambda record: record.created_at, reverse=True))

    def _advance(
        self,
        method: str,
        company_id: uuid.UUID,
        document_id: uuid.UUID,
        status: DocumentStatus,
    ) -> DocumentRecord:
        found = self._own(method, company_id, document_id)
        return self._write(
            found.model_copy(update={"status": status, "updated_at": self._now()})
        )

    def history_of(self, document_id: uuid.UUID) -> list[DocumentRecord]:
        return [record for record in self.history if record.id == document_id]

    def statuses_of(self, document_id: uuid.UUID) -> list[DocumentStatus]:
        return [record.status for record in self.history_of(document_id)]


@dataclass
class Harness:
    """One pipeline and every fake it was built from, so a test can look at any of them."""

    store: FakeStore
    parser: FakeParser
    embedder: FakeEmbedder
    writer: FakeChunkWriter
    records: InMemoryRecords
    pipeline: DocumentPipeline


def harness(
    *,
    pages: Sequence[str] = ("Seite eins: ISO 27001 Zertifikat.", "Seite zwei: Umsatz 2025."),
    store: FakeStore | None = None,
    parser: FakeParser | None = None,
    embedder: FakeEmbedder | None = None,
    writer: FakeChunkWriter | None = None,
    records: InMemoryRecords | None = None,
) -> Harness:
    """The pipeline over fakes. Pass a fake to make one collaborator fail or observe."""
    store = store if store is not None else FakeStore()
    parser = parser if parser is not None else FakeParser(pages)
    embedder = embedder if embedder is not None else FakeEmbedder()
    writer = writer if writer is not None else FakeChunkWriter()
    records = records if records is not None else InMemoryRecords()
    pipeline = DocumentPipeline(
        store=store,
        parser=parser,
        chunker=Chunker(
            chunk_tokens=CHUNK_TOKENS, overlap_tokens=OVERLAP_TOKENS, encoder=CharacterEncoder()
        ),
        embedder=embedder,
        chunk_writer=writer,
        records=records,
    )
    return Harness(store, parser, embedder, writer, records, pipeline)


def upload(filename: str = ORIGINAL_FILENAME, content: bytes = PDF_BYTES) -> Upload:
    return Upload(filename=filename, content_type=DEFAULT_CONTENT_TYPE, content=content)
