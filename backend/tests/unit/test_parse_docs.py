"""S3.1.1 — `parse_docs`: the pack in, `TenderDocument`s out, and what would not open.

Offline. The node's three collaborators are fakes: a loader answering with rows, a fetcher
answering with bytes, and a parser scripted per document id. `storage_fetcher`, the real
fetcher, is tested over a fake store and `httpx.MockTransport`, so the tenancy check and
the error mapping run without a bucket or a socket.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from crossbid.agent.nodes import parse_docs as parse_docs_module
from crossbid.agent.nodes.parse_docs import (
    FETCH_TIMEOUT_SECONDS,
    DocumentFetchError,
    DocumentParser,
    build_parse_docs,
    storage_fetcher,
)
from crossbid.agent.state import BidState, ExtractionProblem, ExtractionProblemReason
from crossbid.ingestion.parser import ParsedDocument, ParsedPage, ParserError
from crossbid.ingestion.pymupdf_parser import PyMuPDFParser
from crossbid.ingestion.storage import (
    CompanyDocumentStore,
    ObjectNotFoundError,
    SignedUrl,
    StorageError,
)
from crossbid.models.ecertis_criteria import CRITERION_IDS
from crossbid.models.requirement import RequirementSource
from crossbid.models.tender import DocumentKind
from crossbid.readmodel.bids import BidDocumentRow
from crossbid.readmodel.documents import DocumentStatus
from crossbid.settings import Settings
from tests.conftest import espd_request_bytes, espd_request_xml

pytestmark = pytest.mark.anyio

COMPANY_ID = str(uuid.uuid4())
BID_ID = str(uuid.uuid4())
STORAGE_HOST = "https://storage.test"


# --------------------------------------------------------------------------------- fakes


def row(
    name: str,
    *,
    document_id: str | None = None,
    kind: DocumentKind = DocumentKind.TENDER_DOCUMENT,
) -> BidDocumentRow:
    identifier = document_id or str(uuid.uuid4())
    return BidDocumentRow(
        id=identifier,
        name=name,
        storage_path=f"{COMPANY_ID}/{identifier}/{name}",
        kind=kind,
        status=DocumentStatus.READY,
        bid_id=BID_ID,
        pages=0,
    )


def parsed(document_id: str, *texts: str) -> ParsedDocument:
    return ParsedDocument(
        document_id=document_id,
        parser_name="scripted",
        pages=tuple(
            ParsedPage(page_number=number, text=text) for number, text in enumerate(texts, 1)
        ),
    )


class ScriptedParser:
    """`Parser` by shape: answers per document id, or raises for ids marked broken."""

    name = "scripted"

    def __init__(
        self, script: dict[str, ParsedDocument], *, broken: Sequence[str] = ()
    ) -> None:
        self._script = script
        self._broken = set(broken)
        self.sources: list[bytes] = []

    def parse(self, source: Any, *, document_id: str) -> ParsedDocument:
        self.sources.append(source)
        if document_id in self._broken:
            raise ParserError("not a PDF")
        return self._script[document_id]


class Collaborators:
    """A loader and a fetcher that record what the node asked for."""

    def __init__(
        self,
        rows: Sequence[BidDocumentRow],
        *,
        fetch_error: Exception | None = None,
        content: Mapping[str, bytes] | None = None,
    ):
        self.rows = list(rows)
        self.loaded: list[tuple[str, str]] = []
        self.fetched: list[tuple[str, str]] = []
        self._fetch_error = fetch_error
        self._content = dict(content or {})

    async def load(self, company_id: str, bid_id: str) -> Sequence[BidDocumentRow]:
        self.loaded.append((company_id, bid_id))
        return self.rows

    async def fetch(self, company_id: str, document: BidDocumentRow) -> bytes:
        self.fetched.append((company_id, document.id))
        if self._fetch_error is not None:
            raise self._fetch_error
        if document.id in self._content:
            return self._content[document.id]
        return f"%PDF-{document.name}".encode()


def state(**overrides: Any) -> BidState:
    values: BidState = {
        "bid_id": BID_ID,
        "company_id": COMPANY_ID,
        "source_language": "de",
    }
    return {**values, **overrides}  # type: ignore[typeddict-item]


# ------------------------------------------------------------------------------ the node


async def test_every_document_is_parsed_in_row_order_with_its_name_and_language() -> None:
    # Arrange
    first, second = row("A_Bewerbungsbedingungen.pdf"), row("B_Leistungsbeschreibung.pdf")
    parser = ScriptedParser(
        {
            first.id: parsed(first.id, "Seite eins", "Seite zwei"),
            second.id: parsed(second.id, "x"),
        }
    )
    collaborators = Collaborators([first, second])
    node = DocumentParser(
        load_documents=collaborators.load, fetch=collaborators.fetch, parser=parser
    )

    # Act
    update = await node(state())

    # Assert
    assert [document.name for document in update["documents"]] == [first.name, second.name]
    assert all(document.language == "de" for document in update["documents"])
    assert update["documents"][0].parsed.page_count == 2
    assert update["extraction_problems"] == []
    assert collaborators.loaded == [(COMPANY_ID, BID_ID)]
    assert collaborators.fetched == [(COMPANY_ID, first.id), (COMPANY_ID, second.id)]
    assert parser.sources == [f"%PDF-{first.name}".encode(), f"%PDF-{second.name}".encode()]


async def test_a_file_that_will_not_open_is_reported_and_the_run_goes_on(
    caplog: pytest.LogCaptureFixture,
) -> None:
    good, bad = row("good.pdf"), row("bad.pdf")
    parser = ScriptedParser({good.id: parsed(good.id, "text")}, broken=[bad.id])
    collaborators = Collaborators([bad, good])
    node = DocumentParser(
        load_documents=collaborators.load, fetch=collaborators.fetch, parser=parser
    )

    with caplog.at_level(logging.ERROR, logger="crossbid.agent.nodes.parse_docs"):
        update = await node(state())

    assert [document.name for document in update["documents"]] == ["good.pdf"]
    assert update["extraction_problems"] == [
        ExtractionProblem(
            reason=ExtractionProblemReason.UNPARSEABLE_DOCUMENT, document_name="bad.pdf"
        )
    ]
    [record] = caplog.records
    assert "bad.pdf" in record.getMessage() and record.exc_info is not None


async def test_pages_without_a_text_layer_are_kept_and_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Listed, never dropped (S2.1.1): the node warns, extraction skips them, the reviewer
    sees them."""
    scanned = row("scan.pdf")
    parser = ScriptedParser({scanned.id: parsed(scanned.id, "text", "", "   ")})
    collaborators = Collaborators([scanned])
    node = DocumentParser(
        load_documents=collaborators.load, fetch=collaborators.fetch, parser=parser
    )

    with caplog.at_level(logging.WARNING, logger="crossbid.agent.nodes.parse_docs"):
        update = await node(state())

    [document] = update["documents"]
    assert document.parsed.unread_pages == (2, 3)
    assert document.parsed.page_count == 3
    [record] = caplog.records
    assert "2 page(s) with no text layer" in record.getMessage()


