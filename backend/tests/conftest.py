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

import asyncio
import importlib.util
import json
import sys
import threading
import uuid
from collections.abc import AsyncIterator, Callable, Iterator, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel

from crossbid.agent.nodes.check_loop import (
    Bidder,
    CheckContext,
    CheckedRequirement,
    EvidenceRef,
)
from crossbid.db import Database
from crossbid.ingestion.chunker import Chunker
from crossbid.ingestion.embeddings import EmbeddedChunk
from crossbid.ingestion.injection_review import InjectionConfirmer, confirm_every_finding
from crossbid.ingestion.parser import DocumentSource, ParsedDocument, ParsedPage
from crossbid.ingestion.pipeline import DocumentPipeline, Upload
from crossbid.ingestion.pymupdf_parser import PyMuPDFParser
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
from crossbid.models.ecertis_criteria import CRITERION_IDS
from crossbid.models.matrix import RowStatus
from crossbid.models.requirement import (
    Checkability,
    Requirement,
    RequirementCategory,
    RequirementKind,
    RequirementSource,
    RequirementStage,
    Threshold,
)
from crossbid.readmodel.companies import profile_document
from crossbid.readmodel.documents import DocumentRecord, DocumentStatus, ReadModelError
from crossbid.readmodel.pagination import Page, PageCursor
from crossbid.reference import ecertis_client
from crossbid.settings import Settings, load_settings
from crossbid.tools.rag import RagHit, RagSearchResult

BACKEND_DIR = Path(__file__).resolve().parent.parent
ECERTIS_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "ecertis"
ECERTIS_GENERATOR_PATH = BACKEND_DIR / "scripts" / "build_ecertis_cache.py"
TENDERS_DIR = Path(__file__).resolve().parent / "fixtures" / "tenders"


def tender_pack_pdfs(fixture_dir: Path) -> dict[str, Path]:
    """Every PDF of a fixture tender by filename: the pack, plus the notice one level up.

    The notice sits beside `documents/` rather than inside it because it came from TED and
    the rest came from the buyer's platform, but a bidder reads both, so both are in scope.
    """
    pdfs = sorted(fixture_dir.glob("documents/*.pdf")) + sorted(fixture_dir.glob("*.pdf"))
    return {pdf.name: pdf for pdf in pdfs}


ESPD_REQUEST_PATH = TENDERS_DIR / "fr" / "documents" / "DUME_acheteur.xml"
"""The French buyer's published ESPD request (DUME), the one structured input in the whole
fixture set that carries canonical ESPD criterion ids. Four suites read it -- the reader
itself, the requirement mapping, the upload boundary and `parse_docs` -- and every one of
them must read the *same* bytes, because the claim they share is "30 criteria, all of them
in the generated register"."""

ESPD_NAMESPACES = {
    "espd-req": "urn:grow:names:specification:ubl:schema:xsd:ESPDRequest-1",
    "ccv": "urn:isa:names:specification:ubl:schema:xsd:CCV-CommonAggregateComponents-1",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "espd": "urn:grow:names:specification:ubl:schema:xsd:ESPDResponse-1",
}
"""ESPD 1.0.2's namespaces, copied from the fixture's own root element."""


def espd_request_bytes() -> bytes:
    """The committed ESPD request as uploaded bytes."""
    return ESPD_REQUEST_PATH.read_bytes()


def espd_request_xml(
    *criteria: tuple[str, str, str, str],
    root: str = "espd-req:ESPDRequest",
    language: str | None = None,
) -> bytes:
    """A synthetic ESPD request carrying exactly `criteria` as `(id, type code, name, text)`.

    Shared because the reader, the upload boundary and the pipeline all need to hand a
    *hostile or unusual* ESPD request to the code under test — an unknown criterion id, a
    repeated one, a wrong root element — and the committed fixture is by definition none of
    those. `root` takes the qualified name so a test can build a document that is XML but
    not an ESPD request; `language` sets UBL's `languageID`, which the fixture omits.
    """
    attribute = "" if language is None else f' languageID="{language}"'
    elements = "".join(
        f"<ccv:Criterion>"
        f'<cbc:ID schemeID="CriteriaID">{identifier}</cbc:ID>'
        f'<cbc:TypeCode listID="CriteriaTypeCode">{type_code}</cbc:TypeCode>'
        f"<cbc:Name{attribute}>{name}</cbc:Name>"
        f"<cbc:Description>{description}</cbc:Description>"
        f"</ccv:Criterion>"
        for identifier, type_code, name, description in criteria
    )
    declarations = " ".join(
        f'xmlns:{prefix}="{uri}"' for prefix, uri in ESPD_NAMESPACES.items()
    )
    document = (
        f'<?xml version="1.0" encoding="UTF-8"?><{root} {declarations}>{elements}</{root}>'
    )
    return document.encode()


