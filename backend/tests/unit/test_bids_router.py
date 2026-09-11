"""S3.1.1 — `POST /bids`, `GET /bids/{id}`, `GET /bids` over an in-memory read model.

Offline. The router is mounted on a bare app whose `state.settings` is the offline settings
(what `current_company` reads), the database dependency is a stand-in that is never
borrowed from, the runner is a recorder, and every read-model function the router calls is
replaced by one method of `InMemoryReadModel`. Nothing here depends on `crossbid.main`
registering the router, so the tests hold whether or not the lifespan has wired it yet.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from crossbid.agent.state import ExtractionProblem, ExtractionProblemReason
from crossbid.auth import DEV_COMPANY_HEADER
from crossbid.ingestion.storage import StorageError
from crossbid.main import get_database
from crossbid.models.matrix import MatrixRow, RowStatus
from crossbid.models.requirement import (
    Checkability,
    Requirement,
    RequirementCategory,
    RequirementKind,
    RequirementStage,
)
from crossbid.models.tender import BidStatus, DocumentKind
from crossbid.readmodel.bids import BidDocumentRow, BidRow, BidStateError, thread_id_of
from crossbid.readmodel.documents import DocumentStatus
from crossbid.routers import bids as bids_router
from crossbid.routers.bids import (
    NO_SUCH_BID_DETAIL,
    NO_SUCH_COMPANY_DETAIL,
    RUNNER_STATE_KEY,
    STORAGE_NOT_CONFIGURED_DETAIL,
    BidDocumentResponse,
    BidListResponse,
    BidResponse,
    StartBidRequest,
    get_bid_runner,
    router,
)
from crossbid.settings import Settings

COMPANY_ID = str(uuid.uuid4())
OTHER_COMPANY_ID = str(uuid.uuid4())
NOTICE = "614251-2026"
NOW = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)

READ_MODEL_FUNCTIONS = (
    "company_language",
    "documents_by_id",
    "create_bid",
    "attach_documents",
    "mark_bid_failed",
    "fetch_bid",
    "list_bids",
    "fetch_requirements",
    "fetch_matrix_rows",
    "bid_documents",
)


# --------------------------------------------------------------------------------- fakes


def document_row(
    *,
    owner: str = COMPANY_ID,
    kind: DocumentKind = DocumentKind.TENDER_DOCUMENT,
    status: DocumentStatus = DocumentStatus.READY,
    bid_id: str | None = None,
    name: str = "Bewerbungsbedingungen.pdf",
) -> tuple[str, BidDocumentRow]:
    row = BidDocumentRow(
        id=str(uuid.uuid4()),
        name=name,
        storage_path=f"{owner}/doc/{name}",
        kind=kind,
        status=status,
        bid_id=bid_id,
        pages=12,
        unread_pages=(3,),
    )
    return owner, row


def requirement(bid_id: str) -> Requirement:
    return Requirement(
        id=str(uuid.uuid4()),
        bid_id=bid_id,
        category=RequirementCategory.ECONOMIC_FINANCIAL,
        kind=RequirementKind.MANDATORY,
        stage=RequirementStage.BID_ELIGIBILITY,
        checkable=Checkability.COMPANY_PROPERTY,
        source_text="Der Umsatz muss mindestens 3.000.000,00 EUR pro Jahr betragen.",
        source_lang="de",
        document_name="Bewerbungsbedingungen.pdf",
        page=4,
        translation="Mindestumsatz von 3.000.000,00 EUR pro Jahr.",
    )


class InMemoryReadModel:
    """The nine read-model functions the router calls, over dicts, scoped like the real ones."""

    def __init__(self) -> None:
        self.companies: dict[str, str] = {COMPANY_ID: "de", OTHER_COMPANY_ID: "fr"}
        self.documents: dict[str, tuple[str, BidDocumentRow]] = {}
        self.bids: dict[str, BidRow] = {}
        self.requirements: dict[str, list[Requirement]] = {}
        self.matrix_rows: dict[str, list[MatrixRow]] = {}
        self.attach_error: BidStateError | None = None
        self.attached: list[tuple[str, list[str]]] = []
        self.failed: list[tuple[str, str]] = []

    def add_document(self, owner: str, row: BidDocumentRow) -> BidDocumentRow:
        self.documents[row.id] = (owner, row)
        return row

    def add_bid(self, **overrides: Any) -> BidRow:
        bid_id = str(uuid.uuid4())
        values: dict[str, Any] = {
            "id": bid_id,
            "company_id": COMPANY_ID,
            "thread_id": thread_id_of(bid_id),
            "notice_number": NOTICE,
            "title": "Netztechnik",
            "source_language": "de",
            "bidder_language": "de",
            "status": BidStatus.QUEUED,
            "created_at": NOW,
            "updated_at": NOW,
        }
        row = BidRow(**(values | overrides))
        self.bids[row.id] = row
        return row

    # -- the functions, with the real signatures ------------------------------------

    async def company_language(self, db: Any, *, company_id: str) -> str | None:
        return self.companies.get(company_id)

    async def documents_by_id(
        self, db: Any, *, company_id: str, document_ids: Sequence[str]
    ) -> list[BidDocumentRow]:
        return [
            row
            for identifier in document_ids
            for owner, row in [self.documents.get(identifier, ("", None))]
            if row is not None and owner == company_id
        ]

    async def create_bid(
        self,
        db: Any,
        *,
        company_id: str,
        notice_number: str,
        title: str,
        source_language: str,
        bidder_language: str,
    ) -> BidRow:
        return self.add_bid(
            company_id=company_id,
            notice_number=notice_number,
            title=title,
            source_language=source_language,
            bidder_language=bidder_language,
        )

    async def attach_documents(
        self, db: Any, *, company_id: str, bid_id: str, document_ids: Sequence[str]
    ) -> None:
        if self.attach_error is not None:
            raise self.attach_error
        self.attached.append((bid_id, list(document_ids)))
        for identifier in document_ids:
            owner, row = self.documents[identifier]
            self.documents[identifier] = (owner, row.model_copy(update={"bid_id": bid_id}))

    async def mark_bid_failed(
        self, db: Any, *, company_id: str, bid_id: str, reason: str
    ) -> None:
        self.failed.append((bid_id, reason))
        self.bids[bid_id] = self.bids[bid_id].model_copy(
            update={"status": BidStatus.FAILED, "failure_reason": reason}
        )

    async def fetch_bid(self, db: Any, *, company_id: str, bid_id: str) -> BidRow | None:
        row = self.bids.get(bid_id)
        return row if row is not None and row.company_id == company_id else None

    async def list_bids(self, db: Any, *, company_id: str) -> list[BidRow]:
        return [row for row in self.bids.values() if row.company_id == company_id]

    async def fetch_requirements(
        self, db: Any, *, company_id: str, bid_id: str
    ) -> list[Requirement]:
        return list(self.requirements.get(bid_id, []))

    async def fetch_matrix_rows(
        self, db: Any, *, company_id: str, bid_id: str
    ) -> list[MatrixRow]:
        return list(self.matrix_rows.get(bid_id, []))

    async def bid_documents(
        self, db: Any, *, company_id: str, bid_id: str
    ) -> list[BidDocumentRow]:
        return [
            row
            for owner, row in self.documents.values()
            if owner == company_id and row.bid_id == bid_id
        ]


class FakeRunner:
    def __init__(self, *, storage_missing: bool = False) -> None:
        self.started: list[BidRow] = []
        self._storage_missing = storage_missing

    @property
    def graph(self) -> object:
        if self._storage_missing:
            raise StorageError("SUPABASE_URL is not set")
        return object()

    def start(self, bid: BidRow) -> None:
        self.started.append(bid)


class FakeDatabase:
    """Handed to the read-model functions, which are fakes here; never borrowed from."""


# ------------------------------------------------------------------------------ fixtures


@pytest.fixture
def read_model(monkeypatch: pytest.MonkeyPatch) -> InMemoryReadModel:
    store = InMemoryReadModel()
    for name in READ_MODEL_FUNCTIONS:
        monkeypatch.setattr(bids_router, name, getattr(store, name))
    return store


@pytest.fixture
def runner() -> FakeRunner:
    return FakeRunner()


@pytest.fixture
def client(offline_settings: Settings, runner: FakeRunner) -> Iterator[TestClient]:
    app = FastAPI()
    app.state.settings = offline_settings
    app.state.db = None
    app.include_router(router)
    app.dependency_overrides[get_database] = lambda: FakeDatabase()
    app.dependency_overrides[get_bid_runner] = lambda: runner
    with TestClient(app) as test_client:
        yield test_client


def headers(company_id: str = COMPANY_ID) -> dict[str, str]:
    return {DEV_COMPANY_HEADER: company_id}


def start_body(*document_ids: str, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "notice_number": NOTICE,
        "document_ids": list(document_ids),
        "source_language": "de",
    }
    return body | overrides


# ---------------------------------------------------------------------------- POST /bids


def test_post_bids_answers_202_with_an_id_and_queued(
    client: TestClient, read_model: InMemoryReadModel, runner: FakeRunner
) -> None:
    # Arrange
    row = read_model.add_document(*document_row())

    # Act
    response = client.post("/bids", json=start_body(row.id), headers=headers())

    # Assert -- the row, the attach, the background start, and the polling shape
    assert response.status_code == 202, response.text
    body = response.json()
    bid_id = str(uuid.UUID(body["id"]))
    assert body["status"] == "queued"
    assert body["notice_number"] == NOTICE
    assert body["title"] == NOTICE, "the title defaults to the notice number"
    assert body["source_language"] == "de"
    assert body["bidder_language"] == "de"
    assert body["requirements"] == []
    assert body["problems"] == []
    assert body["failure_reason"] is None
    assert body["documents"] == [
        {"id": row.id, "name": row.name, "pages": 12, "unread_pages": [3]}
    ]
    assert read_model.attached == [(bid_id, [row.id])]
    assert [bid.id for bid in runner.started] == [bid_id]
    assert read_model.bids[bid_id].thread_id == f"bid:{bid_id}"


def test_post_bids_keeps_a_title_and_trims_the_fields(
    client: TestClient, read_model: InMemoryReadModel
) -> None:
    row = read_model.add_document(*document_row())

    response = client.post(
        "/bids",
        json=start_body(row.id, title="  Netztechnik BMI  ", source_language=" de "),
        headers=headers(),
    )

    assert response.status_code == 202
    assert response.json()["title"] == "Netztechnik BMI"
    assert response.json()["source_language"] == "de"


def test_duplicate_document_ids_count_once(
    client: TestClient, read_model: InMemoryReadModel
) -> None:
    row = read_model.add_document(*document_row())

    response = client.post("/bids", json=start_body(row.id, row.id), headers=headers())

    assert response.status_code == 202
    assert read_model.attached[0][1] == [row.id]


def test_a_document_of_another_company_is_404_naming_the_id(
    client: TestClient, read_model: InMemoryReadModel, runner: FakeRunner
) -> None:
    """Not 403: a "forbidden" would confirm that the document exists."""
    mine = read_model.add_document(*document_row())
    theirs = read_model.add_document(*document_row(owner=OTHER_COMPANY_ID))

    response = client.post("/bids", json=start_body(mine.id, theirs.id), headers=headers())

    assert response.status_code == 404
    assert theirs.id in response.json()["detail"]
    assert mine.id not in response.json()["detail"]
    assert read_model.bids == {}
    assert runner.started == []


def test_an_unknown_document_id_is_404(
    client: TestClient, read_model: InMemoryReadModel
) -> None:
    unknown = str(uuid.uuid4())

    response = client.post("/bids", json=start_body(unknown), headers=headers())

    assert response.status_code == 404
    assert unknown in response.json()["detail"]


@pytest.mark.parametrize(
    "status",
    [
        DocumentStatus.UPLOADED,
        DocumentStatus.PARSED,
        DocumentStatus.EMBEDDED,
        DocumentStatus.FAILED,
    ],
)
def test_a_document_that_is_not_ready_is_409_naming_the_file_and_its_status(
    client: TestClient, read_model: InMemoryReadModel, status: DocumentStatus
) -> None:
    row = read_model.add_document(*document_row(status=status, name="Anlage_3.pdf"))

    response = client.post("/bids", json=start_body(row.id), headers=headers())

    assert response.status_code == 409
    assert response.json()["detail"] == f"Document Anlage_3.pdf is {status.value}, not ready."
    assert read_model.bids == {}


def test_company_evidence_is_422(client: TestClient, read_model: InMemoryReadModel) -> None:
    row = read_model.add_document(
        *document_row(kind=DocumentKind.COMPANY_EVIDENCE, name="ISO27001.pdf")
    )

    response = client.post("/bids", json=start_body(row.id), headers=headers())

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Document ISO27001.pdf is company evidence, not a tender document."
    )


def test_a_tender_notice_may_start_a_bid(
    client: TestClient, read_model: InMemoryReadModel
) -> None:
    row = read_model.add_document(*document_row(kind=DocumentKind.TENDER_NOTICE))

    response = client.post("/bids", json=start_body(row.id), headers=headers())

    assert response.status_code == 202


def test_a_document_already_attached_to_another_bid_is_409(
    client: TestClient, read_model: InMemoryReadModel
) -> None:
    row = read_model.add_document(*document_row(bid_id=str(uuid.uuid4()), name="RC.pdf"))

    response = client.post("/bids", json=start_body(row.id), headers=headers())

    assert response.status_code == 409
    assert response.json()["detail"] == "Document RC.pdf already belongs to another bid."


def test_an_unknown_company_is_404(client: TestClient, read_model: InMemoryReadModel) -> None:
    """`AUTH_MODE=dev` believes the header; a UUID with no company row must still fail
    readably rather than as a foreign-key error."""
    row = read_model.add_document(*document_row(owner=str(uuid.uuid4())))

    response = client.post("/bids", json=start_body(row.id), headers=headers(str(uuid.uuid4())))

    assert response.status_code == 404
    assert response.json()["detail"] == NO_SUCH_COMPANY_DETAIL


def test_storage_not_configured_is_503_and_creates_no_bid(
    client: TestClient, read_model: InMemoryReadModel, runner: FakeRunner
) -> None:
    runner._storage_missing = True
    row = read_model.add_document(*document_row())

    response = client.post("/bids", json=start_body(row.id), headers=headers())

    assert response.status_code == 503
    assert response.json()["detail"] == STORAGE_NOT_CONFIGURED_DETAIL
    assert read_model.bids == {}
    assert runner.started == []


def test_a_lost_attach_race_marks_the_bid_failed_and_answers_409(
    client: TestClient, read_model: InMemoryReadModel, runner: FakeRunner
) -> None:
    """The row exists by then; leaving it `queued` would be a bid that never runs."""
    row = read_model.add_document(*document_row())
    read_model.attach_error = BidStateError("only 0 of 1 documents could be attached")

    response = client.post("/bids", json=start_body(row.id), headers=headers())

    assert response.status_code == 409
    assert response.json()["detail"] == "only 0 of 1 documents could be attached"
    [(bid_id, reason)] = read_model.failed
    assert reason == "attaching documents failed: BidStateError"
    assert read_model.bids[bid_id].status is BidStatus.FAILED
    assert runner.started == []


@pytest.mark.parametrize(
    "body",
    [
        {"notice_number": NOTICE, "document_ids": [], "source_language": "de"},
        {"notice_number": "", "document_ids": [str(uuid.uuid4())], "source_language": "de"},
        {"notice_number": NOTICE, "document_ids": [str(uuid.uuid4())], "source_language": "d"},
        {"notice_number": NOTICE, "document_ids": ["not-a-uuid"], "source_language": "de"},
        {"notice_number": NOTICE, "document_ids": [str(uuid.uuid4())]},
    ],
)
def test_an_invalid_body_is_422_before_anything_is_read(
    client: TestClient, read_model: InMemoryReadModel, body: dict[str, Any]
) -> None:
    response = client.post("/bids", json=body, headers=headers())

    assert response.status_code == 422
    assert read_model.bids == {}


def test_post_bids_without_the_dev_header_is_401(
    client: TestClient, read_model: InMemoryReadModel
) -> None:
    response = client.post("/bids", json=start_body(str(uuid.uuid4())))

    assert response.status_code == 401


# ------------------------------------------------------------------------ GET /bids/{id}


def test_get_bid_returns_the_polling_shape(
    client: TestClient, read_model: InMemoryReadModel
) -> None:
    problem = ExtractionProblem(
        reason=ExtractionProblemReason.UNREADABLE_DOCUMENT,
        document_name="Anlage_7.pdf",
        pages=(1, 2),
    )
    bid = read_model.add_bid(
        status=BidStatus.AWAITING_REVIEW, problems=[problem.model_dump(mode="json")]
    )
    rows = [requirement(bid.id)]
    read_model.requirements[bid.id] = rows
    matrix = [
        MatrixRow(
            id=str(uuid.uuid4()),
            requirement_id=rows[0].id,
            status=RowStatus.PARTIALLY_SUPPORTED,
            agent_rationale="Kein Nachweis im Bestand gefunden.",
        )
    ]
    read_model.matrix_rows[bid.id] = matrix
    document = read_model.add_document(*document_row(bid_id=bid.id))

    # Act
    response = client.get(f"/bids/{bid.id}", headers=headers())

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == bid.id
    assert body["status"] == "awaiting_review"
    assert body["failure_reason"] is None
    assert body["requirements"] == [rows[0].model_dump(mode="json")]
    assert body["matrix_rows"] == [matrix[0].model_dump(mode="json")]
    assert body["problems"] == [problem.model_dump(mode="json")]
    assert body["documents"] == [
        {"id": document.id, "name": document.name, "pages": 12, "unread_pages": [3]}
    ]
    assert body["created_at"] == "2026-09-11T12:00:00Z"
    assert set(body) == set(BidResponse.model_fields)


def test_get_bid_shows_a_failed_run_with_its_reason(
    client: TestClient, read_model: InMemoryReadModel
) -> None:
    bid = read_model.add_bid(
        status=BidStatus.FAILED, failure_reason="parsing failed: DocumentFetchError"
    )

    response = client.get(f"/bids/{bid.id}", headers=headers())

    assert response.json()["status"] == "failed"
    assert response.json()["failure_reason"] == "parsing failed: DocumentFetchError"


def test_another_companys_bid_is_404(client: TestClient, read_model: InMemoryReadModel) -> None:
    bid = read_model.add_bid(company_id=OTHER_COMPANY_ID)

    response = client.get(f"/bids/{bid.id}", headers=headers())

    assert response.status_code == 404
    assert response.json()["detail"] == NO_SUCH_BID_DETAIL


def test_an_unknown_bid_is_404_and_a_malformed_id_is_422(
    client: TestClient, read_model: InMemoryReadModel
) -> None:
    assert client.get(f"/bids/{uuid.uuid4()}", headers=headers()).status_code == 404
    assert client.get("/bids/not-a-uuid", headers=headers()).status_code == 422


# ------------------------------------------------------------------------------ GET /bids


def test_list_bids_returns_summaries_for_the_calling_company_only(
    client: TestClient, read_model: InMemoryReadModel
) -> None:
    mine = read_model.add_bid(status=BidStatus.EXTRACTING)
    read_model.add_bid(company_id=OTHER_COMPANY_ID)

    response = client.get("/bids", headers=headers())

    assert response.status_code == 200
    [summary] = response.json()["bids"]
    assert summary["id"] == mine.id
    assert summary["status"] == "extracting"
    assert summary["ted_publication_number"] == NOTICE
    assert summary["decision"] is None


def test_list_bids_without_the_dev_header_is_401(
    client: TestClient, read_model: InMemoryReadModel
) -> None:
    assert client.get("/bids").status_code == 401


# ------------------------------------------------------------------------- the runner dep


def test_get_bid_runner_builds_one_runner_and_keeps_it_on_app_state(
    offline_settings: Settings,
) -> None:
    """Startup (`resume_unfinished_runs`) and requests must share one task registry."""
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))

    first = get_bid_runner(request, FakeDatabase(), offline_settings)  # type: ignore[arg-type]
    second = get_bid_runner(request, FakeDatabase(), offline_settings)  # type: ignore[arg-type]

    assert first is second
    assert getattr(request.app.state, RUNNER_STATE_KEY) is first


def test_get_bid_runner_returns_the_runner_the_lifespan_stored(
    offline_settings: Settings, runner: FakeRunner
) -> None:
    state = SimpleNamespace(**{RUNNER_STATE_KEY: runner})
    request = SimpleNamespace(app=SimpleNamespace(state=state))

    found = get_bid_runner(request, FakeDatabase(), offline_settings)  # type: ignore[arg-type]

    assert found is runner


# ------------------------------------------------------------------------ the contract


@pytest.mark.parametrize(
    "model", [StartBidRequest, BidResponse, BidDocumentResponse, BidListResponse]
)
def test_every_field_of_the_contract_carries_a_description(model: type[BaseModel]) -> None:
    """`frontend/lib/api.ts` is generated from this schema; a field without a description is
    a field the frontend developer has to guess at."""
    undescribed = [name for name, field in model.model_fields.items() if not field.description]
    assert undescribed == []