async def test_a_bid_with_no_documents_is_an_error_not_an_empty_pack() -> None:
    collaborators = Collaborators([])
    node = DocumentParser(
        load_documents=collaborators.load, fetch=collaborators.fetch, parser=ScriptedParser({})
    )

    with pytest.raises(ValueError, match="no documents attached"):
        await node(state())


@pytest.mark.parametrize(
    ("overrides", "missing"),
    [
        ({"bid_id": ""}, "bid_id"),
        ({"company_id": "  "}, "company_id"),
        ({"source_language": ""}, "source_language"),
        ({"company_id": "", "source_language": ""}, "company_id, source_language"),
    ],
)
async def test_a_state_missing_its_identity_names_what_is_missing(
    overrides: dict[str, str], missing: str
) -> None:
    collaborators = Collaborators([row("a.pdf")])
    node = DocumentParser(
        load_documents=collaborators.load, fetch=collaborators.fetch, parser=ScriptedParser({})
    )

    with pytest.raises(ValueError, match=f"parse_docs needs {missing}"):
        await node(state(**overrides))

    assert collaborators.loaded == [], "nothing is read under an unknown tenant"


async def test_a_fetch_failure_stops_the_run_rather_than_thinning_the_pack() -> None:
    """Storage refusing a file is an outage; a run that went on without half its pack would
    park at `awaiting_review` looking complete."""
    collaborators = Collaborators([row("a.pdf")], fetch_error=DocumentFetchError("refused"))
    node = DocumentParser(
        load_documents=collaborators.load, fetch=collaborators.fetch, parser=ScriptedParser({})
    )

    with pytest.raises(DocumentFetchError, match="refused"):
        await node(state())


def test_the_default_parser_is_pymupdf() -> None:
    collaborators = Collaborators([])
    node = DocumentParser(load_documents=collaborators.load, fetch=collaborators.fetch)

    assert isinstance(node.parser, PyMuPDFParser)


# ---------------------------------------------------------------------- storage_fetcher


class FakeStore:
    """`CompanyDocumentStore` by shape: signs its own company's keys, refuses the rest."""

    def __init__(self) -> None:
        self.signed: list[tuple[str, str]] = []

    def signed_url(self, *, company_id: str, key: str) -> SignedUrl:
        self.signed.append((company_id, key))
        if not key.startswith(f"{company_id}/"):
            raise ObjectNotFoundError("no such document for this company")
        return SignedUrl(
            url=f"{STORAGE_HOST}/sign/{key}?token=SECRET-TOKEN",
            expires_in=600,
            expires_at=datetime(2026, 9, 11, tzinfo=UTC),
        )