@cache
def parsed_fixture_pdf(pdf: Path) -> ParsedDocument:
    """One parse per fixture PDF for the whole session, through the repo's own parser.

    Shared ground rather than a per-module cache because two suites re-derive claims from
    these pages -- `test_golden_labels` checks the answer keys, `test_recall_script` checks
    the committed extraction fixtures -- and the DE pack is 191 pages. Parsed twice it cost
    twenty seconds of every `make test`. It is `PyMuPDFParser` on purpose: a page number
    only means something relative to the reader that produced it, and this is the reader
    S3.2.1 runs.
    """
    return PyMuPDFParser().parse(pdf, document_id=pdf.name)


# Distinctive so that a leak into a repr, a dump or an exception is unmistakable.
FAKE_OPENROUTER_KEY = "sk-or-v1-LEAKED-OPENROUTER-KEY"
# A real Fernet key (32 url-safe base64 bytes) that still reads as a canary: it decodes
# to b"LEAKED-FERNET-ENCRYPTION-KEY-32b". It has to be genuinely valid since S5.4, because
# the offline tests now seal and open provider keys with it.
FAKE_ENCRYPTION_KEY = "TEVBS0VELUZFUk5FVC1FTkNSWVBUSU9OLUtFWS0zMmI="
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
    "SUPABASE_URL",
    "DEVELOPER_EMAILS",
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
        # Set to raise from `executemany`, which is how a test puts a writer's second
        # statement under the failure its transaction block exists to survive.
        self.fail_executemany: BaseException | None = None

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
        if self.fail_executemany is not None:
            raise self.fail_executemany

    async def fetchone(self) -> Mapping[str, Any] | None:
        return self._rows[0] if self._rows else None

    async def fetchall(self) -> list[Mapping[str, Any]]:
        return list(self._rows)


class FakeConnection:
    """One cursor per connection, so `cursor()` and `execute()` write to the same log."""

    def __init__(
        self,
        rows: Sequence[Mapping[str, Any]],
        log: list[RecordedStatement],
        transactions: list[str] | None = None,
    ) -> None:
        self._cursor = FakeCursor(rows, log)
        self.transactions = [] if transactions is None else transactions

    def cursor(self, **_kwargs: Any) -> FakeCursor:
        return self._cursor

    def transaction(self) -> Any:
        """`AsyncConnection.transaction()`, recording only how the block ended.

        Every pooled connection is `autocommit=True` (`db.pool_connection_kwargs`), so a
        writer whose statements have to land together must open a block explicitly. Recording
        the outcome is what lets a test prove a failed pair rolled back — counting borrows
        never could.
        """
        outcomes = self.transactions

        class _Block:
            async def __aenter__(self) -> Any:
                return self

            async def __aexit__(
                self, exc_type: type[BaseException] | None, *_exc: object
            ) -> bool:
                outcomes.append("rollback" if exc_type is not None else "commit")
                return False

        return _Block()

    async def execute(self, sql: str, params: Any = None) -> FakeCursor:
        return await self._cursor.execute(sql, params)


