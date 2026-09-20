"""S2.2.3 — `POST /documents` answers 202 and the row becomes `ready` while the browser polls.

Offline, end to end through HTTP: the app is the real `create_app`, the router is the real
one, and behind `get_pipeline` runs the real `DocumentPipeline` over the fakes
`test_ingestion_pipeline.py` defines. `TestClient` runs Starlette's background task before it
hands the response back, so the test that polls `GET /documents/{id}` right after the 202
sees the finished row — the same two requests the browser makes, minus the wait.

Two production dependencies are exercised for real rather than overridden: `get_pipeline`
against settings with and without Storage wiring (a 503 that names the problem, a pipeline
that opens no socket), and `get_document_records` over a recording fake database, which is
how the router's 404 for another company's id is shown to come from a scoped statement.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr
from starlette.datastructures import Headers, UploadFile

from crossbid.auth import DEV_COMPANY_HEADER
from crossbid.company_keys import get_company_settings
from crossbid.deps import get_database
from crossbid.ingestion.parser import ParserError
from crossbid.ingestion.pipeline import UNREADABLE_REASON, DocumentPipeline
from crossbid.ingestion.safe_xml import MAX_XML_BYTES
from crossbid.ingestion.storage import (
    DEFAULT_CONTENT_TYPE,
    XML_CONTENT_TYPE,
    CompanyDocumentStore,
    ObjectNotFoundError,
    SignedUrl,
    StorageError,
    object_key,
)
from crossbid.main import create_app
from crossbid.models import DocumentKind
from crossbid.readmodel.documents import DocumentsReadModel, DocumentStatus, ReadModelError
from crossbid.routers.documents import (
    EMPTY_FILE_DETAIL,
    MAX_UPLOAD_BYTES,
    NO_FILENAME_DETAIL,
    NO_SUCH_DOCUMENT_DETAIL,
    NOT_DELETED_DETAIL,
    NOT_ESPD_CONTENT_DETAIL,
    NOT_PDF_CONTENT_DETAIL,
    NOT_PDF_SUFFIX_DETAIL,
    NOT_PDF_TYPE_DETAIL,
    NOT_XML_SUFFIX_DETAIL,
    NOT_XML_TYPE_DETAIL,
    STORAGE_NOT_CONFIGURED_DETAIL,
    TOO_LARGE_DETAIL,
    URL_NOT_SIGNED_DETAIL,
    XML_TOO_LARGE_DETAIL,
    DocumentListResponse,
    DocumentResponse,
    DocumentUrlResponse,
    document_in_use_detail,
    get_document_records,
    get_document_store,
    get_pipeline,
    router,
    validated_upload,
)
from crossbid.settings import Settings
from tests.conftest import (
    LEAKY_MESSAGE,
    ORIGINAL_FILENAME,
    PDF_BYTES,
    FakeConnectionSource,
    FakeParser,
    Harness,
    InMemoryRecords,
    espd_request_bytes,
    harness,
)

COMPANY = "11111111-1111-4111-8111-111111111111"
OTHER_COMPANY = "22222222-2222-4222-8222-222222222222"
AS_COMPANY = {DEV_COMPANY_HEADER: COMPANY}
AS_OTHER_COMPANY = {DEV_COMPANY_HEADER: OTHER_COMPANY}

FAKE_SUPABASE_URL = "https://abcdefghijklmnopqrst.supabase.co"
FAKE_SERVICE_KEY = "sb_secret_LEAKED-SERVICE-ROLE-KEY"

Overrides = dict[Callable[..., Any], Callable[..., Any]]


# ---------------------------------------------------------------------------- fixtures


@pytest.fixture
def pipeline() -> Harness:
    return harness()


def build_app(settings: Settings, overrides: Overrides) -> FastAPI:
    """The real app with the real router; only the named dependencies are replaced."""
    app = create_app(settings)
    app.include_router(router)
    app.dependency_overrides.update(overrides)
    return app


@pytest.fixture
def api(offline_settings: Settings, pipeline: Harness) -> Iterator[TestClient]:
    """The router over the fake pipeline and its in-memory `documents` table."""
    overrides: Overrides = {
        get_pipeline: lambda: pipeline.pipeline,
        get_document_records: lambda: pipeline.records,
    }
    with TestClient(build_app(offline_settings, overrides)) as client:
        yield client


def pdf_part(
    filename: str = ORIGINAL_FILENAME,
    content: bytes = PDF_BYTES,
    content_type: str | None = DEFAULT_CONTENT_TYPE,
) -> dict[str, tuple[str, bytes, str | None]]:
    return {"file": (filename, content, content_type)}


def post_pdf(api: TestClient, **part: Any) -> Any:
    return api.post(
        "/documents",
        files=pdf_part(**part),
        data={"kind": "company_evidence"},
        headers=AS_COMPANY,
    )


FAKE_BUCKET = "company-docs"
"""Stated, not defaulted. `supabase_storage_bucket` lost its default on 2026-09-16 because a
guessed bucket name is a bucket that does not exist: the old `company-documents` was not the
Frankfurt project's `company-docs`, and `storage.py` swallows Storage's own 404 on purpose,
so every upload failed with a sentence that named nothing. This test passed locally and broke
CI, which is the difference between a developer's `.env` and a clean machine."""