def fetcher_over(handler: Any, store: FakeStore | None = None) -> Any:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return storage_fetcher(store or FakeStore(), client=client)  # type: ignore[arg-type]


async def test_storage_fetcher_signs_for_the_company_then_downloads() -> None:
    document = row("a.pdf")
    store = FakeStore()
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, content=b"%PDF-1.7 bytes")

    fetch = fetcher_over(handler, store)

    content = await fetch(COMPANY_ID, document)

    assert content == b"%PDF-1.7 bytes"
    assert store.signed == [(COMPANY_ID, document.storage_path)]
    assert seen == [f"{STORAGE_HOST}/sign/{document.storage_path}?token=SECRET-TOKEN"]


async def test_a_key_of_another_company_is_refused_before_a_byte_moves() -> None:
    other = str(uuid.uuid4())
    document = row("a.pdf")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover -- never hit
        requests.append(request)
        return httpx.Response(200, content=b"x")

    fetch = fetcher_over(handler)

    with pytest.raises(DocumentFetchError) as caught:
        await fetch(other, document)

    assert requests == []
    assert document.id in str(caught.value)
    assert "ObjectNotFoundError" in str(caught.value)
    assert "SECRET-TOKEN" not in str(caught.value)
    assert document.storage_path not in str(caught.value)


async def test_an_http_error_from_storage_is_a_fetch_error_naming_the_document() -> None:
    document = row("a.pdf")
    fetch = fetcher_over(lambda request: httpx.Response(503))

    with pytest.raises(DocumentFetchError) as caught:
        await fetch(COMPANY_ID, document)

    assert document.id in str(caught.value)
    assert "HTTPStatusError" in str(caught.value)
    assert STORAGE_HOST not in str(caught.value)


async def test_an_empty_body_is_a_fetch_error() -> None:
    document = row("a.pdf")
    fetch = fetcher_over(lambda request: httpx.Response(200, content=b""))

    with pytest.raises(DocumentFetchError, match="came back empty"):
        await fetch(COMPANY_ID, document)


async def test_a_generic_storage_error_is_a_fetch_error() -> None:
    class RefusingStore:
        def signed_url(self, *, company_id: str, key: str) -> SignedUrl:
            raise StorageError("the document URL could not be signed")

    fetch = storage_fetcher(RefusingStore())  # type: ignore[arg-type]

    with pytest.raises(DocumentFetchError, match="StorageError"):
        await fetch(COMPANY_ID, row("a.pdf"))


def test_storage_fetcher_builds_its_own_client_with_the_file_timeout() -> None:
    """No client given: one is built with `FETCH_TIMEOUT_SECONDS`, and nothing connects."""
    fetch = storage_fetcher(FakeStore())  # type: ignore[arg-type]

    client = fetch.__closure__[0].cell_contents  # type: ignore[index, union-attr]
    assert isinstance(client, httpx.AsyncClient)
    assert client.timeout == httpx.Timeout(FETCH_TIMEOUT_SECONDS)


# ------------------------------------------------------------------------ build_parse_docs


def test_build_parse_docs_refuses_to_build_without_storage(offline_settings: Settings) -> None:
    with pytest.raises(StorageError, match="SUPABASE_URL"):
        build_parse_docs(offline_settings, object())  # type: ignore[arg-type]


async def test_build_parse_docs_wires_the_read_model_loader(
    offline_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[object, str, str]] = []
    rows = [row("a.pdf")]

    async def bid_documents(
        db: object, *, company_id: str, bid_id: str
    ) -> list[BidDocumentRow]:
        calls.append((db, company_id, bid_id))
        return rows

    monkeypatch.setattr(parse_docs_module, "bid_documents", bid_documents)
    db = object()
    store = CompanyDocumentStore(FakeStore(), ttl_seconds=600)  # type: ignore[arg-type]

    node = build_parse_docs(offline_settings, db, store=store)  # type: ignore[arg-type]
    loaded = await node._load_documents(COMPANY_ID, BID_ID)

    assert isinstance(node, DocumentParser)
    assert loaded == rows
    assert calls == [(db, COMPANY_ID, BID_ID)]


# ------------------------------------------------------------------ the published DUME