class FakeConnectionSource:
    """Satisfies `ConnectionSource`, and counts how often a connection was borrowed."""

    def __init__(self, rows: Sequence[Mapping[str, Any]] = ()) -> None:
        self.log: list[RecordedStatement] = []
        self.borrows = 0
        self._rows = rows
        #: How each transaction block this source handed out ended, in order.
        self.transactions: list[str] = []
        self.connections: list[FakeConnection] = []

    def connection(self) -> Any:
        source = self

        class _Borrow:
            async def __aenter__(self) -> FakeConnection:
                source.borrows += 1
                made = FakeConnection(source._rows, source.log, source.transactions)
                source.connections.append(made)
                return made

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

    async def set_flagged_chunks(
        self, *, company_id: uuid.UUID, document_id: uuid.UUID, flagged_chunks: Sequence[int]
    ) -> DocumentRecord:
        """What the guard withheld (S2.3.1). Writes no status, exactly as the real one does
        not — every kind is scanned, including the ones that never reach `embedded`."""
        found = self._own("set_flagged_chunks", company_id, document_id)
        return self._write(
            found.model_copy(
                update={"flagged_chunks": tuple(flagged_chunks), "updated_at": self._now()}
            )
        )

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

    async def delete(self, *, company_id: uuid.UUID, document_id: uuid.UUID) -> bool:
        found = self.rows.get(document_id)
        if found is None or found.company_id != company_id or found.bid_count:
            return False
        del self.rows[document_id]
        return True

    async def list(
        self, *, company_id: uuid.UUID, limit: int, after: PageCursor | None = None
    ) -> Page[DocumentRecord]:
        """The real read model's page (M13), ordered and sliced the way Postgres would.

        The fake pages for real rather than ignoring the arguments: a route that forgot to
        pass the cursor on would otherwise pass its tests and serve page one forever.
        """
        own = sorted(
            (record for record in self.rows.values() if record.company_id == company_id),
            key=lambda record: (record.created_at, record.id),
            reverse=True,
        )
        if after is not None:
            own = [
                record
                for record in own
                if (record.created_at, record.id) < (after.created_at, after.row_id)
            ]
        return Page.of(
            own[: limit + 1], limit=limit, key=lambda record: (record.created_at, record.id)
        )

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
        """The statuses a poller would have seen, which is not the same as the writes.

        Consecutive repeats are collapsed because a write that changes no status is not a
        transition: S2.3.1's `set_flagged_chunks` records what the injection guard withheld
        without advancing the row, and a test about the *order of statuses* should not start
        failing because a new column is written between two of them.
        """
        seen: list[DocumentStatus] = []
        for record in self.history_of(document_id):
            if not seen or seen[-1] is not record.status:
                seen.append(record.status)
        return seen


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
    confirm: InjectionConfirmer | None = None,
) -> Harness:
    """The pipeline over fakes. Pass a fake to make one collaborator fail or observe.

    `confirm` defaults to `confirm_every_finding` — the heuristic alone, no model — so a
    test that says nothing about S5.3 measures what the scanner decided and nothing else.
    """
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
        confirm=confirm_every_finding if confirm is None else confirm,
    )
    return Harness(store, parser, embedder, writer, records, pipeline)


def upload(filename: str = ORIGINAL_FILENAME, content: bytes = PDF_BYTES) -> Upload:
    return Upload(filename=filename, content_type=DEFAULT_CONTENT_TYPE, content=content)


# ------------------------------------------------------- the checking loop's scripted model

# `CheckContext` is two async callables and a dict of tools (S3.3.1), which is the whole
# reason every checking branch can be driven with no provider and no socket. Shared because
# two modules drive it and must drive the *same* one: `test_check_reqs.py` proves the loop
# itself -- the citation resolution, the tool budget, the fan-out -- and
# `test_check_statuses.py` (S3.3.2) pins one row shape per `RowStatus` so that an edit to
# `prompts/check.md` or a swapped model slug cannot quietly change the matrix. A second copy
# of `ScriptedModel` would let one of those stories reshape the fake the other one's
# regression guard is written against, which is the failure this file exists to prevent.

COMPANY_ID = str(DEMO_COMPANY_ID)
BID_ID = str(uuid.UUID("33333333-3333-4333-8333-333333333333"))
DOCUMENT_ID = str(uuid.UUID("44444444-4444-4444-8444-444444444444"))