def with_storage(settings: Settings) -> Settings:
    """Settings whose env layer carries Storage wiring; the original is untouched."""
    env = settings.env.model_copy(
        update={
            "supabase_url": FAKE_SUPABASE_URL,
            "supabase_service_role_key": SecretStr(FAKE_SERVICE_KEY),
            "supabase_storage_bucket": FAKE_BUCKET,
        }
    )
    return Settings(env=env, runtime=settings.runtime)


# ------------------------------------------------------------------------- the 202


def test_an_upload_is_accepted_with_an_id_and_the_uploaded_status(api: TestClient) -> None:
    # Act
    response = post_pdf(api)

    # Assert
    assert response.status_code == 202
    body = response.json()
    uuid.UUID(body["id"])
    assert body["status"] == "uploaded"
    assert body["kind"] == "company_evidence"
    assert body["name"] == ORIGINAL_FILENAME
    assert body["bid_count"] == 0
    assert body["failure_reason"] is None
    assert body["pages"] == 0
    assert body["unread_pages"] == [] and body["unread_page_count"] == 0
    assert body["created_at"] == body["updated_at"]


def test_the_response_carries_nothing_the_browser_has_no_use_for(api: TestClient) -> None:
    """`storage_path` is a key into a private bucket and `company_id` is the caller's own."""
    body = post_pdf(api).json()

    assert set(body) == set(DocumentResponse.model_fields)
    assert "storage_path" not in body and "company_id" not in body


def test_every_response_field_is_described_for_the_generated_client() -> None:
    """`frontend/lib/api.ts` is generated from this schema; a bare field is a bare type."""
    for model in (DocumentResponse, DocumentListResponse, DocumentUrlResponse):
        for name, info in model.model_fields.items():
            assert info.description, f"{model.__name__}.{name} has no description"


# ------------------------------------------------------------ upload → ready, polled


def test_polling_after_the_202_shows_the_document_ready_with_its_pages(
    api: TestClient, pipeline: Harness
) -> None:
    # Arrange
    document_id = post_pdf(api).json()["id"]

    # Act
    response = api.get(f"/documents/{document_id}", headers=AS_COMPANY)

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["pages"] == 2 and body["unread_pages"] == [] and body["unread_page_count"] == 0
    assert body["updated_at"] > body["created_at"]
    assert pipeline.records.statuses_of(uuid.UUID(document_id)) == [
        DocumentStatus.UPLOADED,
        DocumentStatus.PARSED,
        DocumentStatus.EMBEDDED,
        DocumentStatus.READY,
    ]


def test_unread_pages_are_listed_and_counted_on_the_document(
    offline_settings: Settings,
) -> None:
    # Arrange
    h = harness(pages=("Seite eins.", "", "Seite drei.", ""))
    overrides: Overrides = {
        get_pipeline: lambda: h.pipeline,
        get_document_records: lambda: h.records,
    }

    # Act
    with TestClient(build_app(offline_settings, overrides)) as api:
        document_id = post_pdf(api).json()["id"]
        body = api.get(f"/documents/{document_id}", headers=AS_COMPANY).json()

    # Assert
    assert body["status"] == "ready"
    assert body["pages"] == 4
    assert body["unread_pages"] == [2, 4]
    assert body["unread_page_count"] == 2


def test_a_failed_document_shows_a_reason_the_bidder_can_act_on(
    offline_settings: Settings,
) -> None:
    # Arrange
    h = harness(parser=FakeParser((), error=ParserError(LEAKY_MESSAGE)))
    overrides: Overrides = {
        get_pipeline: lambda: h.pipeline,
        get_document_records: lambda: h.records,
    }

    # Act
    with TestClient(build_app(offline_settings, overrides)) as api:
        document_id = post_pdf(api).json()["id"]
        body = api.get(f"/documents/{document_id}", headers=AS_COMPANY).json()

    # Assert
    assert body["status"] == "failed"
    assert body["failure_reason"] == UNREADABLE_REASON
    assert "https://" not in body["failure_reason"]
    assert h.embedder.closed == 1, "the background task released the embeddings client"