def espd_node(
    *rows_and_content: tuple[BidDocumentRow, bytes],
    extra: Sequence[BidDocumentRow] = (),
    parser: ScriptedParser | None = None,
) -> tuple[DocumentParser, Collaborators]:
    """The node over a pack that includes one or more ESPD requests with their bytes."""
    rows = [document for document, _ in rows_and_content] + list(extra)
    collaborators = Collaborators(
        rows, content={document.id: data for document, data in rows_and_content}
    )
    return (
        DocumentParser(
            load_documents=collaborators.load,
            fetch=collaborators.fetch,
            parser=parser or ScriptedParser({}),
        ),
        collaborators,
    )


async def test_a_published_dume_becomes_requirements_and_not_a_parsed_document() -> None:
    """S2.5.1: the XML never reaches the PDF parser, and its criteria arrive already mapped."""
    # Arrange
    dume = row("DUME_acheteur.xml", kind=DocumentKind.TENDER_ESPD_REQUEST)
    node, _ = espd_node((dume, espd_request_bytes()))

    # Act
    update = await node(state(source_language="fr"))

    # Assert
    assert update["documents"] == []
    assert update["extraction_problems"] == []
    rows = update["requirements"]
    assert len(rows) == 30
    assert all(row.ecertis_criterion_id is not None for row in rows)
    assert all(row.source is RequirementSource.ESPD_REQUEST for row in rows)
    assert all(row.page is None for row in rows)
    assert all(row.source_lang == "fr" for row in rows)
    assert all(row.bid_id == BID_ID for row in rows)
    assert all(row.document_name == "DUME_acheteur.xml" for row in rows)


async def test_a_pack_of_pdfs_and_a_dume_keeps_both_and_mixes_neither() -> None:
    # Arrange
    pdf = row("Reglement.pdf")
    dume = row("DUME_acheteur.xml", kind=DocumentKind.TENDER_ESPD_REQUEST)
    parser = ScriptedParser({pdf.id: parsed(pdf.id, "Article 1")})
    node, collaborators = espd_node((dume, espd_request_bytes()), extra=[pdf], parser=parser)

    # Act
    update = await node(state(source_language="fr"))

    # Assert
    assert [document.name for document in update["documents"]] == ["Reglement.pdf"]
    assert len(update["requirements"]) == 30
    assert parser.sources == [b"%PDF-Reglement.pdf"]
    assert collaborators.fetched == [(COMPANY_ID, dume.id), (COMPANY_ID, pdf.id)]


async def test_a_pack_without_a_dume_writes_no_requirements() -> None:
    """Extraction owns that channel too; parse_docs must not send it an empty list."""
    # Arrange
    pdf = row("Reglement.pdf")
    parser = ScriptedParser({pdf.id: parsed(pdf.id, "Article 1")})
    collaborators = Collaborators([pdf])
    node = DocumentParser(
        load_documents=collaborators.load, fetch=collaborators.fetch, parser=parser
    )

    # Act
    update = await node(state())

    # Assert
    assert "requirements" not in update


async def test_a_criterion_the_register_does_not_know_is_reported_to_the_reviewer() -> None:
    """Dropped loudly: one problem per criterion that could not be mapped (ADR-0007)."""
    # Arrange
    dume = row("DUME_acheteur.xml", kind=DocumentKind.TENDER_ESPD_REQUEST)
    data = espd_request_xml(
        (CRITERION_IDS[0], "CRITERION.EXCLUSION.CONVICTIONS.FRAUD", "Fraude", "Fraude ?"),
        ("ffffffff-ffff-4fff-8fff-ffffffffffff", "CRITERION.OTHER.X", "Inconnu", "?"),
    )
    node, _ = espd_node((dume, data))

    # Act
    update = await node(state(source_language="fr"))

    # Assert
    assert len(update["requirements"]) == 1
    assert update["extraction_problems"] == [
        ExtractionProblem(
            reason=ExtractionProblemReason.INVALID_CRITERION_ID,
            document_name="DUME_acheteur.xml",
        )
    ]


async def test_a_file_that_is_not_a_readable_espd_request_is_reported_and_the_run_goes_on(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Same shape as an unopenable PDF: one bad upload must not lose the bid (S3.4.4)."""
    # Arrange
    dume = row("not_really.xml", kind=DocumentKind.TENDER_ESPD_REQUEST)
    pdf = row("Reglement.pdf")
    parser = ScriptedParser({pdf.id: parsed(pdf.id, "Article 1")})
    node, _ = espd_node((dume, b"<hello/>"), extra=[pdf], parser=parser)

    # Act
    with caplog.at_level(logging.WARNING, logger="crossbid.agent.nodes.parse_docs"):
        update = await node(state(source_language="fr"))

    # Assert
    assert update["extraction_problems"] == [
        ExtractionProblem(
            reason=ExtractionProblemReason.UNPARSEABLE_DOCUMENT, document_name="not_really.xml"
        )
    ]
    assert [document.name for document in update["documents"]] == ["Reglement.pdf"]
    assert "not_really.xml" in caplog.text