TURNOVER = "Der Umsatz muss mindestens 3.000.000,00 EUR pro Jahr betragen."
SUBMIT = "Das Formblatt 124 ist mit dem Angebot einzureichen."
QUOTE = "Der Jahresumsatz 2025 betrug 7.400.000,00 EUR im Bereich IT-Dienstleistungen."
DOCUMENT_NAME = "Bewerbungsbedingungen_VV2_V1.pdf"
EVIDENCE_NAME = "Jahresabschluss_2025.pdf"
REAL_CRITERION_ID = CRITERION_IDS[0]

BIDDER = Bidder(country="de", language="de")


def requirement(
    source_text: str = TURNOVER,
    *,
    page: int | None = 4,
    checkable: Checkability = Checkability.COMPANY_PROPERTY,
    criterion_id: str | None = None,
    identifier: str | None = None,
    source: RequirementSource = RequirementSource.TENDER_DOCUMENT,
    document_name: str = DOCUMENT_NAME,
    category: RequirementCategory = RequirementCategory.ECONOMIC_FINANCIAL,
    kind: RequirementKind = RequirementKind.MANDATORY,
    stage: RequirementStage = RequirementStage.BID_ELIGIBILITY,
    threshold: Threshold | None = None,
    translation: str | None = None,
) -> Requirement:
    """One extracted requirement, defaulting to the kind a company document can settle.

    `source` and `page` travel together: an `ESPD_REQUEST` row carries `page=None`, which
    `Requirement` enforces (S2.5.1), so a caller that flips one must flip the other.

    `category`, `kind` and `stage` are keywords because S3.4.1's scorer turns on all three:
    it reads only `bid_eligibility` rows, treats `mandatory` as the gate, and gives an
    `exclusion_ground` its own severity whatever its kind says.
    """
    return Requirement(
        id=identifier or str(uuid.uuid5(uuid.NAMESPACE_URL, source_text)),
        bid_id=BID_ID,
        category=category,
        kind=kind,
        stage=stage,
        checkable=checkable,
        source=source,
        source_text=source_text,
        source_lang="de",
        document_name=document_name,
        page=page,
        translation=translation,
        threshold=threshold,
        ecertis_criterion_id=criterion_id,  # type: ignore[arg-type]
    )


def hit(*, quote: str = QUOTE, page: int = 2, name: str = EVIDENCE_NAME) -> RagHit:
    """One retrieved passage, as `RagSearchResult` carries it on a tool's artifact."""
    return RagHit(
        document_id=DOCUMENT_ID,
        document_name=name,
        page=page,
        pages=(page,),
        quote=quote,
        score=0.81,
    )


def rag_result(*hits: RagHit, query: str = "Jahresumsatz") -> RagSearchResult:
    return RagSearchResult(query=query, corpus="the company's own documents", hits=hits)


def verdict(
    status: RowStatus = RowStatus.SUPPORTED,
    *,
    rationale: str = "Der Jahresabschluss weist 7,4 Mio. EUR aus.",
    evidence: Sequence[tuple[int, int]] = ((1, 1),),
) -> CheckedRequirement:
    """What the model answers, before anything about it is believed."""
    return CheckedRequirement(
        status=status,
        rationale=rationale,
        evidence=[EvidenceRef(search=search, passage=passage) for search, passage in evidence],
    )