def test_the_original_filename_is_kept_and_the_storage_key_is_sanitised(
    api: TestClient, pipeline: Harness
) -> None:
    # Act
    body = post_pdf(api).json()

    # Assert
    record = pipeline.records.rows[uuid.UUID(body["id"])]
    assert body["name"] == ORIGINAL_FILENAME
    assert record.name == ORIGINAL_FILENAME
    assert record.storage_path == object_key(
        company_id=COMPANY, document_id=body["id"], filename=ORIGINAL_FILENAME
    )
    assert " " not in record.storage_path and "Ü" not in record.storage_path
    (uploaded,) = pipeline.store.uploads
    assert uploaded["key"] == record.storage_path
    assert uploaded["content"] == PDF_BYTES


def test_a_tender_document_is_accepted_and_becomes_ready_without_vectors(
    api: TestClient, pipeline: Harness
) -> None:
    # Act
    response = api.post(
        "/documents", files=pdf_part(), data={"kind": "tender_document"}, headers=AS_COMPANY
    )

    # Assert
    assert response.status_code == 202
    body = api.get(f"/documents/{response.json()['id']}", headers=AS_COMPANY).json()
    assert body["kind"] == "tender_document" and body["status"] == "ready"
    assert pipeline.writer.inserts == []


def test_the_embeddings_client_is_released_after_the_background_task(
    api: TestClient, pipeline: Harness
) -> None:
    post_pdf(api)

    assert pipeline.embedder.closed == 1


# --------------------------------------------------------------------- tenant scope


def test_another_company_polling_the_id_gets_404_not_403(
    api: TestClient, pipeline: Harness
) -> None:
    # Arrange
    document_id = post_pdf(api).json()["id"]
    assert uuid.UUID(document_id) in pipeline.records.rows

    # Act
    response = api.get(f"/documents/{document_id}", headers=AS_OTHER_COMPANY)

    # Assert
    assert response.status_code == 404
    assert response.json() == {"detail": NO_SUCH_DOCUMENT_DETAIL}


def test_an_unknown_id_is_the_same_404(api: TestClient) -> None:
    response = api.get(f"/documents/{uuid.uuid4()}", headers=AS_COMPANY)

    assert response.status_code == 404
    assert response.json() == {"detail": NO_SUCH_DOCUMENT_DETAIL}


def test_a_malformed_id_is_422_from_the_path_validator(api: TestClient) -> None:
    assert api.get("/documents/not-a-uuid", headers=AS_COMPANY).status_code == 422


def test_the_list_holds_only_the_calling_company_s_documents_newest_first(
    api: TestClient,
) -> None:
    # Arrange
    first = post_pdf(api, filename="erste.pdf").json()["id"]
    second = post_pdf(api, filename="zweite.pdf").json()["id"]
    api.post(
        "/documents",
        files=pdf_part(filename="fremd.pdf"),
        data={"kind": "company_evidence"},
        headers=AS_OTHER_COMPANY,
    )

    # Act
    mine = api.get("/documents", headers=AS_COMPANY).json()
    theirs = api.get("/documents", headers=AS_OTHER_COMPANY).json()

    # Assert
    assert [document["id"] for document in mine["documents"]] == [second, first]
    assert [document["name"] for document in mine["documents"]] == ["zweite.pdf", "erste.pdf"]
    assert [document["name"] for document in theirs["documents"]] == ["fremd.pdf"]


def test_every_route_requires_the_caller_s_company(api: TestClient) -> None:
    """The dev bridge answers 401 without the header; no route is reachable anonymously."""
    assert api.post("/documents", files=pdf_part(), data={"kind": "x"}).status_code == 401
    assert api.get("/documents").status_code == 401
    assert api.get(f"/documents/{uuid.uuid4()}").status_code == 401


# ---------------------------------------------------------------------- validation


@pytest.mark.parametrize(
    ("part", "status", "detail"),
    [
        ({"filename": "angebot.docx"}, 415, NOT_PDF_SUFFIX_DETAIL),
        ({"filename": "angebot.pdf.exe"}, 415, NOT_PDF_SUFFIX_DETAIL),
        ({"content_type": "application/msword"}, 415, NOT_PDF_TYPE_DETAIL),
        ({"content": b"MZ\x90\x00 not a pdf at all"}, 415, NOT_PDF_CONTENT_DETAIL),
        ({"content": b""}, 422, EMPTY_FILE_DETAIL),
        ({"content": b"%PDF-" + b"\0" * MAX_UPLOAD_BYTES}, 413, TOO_LARGE_DETAIL),
    ],
    ids=["docx-suffix", "double-suffix", "declared-type", "magic-bytes", "empty", "oversized"],
)
def test_a_refused_upload_names_the_problem_and_writes_nothing(
    api: TestClient, pipeline: Harness, part: dict[str, Any], status: int, detail: str
) -> None:
    # Act
    response = post_pdf(api, **part)

    # Assert
    assert response.status_code == status
    assert response.json() == {"detail": detail}
    assert pipeline.records.rows == {} and pipeline.store.uploads == []


@pytest.mark.parametrize("content_type", ["application/octet-stream", "", "application/x-pdf"])
def test_a_browser_that_does_not_know_the_type_is_still_accepted(
    api: TestClient, content_type: str
) -> None:
    """The magic bytes decide; browsers send `octet-stream` for genuine PDFs often enough."""
    assert post_pdf(api, content_type=content_type).status_code == 202


def test_a_pdf_exactly_at_the_cap_is_accepted(api: TestClient) -> None:
    content = b"%PDF-" + b"\0" * (MAX_UPLOAD_BYTES - len(b"%PDF-"))
    assert len(content) == MAX_UPLOAD_BYTES
    assert post_pdf(api, content=content).status_code == 202


def test_the_suffix_check_is_case_insensitive(api: TestClient) -> None:
    assert post_pdf(api, filename="ANGEBOT.PDF").status_code == 202


def test_an_unknown_kind_is_422(api: TestClient, pipeline: Harness) -> None:
    response = api.post(
        "/documents", files=pdf_part(), data={"kind": "invoice"}, headers=AS_COMPANY
    )

    assert response.status_code == 422
    assert pipeline.records.rows == {}


def test_a_missing_file_part_is_422(api: TestClient) -> None:
    response = api.post("/documents", data={"kind": "company_evidence"}, headers=AS_COMPANY)
    assert response.status_code == 422


@pytest.mark.anyio
@pytest.mark.parametrize("filename", [None, "", "   "])
async def test_a_part_without_a_filename_is_refused(filename: str | None) -> None:
    """Reached directly: multipart clients drop a nameless part before the router sees it."""
    part = UploadFile(
        _Bytes(PDF_BYTES),
        filename=filename,
        headers=Headers({"content-type": "application/pdf"}),
    )

    with pytest.raises(HTTPException) as caught:
        await validated_upload(part, DocumentKind.COMPANY_EVIDENCE)
    assert caught.value.status_code == 422
    assert caught.value.detail == NO_FILENAME_DETAIL


class _Bytes:
    """The slice of a `SpooledTemporaryFile` that `UploadFile.read` uses."""

    def __init__(self, content: bytes) -> None:
        self._content = content
        self._position = 0

    def read(self, size: int = -1) -> bytes:
        end = len(self._content) if size < 0 else self._position + size
        chunk = self._content[self._position : end]
        self._position = end
        return chunk

    def seek(self, position: int) -> int:
        self._position = position
        return position


# ------------------------------------------------------------- the production wiring


def test_uploads_are_503_when_storage_is_not_configured(offline_settings: Settings) -> None:
    """`offline_settings` has no Supabase wiring; the detail names the problem, not the vars."""
    # Arrange -- the real `get_pipeline`, a fake pool behind `get_database`. The company
    # key resolution is stubbed: this test is about Storage being unwired, and without the
    # stub it would answer 402 for the missing key before ever reaching that.
    source = FakeConnectionSource()
    overrides: Overrides = {
        get_database: lambda: source,
        get_company_settings: lambda: offline_settings,
    }

    # Act
    with TestClient(build_app(offline_settings, overrides)) as api:
        response = post_pdf(api)

    # Assert
    assert response.status_code == 503
    assert response.json() == {"detail": STORAGE_NOT_CONFIGURED_DETAIL}
    assert "SUPABASE" not in response.text
    assert source.log == [], "nothing was written for a document that was never accepted"


@pytest.mark.anyio
async def test_get_pipeline_wires_the_real_collaborators_without_opening_a_socket(
    offline_settings: Settings,
) -> None:
    # Arrange
    settings = with_storage(offline_settings)
    source = FakeConnectionSource()
    records = InMemoryRecords()

    # Act
    built = get_pipeline(settings=settings, db=source, records=records)  # type: ignore[arg-type]

    # Assert
    assert isinstance(built, DocumentPipeline)
    assert source.borrows == 0
    await built.aclose()


def test_get_document_records_reads_through_the_pool_with_the_caller_s_scope(
    offline_settings: Settings,
) -> None:
    """The real read model over a recording fake database: the 404 comes from a scoped query."""
    # Arrange
    source = FakeConnectionSource(rows=[])
    overrides: Overrides = {get_database: lambda: source}
    document_id = uuid.uuid4()

    # Act
    with TestClient(build_app(offline_settings, overrides)) as api:
        response = api.get(f"/documents/{document_id}", headers=AS_OTHER_COMPANY)

    # Assert
    assert response.status_code == 404
    assert source.only.params == {
        "document_id": document_id,
        "company_id": uuid.UUID(OTHER_COMPANY),
    }
    assert "company_id = %(company_id)s" in source.only.sql


def test_get_document_records_builds_the_read_model_on_the_pool() -> None:
    source = FakeConnectionSource()
    assert isinstance(get_document_records(source), DocumentsReadModel)  # type: ignore[arg-type]