class ScriptedModel:
    """A `CheckContext`'s two seams, scripted, recording every prompt it was handed.

    The recording is what makes the data-block postcondition assertable: the promise is
    about the bytes the model receives, and nothing short of holding those bytes checks it.
    `in_flight` is the other half -- a lane that ran two requirements at once would be
    invisible to a row assertion and obvious here.
    """

    def __init__(
        self,
        turns: Sequence[AIMessage | Exception],
        answer: CheckedRequirement | Exception | Sequence[CheckedRequirement | Exception] = (
            verdict()
        ),
    ) -> None:
        self._turns = list(turns)
        # A sequence so S3.4.4's re-ask can be scripted: the verdict call may now happen
        # twice for one requirement, and the second answer has to be able to differ from the
        # first. A scalar is a script of one, and the last entry repeats — the same rule
        # `turn` already follows, so the two seams behave alike.
        self._answers: list[CheckedRequirement | Exception] = (
            list(answer)
            if isinstance(answer, Sequence) and not isinstance(answer, str)
            else [answer]
        )
        self.prompts: list[list[BaseMessage]] = []
        self.verdict_prompts: list[list[BaseMessage]] = []
        self.in_flight = 0
        self.peak_in_flight = 0

    async def turn(self, messages: Sequence[BaseMessage]) -> AIMessage:
        self.prompts.append(list(messages))
        self.in_flight += 1
        self.peak_in_flight = max(self.peak_in_flight, self.in_flight)
        try:
            await asyncio.sleep(0)
            result = self._turns[min(len(self.prompts) - 1, len(self._turns) - 1)]
            if isinstance(result, Exception):
                raise result
            return result
        finally:
            self.in_flight -= 1

    async def verdict(self, messages: Sequence[BaseMessage]) -> CheckedRequirement:
        self.verdict_prompts.append(list(messages))
        answer = self._answers[min(len(self.verdict_prompts) - 1, len(self._answers) - 1)]
        if isinstance(answer, Exception):
            raise answer
        return answer

    @property
    def verdicts_asked(self) -> int:
        return len(self.verdict_prompts)

    @property
    def turns_taken(self) -> int:
        return len(self.prompts)


def answers(text: str = "Nichts mehr zu suchen.") -> AIMessage:
    """A turn with no tool calls: the model is ready to answer."""
    return AIMessage(content=text)


def calls(*names_and_args: tuple[str, dict[str, Any]]) -> AIMessage:
    """A turn that asks for tools, numbered as the loop counts them."""
    return AIMessage(
        content="",
        tool_calls=[
            {"name": name, "args": args, "id": f"call-{index}", "type": "tool_call"}
            for index, (name, args) in enumerate(names_and_args, start=1)
        ],
    )


def search_call(query: str = "Jahresumsatz") -> AIMessage:
    return calls(("company_rag_search", {"query": query}))


def rag_tool(
    *results: RagSearchResult | Exception, name: str = "company_rag_search"
) -> tuple[BaseTool, list[str]]:
    """A `content_and_artifact` tool exactly like the real ones, answering from a script.

    Returns the tool and the list of queries it was asked, which is what a budget assertion
    counts: the loop's own counter and the tool's record have to agree.
    """
    seen: list[str] = []

    class Args(BaseModel):
        query: str

    async def run(query: str) -> tuple[str, RagSearchResult]:
        seen.append(query)
        result = results[min(len(seen) - 1, len(results) - 1)]
        if isinstance(result, Exception):
            raise result
        return result.render(), result

    tool = StructuredTool.from_function(
        coroutine=run,
        name=name,
        description="search the company's documents",
        args_schema=Args,
        response_format="content_and_artifact",
    )
    return tool, seen


def check_context(
    model: ScriptedModel,
    *,
    tools: Mapping[str, BaseTool] | None = None,
    max_tool_calls: int = 4,
    bidder: Bidder = BIDDER,
    system_prompt: str | None = None,
) -> CheckContext:
    """One lane's checking context over a scripted model."""
    return CheckContext(
        turn=model.turn,
        verdict=model.verdict,
        tools=dict(tools or {}),
        max_tool_calls=max_tool_calls,
        bidder=bidder,
        system_prompt=system_prompt,
    )


class ScriptedSession:
    """A `SessionBuilder` that yields a fixed context and counts open/close pairs."""

    def __init__(
        self, model: ScriptedModel, *, tools: Mapping[str, BaseTool] | None = None
    ) -> None:
        self.model = model
        self.tools = dict(tools or {})
        self.opened: list[tuple[str, str, Bidder]] = []
        self.closed = 0

    def __call__(self, company_id: str, bid_id: str, bidder: Bidder) -> Any:
        session = self

        class _Open:
            async def __aenter__(self) -> CheckContext:
                session.opened.append((company_id, bid_id, bidder))
                return check_context(session.model, tools=session.tools)

            async def __aexit__(self, *_exc: object) -> None:
                session.closed += 1

        return _Open()