def test_a_failing_insert_releases_the_pipeline_and_surfaces_the_error(
    offline_settings: Settings,
) -> None:
    """Nothing is swallowed: the request fails loudly and the embeddings client is closed."""
    # Arrange
    h = harness(records=InMemoryRecords(fail_on=frozenset({"insert"})))
    overrides: Overrides = {
        get_pipeline: lambda: h.pipeline,
        get_document_records: lambda: h.records,
    }

    # Act / Assert
    with (
        TestClient(build_app(offline_settings, overrides)) as api,
        pytest.raises(ReadModelError, match="insert refused"),
    ):
        post_pdf(api)
    assert h.embedder.closed == 1
    assert h.store.uploads == []


# ------------------------------------------------------------ the viewer's signed URL

SIGNED_URL = "https://abcdefghijklmnopqrst.supabase.co/storage/v1/object/sign/x?token=T"
FROZEN_NOW = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)
TTL_SECONDS = 600


class FakeSigningStore:
    """`CompanyDocumentStore.signed_url` by shape: records the call, answers or raises."""

    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, str]] = []

    def signed_url(self, *, company_id: str, key: str) -> SignedUrl:
        self.calls.append({"company_id": company_id, "key": key})
        if self.error is not None:
            raise self.error
        return SignedUrl(
            url=SIGNED_URL,
            expires_in=TTL_SECONDS,
            expires_at=FROZEN_NOW + timedelta(seconds=TTL_SECONDS),
        )


@pytest.fixture
def signing() -> FakeSigningStore:
    return FakeSigningStore()


@pytest.fixture
def url_api(
    offline_settings: Settings, pipeline: Harness, signing: FakeSigningStore
) -> Iterator[TestClient]:
    """The router with a fake signing store beside the fake pipeline."""
    overrides: Overrides = {
        get_pipeline: lambda: pipeline.pipeline,
        get_document_records: lambda: pipeline.records,
        get_document_store: lambda: signing,
    }
    with TestClient(build_app(offline_settings, overrides)) as client:
        yield client


def test_the_url_route_signs_the_document_s_own_key_for_the_calling_company(
    url_api: TestClient, pipeline: Harness, signing: FakeSigningStore
) -> None:
    # Arrange
    document_id = post_pdf(url_api).json()["id"]
    record = pipeline.records.rows[uuid.UUID(document_id)]

    # Act
    response = url_api.get(f"/documents/{document_id}/url", headers=AS_COMPANY)

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert set(body) == set(DocumentUrlResponse.model_fields) == {"url", "expires_at"}
    assert body["url"] == SIGNED_URL
    assert datetime.fromisoformat(body["expires_at"]) == FROZEN_NOW + timedelta(
        seconds=TTL_SECONDS
    )
    assert signing.calls == [{"company_id": COMPANY, "key": record.storage_path}]


def test_another_company_asking_for_the_url_gets_404_and_nothing_is_signed(
    url_api: TestClient, signing: FakeSigningStore
) -> None:
    document_id = post_pdf(url_api).json()["id"]

    response = url_api.get(f"/documents/{document_id}/url", headers=AS_OTHER_COMPANY)

    assert response.status_code == 404
    assert response.json() == {"detail": NO_SUCH_DOCUMENT_DETAIL}
    assert signing.calls == []


def test_an_unknown_document_s_url_is_the_same_404(
    url_api: TestClient, signing: FakeSigningStore
) -> None:
    response = url_api.get(f"/documents/{uuid.uuid4()}/url", headers=AS_COMPANY)

    assert response.status_code == 404
    assert response.json() == {"detail": NO_SUCH_DOCUMENT_DETAIL}
    assert signing.calls == []


def test_a_key_storage_no_longer_has_is_404_not_500(
    offline_settings: Settings, pipeline: Harness
) -> None:
    """Storage's own "gone" arrives as `ObjectNotFoundError`; the browser sees the usual 404."""
    # Arrange
    signing = FakeSigningStore(error=ObjectNotFoundError("no such document for this company"))
    overrides: Overrides = {
        get_pipeline: lambda: pipeline.pipeline,
        get_document_records: lambda: pipeline.records,
        get_document_store: lambda: signing,
    }

    # Act
    with TestClient(build_app(offline_settings, overrides)) as api:
        document_id = post_pdf(api).json()["id"]
        response = api.get(f"/documents/{document_id}/url", headers=AS_COMPANY)

    # Assert
    assert response.status_code == 404
    assert response.json() == {"detail": NO_SUCH_DOCUMENT_DETAIL}


def test_a_signing_failure_is_502_with_a_detail_that_names_no_key(
    offline_settings: Settings, pipeline: Harness
) -> None:
    # Arrange
    signing = FakeSigningStore(error=StorageError("the document URL could not be signed"))
    overrides: Overrides = {
        get_pipeline: lambda: pipeline.pipeline,
        get_document_records: lambda: pipeline.records,
        get_document_store: lambda: signing,
    }

    # Act
    with TestClient(build_app(offline_settings, overrides)) as api:
        document_id = post_pdf(api).json()["id"]
        record = pipeline.records.rows[uuid.UUID(document_id)]
        response = api.get(f"/documents/{document_id}/url", headers=AS_COMPANY)

    # Assert
    assert response.status_code == 502
    assert response.json() == {"detail": URL_NOT_SIGNED_DETAIL}
    assert record.storage_path not in response.text
    assert COMPANY not in response.text


def test_the_url_route_requires_the_caller_s_company(url_api: TestClient) -> None:
    assert url_api.get(f"/documents/{uuid.uuid4()}/url").status_code == 401


def test_the_url_route_is_503_when_storage_is_not_configured(
    offline_settings: Settings, pipeline: Harness
) -> None:
    """The real `get_document_store` over settings with no Supabase wiring."""
    # Arrange -- the fake pipeline so a document exists; the store dependency is real
    overrides: Overrides = {
        get_pipeline: lambda: pipeline.pipeline,
        get_document_records: lambda: pipeline.records,
    }

    # Act
    with TestClient(build_app(offline_settings, overrides)) as api:
        document_id = post_pdf(api).json()["id"]
        response = api.get(f"/documents/{document_id}/url", headers=AS_COMPANY)

    # Assert
    assert response.status_code == 503
    assert response.json() == {"detail": STORAGE_NOT_CONFIGURED_DETAIL}
    assert "SUPABASE" not in response.text


def test_get_document_store_builds_the_real_store_without_opening_a_socket(
    offline_settings: Settings,
) -> None:
    built = get_document_store(settings=with_storage(offline_settings))

    assert isinstance(built, CompanyDocumentStore)


# ------------------------------------------------- the ESPD request (DUME), S2.5.1


def espd_part(
    filename: str = "DUME_acheteur.xml",
    content: bytes | None = None,
    content_type: str | None = XML_CONTENT_TYPE,
) -> dict[str, tuple[str, bytes, str | None]]:
    return {
        "file": (
            filename,
            content if content is not None else espd_request_bytes(),
            content_type,
        )
    }


def post_espd(api: TestClient, **part: Any) -> Any:
    return api.post(
        "/documents",
        files=espd_part(**part),
        data={"kind": "tender_espd_request"},
        headers=AS_COMPANY,
    )


def test_a_published_dume_is_accepted_and_stored_as_xml(
    api: TestClient, pipeline: Harness
) -> None:
    """The one non-PDF kind. The accept-list is keyed on kind, not on an exception to it."""
    # Act
    response = post_espd(api)

    # Assert
    assert response.status_code == 202
    assert response.json()["kind"] == "tender_espd_request"
    assert pipeline.store.uploads[0]["content_type"] == XML_CONTENT_TYPE
    assert pipeline.store.uploads[0]["content"] == espd_request_bytes()


@pytest.mark.parametrize(
    ("part", "status", "detail"),
    [
        ({"filename": "dume.pdf"}, 415, NOT_XML_SUFFIX_DETAIL),
        ({"content_type": "application/pdf"}, 415, NOT_XML_TYPE_DETAIL),
        ({"content": b"%PDF-1.7 really a pdf"}, 415, NOT_ESPD_CONTENT_DETAIL),
        ({"content": b"<cac:Tender/>"}, 415, NOT_ESPD_CONTENT_DETAIL),
        ({"content": b""}, 422, EMPTY_FILE_DETAIL),
        ({"content": b"<a>" + b"x" * MAX_XML_BYTES}, 413, XML_TOO_LARGE_DETAIL),
    ],
    ids=["pdf-suffix", "declared-type", "pdf-content", "not-espd", "empty", "oversized"],
)
def test_a_refused_espd_upload_names_the_problem_and_writes_nothing(
    api: TestClient, pipeline: Harness, part: dict[str, Any], status: int, detail: str
) -> None:
    # Act
    response = post_espd(api, **part)

    # Assert
    assert response.status_code == status
    assert response.json() == {"detail": detail}
    assert pipeline.records.rows == {} and pipeline.store.uploads == []


def test_a_hostile_xml_is_refused_at_the_boundary(api: TestClient, pipeline: Harness) -> None:
    """The upload route reads the file with the hardened reader, not a bare parser."""
    # Arrange
    billion_laughs = (
        b'<?xml version="1.0"?>'
        b'<!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;">]>'
        b"<lolz>&lol2;</lolz>"
    )

    # Act
    response = post_espd(api, content=billion_laughs)

    # Assert
    assert response.status_code == 415
    assert response.json() == {"detail": NOT_ESPD_CONTENT_DETAIL}
    assert pipeline.store.uploads == []


def test_an_xml_uploaded_as_a_tender_document_is_still_refused(api: TestClient) -> None:
    """The accept-list narrows per kind; it does not loosen the PDF rule for everyone."""
    # Act
    response = api.post(
        "/documents",
        files=espd_part(),
        data={"kind": "tender_document"},
        headers=AS_COMPANY,
    )

    # Assert
    assert response.status_code == 415
    assert response.json() == {"detail": NOT_PDF_SUFFIX_DETAIL}


@pytest.mark.parametrize("content_type", ["application/octet-stream", "", "text/xml"])
def test_a_client_that_declares_a_plausible_xml_type_is_accepted(
    api: TestClient, content_type: str
) -> None:
    """The root element decides, the same way the magic bytes decide for a PDF."""
    assert post_espd(api, content_type=content_type).status_code == 202


# ------------------------------------------------------------------- deleting a document


class FakeDeletingStore:
    """`CompanyDocumentStore.remove` by shape: records the call, answers or raises."""

    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.removed: list[dict[str, str]] = []

    def remove(self, *, company_id: str, key: str) -> None:
        self.removed.append({"company_id": company_id, "key": key})
        if self.error is not None:
            raise self.error


@pytest.fixture
def deleting() -> FakeDeletingStore:
    return FakeDeletingStore()


@pytest.fixture
def delete_api(
    offline_settings: Settings, pipeline: Harness, deleting: FakeDeletingStore
) -> Iterator[TestClient]:
    """The router with a fake store that records removals beside the fake pipeline."""
    overrides: Overrides = {
        get_pipeline: lambda: pipeline.pipeline,
        get_document_records: lambda: pipeline.records,
        get_document_store: lambda: deleting,
    }
    with TestClient(build_app(offline_settings, overrides)) as client:
        yield client


def attach_to_a_bid(pipeline: Harness, document_id: str, bid_count: int = 1) -> None:
    """Put the row where `POST /bids` puts it: cited by a run, so its pages are pointed at."""
    key = uuid.UUID(document_id)
    pipeline.records.rows[key] = pipeline.records.rows[key].model_copy(
        update={"bid_count": bid_count}
    )


def test_deleting_a_document_no_bid_has_claimed_removes_the_row_and_the_file(
    delete_api: TestClient, pipeline: Harness, deleting: FakeDeletingStore
) -> None:
    # Arrange
    document_id = post_pdf(delete_api).json()["id"]
    record = pipeline.records.rows[uuid.UUID(document_id)]

    # Act
    response = delete_api.delete(f"/documents/{document_id}", headers=AS_COMPANY)

    # Assert
    assert response.status_code == 204
    assert response.content == b""
    assert uuid.UUID(document_id) not in pipeline.records.rows
    assert deleting.removed == [{"company_id": COMPANY, "key": record.storage_path}]
    assert delete_api.get(f"/documents/{document_id}", headers=AS_COMPANY).status_code == 404


def test_deleting_a_document_a_bid_has_claimed_is_refused_and_keeps_it(
    delete_api: TestClient, pipeline: Harness, deleting: FakeDeletingStore
) -> None:
    # Arrange
    document_id = post_pdf(delete_api).json()["id"]
    attach_to_a_bid(pipeline, document_id)

    # Act
    response = delete_api.delete(f"/documents/{document_id}", headers=AS_COMPANY)

    # Assert
    assert response.status_code == 409
    assert response.json() == {"detail": document_in_use_detail(ORIGINAL_FILENAME, 1)}
    assert uuid.UUID(document_id) in pipeline.records.rows
    assert deleting.removed == []


def test_another_company_deleting_the_id_gets_404_and_the_row_survives(
    delete_api: TestClient, pipeline: Harness, deleting: FakeDeletingStore
) -> None:
    # Arrange
    document_id = post_pdf(delete_api).json()["id"]

    # Act
    response = delete_api.delete(f"/documents/{document_id}", headers=AS_OTHER_COMPANY)

    # Assert
    assert response.status_code == 404
    assert response.json() == {"detail": NO_SUCH_DOCUMENT_DETAIL}
    assert uuid.UUID(document_id) in pipeline.records.rows
    assert deleting.removed == []


def test_deleting_an_unknown_id_is_the_same_404(delete_api: TestClient) -> None:
    response = delete_api.delete(f"/documents/{uuid.uuid4()}", headers=AS_COMPANY)

    assert response.status_code == 404
    assert response.json() == {"detail": NO_SUCH_DOCUMENT_DETAIL}


def test_a_file_storage_has_already_lost_still_deletes_the_row(
    offline_settings: Settings, pipeline: Harness
) -> None:
    # Arrange -- the blob is gone; the row must not be stranded because of it.
    gone = FakeDeletingStore(error=ObjectNotFoundError("no such object"))
    overrides: Overrides = {
        get_pipeline: lambda: pipeline.pipeline,
        get_document_records: lambda: pipeline.records,
        get_document_store: lambda: gone,
    }
    with TestClient(build_app(offline_settings, overrides)) as api:
        document_id = post_pdf(api).json()["id"]

        # Act
        response = api.delete(f"/documents/{document_id}", headers=AS_COMPANY)

        # Assert
        assert response.status_code == 204
        assert uuid.UUID(document_id) not in pipeline.records.rows


def test_a_storage_failure_leaves_the_row_in_place_rather_than_stranding_the_file(
    offline_settings: Settings, pipeline: Harness
) -> None:
    # Arrange
    broken = FakeDeletingStore(error=StorageError("storage is down"))
    overrides: Overrides = {
        get_pipeline: lambda: pipeline.pipeline,
        get_document_records: lambda: pipeline.records,
        get_document_store: lambda: broken,
    }
    with TestClient(build_app(offline_settings, overrides)) as api:
        document_id = post_pdf(api).json()["id"]

        # Act
        response = api.delete(f"/documents/{document_id}", headers=AS_COMPANY)

        # Assert
        assert response.status_code == 502
        assert response.json() == {"detail": NOT_DELETED_DETAIL}
        assert uuid.UUID(document_id) in pipeline.records.rows


# ------------------------------------------------------------------- M13: paging


def test_the_document_list_pages_and_hands_back_a_cursor(api: TestClient) -> None:
    """M13. The list had no limit at all, then a silent 500-row cap."""
    # Arrange
    for name in ("eins.pdf", "zwei.pdf", "drei.pdf"):
        post_pdf(api, filename=name)

    # Act
    page = api.get("/documents", params={"limit": 2}, headers=AS_COMPANY).json()

    # Assert
    assert [document["name"] for document in page["documents"]] == ["drei.pdf", "zwei.pdf"]
    assert page["next_cursor"] is not None


def test_following_the_cursor_gives_the_rest_and_never_repeats_a_row(api: TestClient) -> None:
    # Arrange
    names = ("eins.pdf", "zwei.pdf", "drei.pdf", "vier.pdf", "fuenf.pdf")
    for name in names:
        post_pdf(api, filename=name)

    # Act
    seen: list[str] = []
    cursor: str | None = None
    for _ in range(3):
        params = {"limit": 2} | ({"cursor": cursor} if cursor else {})
        page = api.get("/documents", params=params, headers=AS_COMPANY).json()
        seen.extend(document["name"] for document in page["documents"])
        cursor = page["next_cursor"]

    # Assert
    assert sorted(seen) == sorted(names)
    assert cursor is None


def test_an_upload_between_two_pages_does_not_shift_the_boundary(api: TestClient) -> None:
    """The reason this is a cursor and not an offset — and on `documents` the insert at the
    head is the bidder's own next upload, so it happens on the screen they are looking at."""
    # Arrange
    for name in ("eins.pdf", "zwei.pdf", "drei.pdf", "vier.pdf"):
        post_pdf(api, filename=name)
    first = api.get("/documents", params={"limit": 2}, headers=AS_COMPANY).json()

    # Act
    post_pdf(api, filename="neu.pdf")
    second = api.get(
        "/documents", params={"limit": 2, "cursor": first["next_cursor"]}, headers=AS_COMPANY
    ).json()

    # Assert
    page_one = {document["id"] for document in first["documents"]}
    page_two = {document["id"] for document in second["documents"]}
    assert page_one & page_two == set()
    assert len(page_two) == 2


def test_a_cursor_this_api_did_not_issue_is_422_and_is_not_echoed(api: TestClient) -> None:
    # Act
    response = api.get(
        "/documents", params={"cursor": "<script>alert(1)</script>"}, headers=AS_COMPANY
    )

    # Assert
    assert response.status_code == 422
    assert "script" not in response.text


def test_a_document_limit_past_the_ceiling_is_refused(api: TestClient) -> None:
    assert api.get("/documents", params={"limit": 5000}, headers=AS_COMPANY).status_code == 422


def test_a_page_of_documents_holds_only_the_calling_company_s_rows(api: TestClient) -> None:
    """The cursor must not become a way around the tenant scope: the predicate sits beside
    `company_id`, never instead of it. Both pages are asked for while another company's
    document sits between them in insertion order."""
    # Arrange
    post_pdf(api, filename="meins-eins.pdf")
    api.post(
        "/documents",
        files=pdf_part(filename="fremd.pdf"),
        data={"kind": "company_evidence"},
        headers=AS_OTHER_COMPANY,
    )
    post_pdf(api, filename="meins-zwei.pdf")
    first = api.get("/documents", params={"limit": 1}, headers=AS_COMPANY).json()

    # Act
    after = api.get(
        "/documents",
        params={"limit": 50, "cursor": first["next_cursor"]},
        headers=AS_COMPANY,
    ).json()

    # Assert
    assert [document["name"] for document in first["documents"]] == ["meins-zwei.pdf"]
    assert [document["name"] for document in after["documents"]] == ["meins-eins.pdf"]
