"""S3.1.1 — `POST /bids`, `GET /bids/{id}`, `GET /bids` over an in-memory read model.

Offline. The router is mounted on a bare app whose `state.settings` is the offline settings
(what `current_company` reads), the database dependency is a stand-in that is never
borrowed from, the runner is a recorder, and every read-model function the router calls is
replaced by one method of `InMemoryReadModel`. Nothing here depends on `crossbid.main`
registering the router, so the tests hold whether or not the lifespan has wired it yet.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from crossbid.agent.runner import RunnerError
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
from crossbid.models.review import ReviewSubmission
from crossbid.models.tender import BidStatus, DocumentKind
from crossbid.models.verdict import Decision, Gap, GapSeverity, Verdict
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
    "claim_bid_for_review",
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
        self.claimed: list[str] = []
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
        buyer: str | None = None,
        deadline: datetime | None = None,
        deadline_utc_offset_minutes: int | None = None,
    ) -> BidRow:
        return self.add_bid(
            company_id=company_id,
            notice_number=notice_number,
            title=title,
            source_language=source_language,
            bidder_language=bidder_language,
            buyer=buyer,
            deadline=deadline,
            deadline_utc_offset_minutes=deadline_utc_offset_minutes,
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

    async def claim_bid_for_review(self, db: Any, *, company_id: str, bid_id: str) -> None:
        """The real one is a conditional update; this is the same condition, in a dict."""
        row = self.bids.get(bid_id)
        if row is None or row.status is not BidStatus.AWAITING_REVIEW:
            raise BidStateError(f"bid {bid_id} is not waiting for a review")
        self.claimed.append(bid_id)
        self.bids[bid_id] = row.model_copy(update={"status": BidStatus.APPLYING_REVIEW})

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
        self.reviewed: list[tuple[BidRow, ReviewSubmission]] = []
        self.review_error: Exception | None = None
        self.on_review: Callable[[BidRow], None] | None = None
        self._storage_missing = storage_missing

    @property
    def graph(self) -> object:
        if self._storage_missing:
            raise StorageError("SUPABASE_URL is not set")
        return object()

    def start(self, bid: BidRow) -> None:
        self.started.append(bid)

    async def submit_review(self, bid: BidRow, review: ReviewSubmission) -> None:
        if self.review_error is not None:
            raise self.review_error
        self.reviewed.append((bid, review))
        if self.on_review is not None:
            self.on_review(bid)


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


def test_get_bid_carries_the_agents_verdict_once_it_has_been_scored(
    client: TestClient, read_model: InMemoryReadModel
) -> None:
    # Arrange
    verdict = Verdict(
        decision=Decision.NO_GO,
        gaps=(
            Gap(
                requirement_id="TECH-06",
                severity=GapSeverity.BLOCKING,
                summary="Zu wenige Fachkräfte",
                required="29 FTE",
                actual="21 FTE",
            ),
        ),
        rationale="Dieses Angebot wird nicht empfohlen.",
        mandatory_total=21,
        mandatory_supported=19,
        partially_supported_rows=0,
    )
    bid = read_model.add_bid(
        status=BidStatus.AWAITING_REVIEW, verdict=verdict.model_dump(mode="json")
    )

    # Act
    response = client.get(f"/bids/{bid.id}", headers=headers())

    # Assert
    assert response.status_code == 200
    assert response.json()["verdict"] == verdict.model_dump(mode="json")


def test_get_bid_has_no_verdict_before_scoring_has_run(
    client: TestClient, read_model: InMemoryReadModel
) -> None:
    bid = read_model.add_bid(status=BidStatus.CHECKING)

    assert client.get(f"/bids/{bid.id}", headers=headers()).json()["verdict"] is None


def test_a_stored_verdict_the_contract_no_longer_recognises_is_omitted_not_a_500(
    client: TestClient, read_model: InMemoryReadModel, caplog: pytest.LogCaptureFixture
) -> None:
    """The column is a projection and the checkpoint is the authority (S3.4.3). A bid whose
    verdict predates a vocabulary change must still open, so its reviewer can re-run it."""
    # Arrange
    bid = read_model.add_bid(
        status=BidStatus.AWAITING_REVIEW, verdict={"decision": "go_with_open_items"}
    )

    # Act
    with caplog.at_level(logging.WARNING, logger="crossbid.routers.bids"):
        response = client.get(f"/bids/{bid.id}", headers=headers())

    # Assert
    assert response.status_code == 200
    assert response.json()["verdict"] is None
    assert "no longer validates" in caplog.text


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


def test_list_bids_shows_the_final_decision_once_a_reviewer_has_given_one(
    client: TestClient, read_model: InMemoryReadModel
) -> None:
    """S3.4.3: the dashboard reads the decision out of the `bids` projection and nothing
    else -- no checkpoint, no join onto `reviews`."""
    # Arrange
    read_model.add_bid(status=BidStatus.COMPLETE, reviewed_decision=Decision.CONDITIONAL)
    read_model.add_bid(
        status=BidStatus.AWAITING_REVIEW, verdict=AGENT_VERDICT.model_dump(mode="json")
    )
    read_model.add_bid(status=BidStatus.CHECKING)

    # Act
    body = client.get("/bids", headers=headers()).json()

    # Assert -- reviewed shows the human's call, parked shows the agent's, running shows none
    assert sorted(bid["decision"] or "none" for bid in body["bids"]) == [
        "conditional",
        "no_go",
        "none",
    ]


def test_listing_bids_never_touches_the_graph(
    client: TestClient, read_model: InMemoryReadModel, runner: FakeRunner
) -> None:
    """ "`GET /bids` reads only from the read model" is the story's criterion, and a runner
    whose graph cannot be built is how it is made checkable: a list that reached for a
    checkpoint would raise here."""
    # Arrange
    read_model.add_bid(status=BidStatus.COMPLETE, reviewed_decision=Decision.GO)
    runner._storage_missing = True

    # Act / Assert
    assert client.get("/bids", headers=headers()).status_code == 200


def test_list_bids_without_the_dev_header_is_401(
    client: TestClient, read_model: InMemoryReadModel
) -> None:
    assert client.get("/bids").status_code == 401


# ------------------------------------------------------------------------- the runner dep


def test_get_bid_runner_builds_one_runner_and_keeps_it_on_app_state(
    offline_settings: Settings,
) -> None:
    """Startup (`resume_unfinished_runs`) and requests must share one task registry.

    The runner is built over `settings_provider(request.app)`, which reads `app.state.settings`
    -- the seam S4.6.2's write route replaces -- so the fake state carries them."""
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(settings=offline_settings))
    )

    first = get_bid_runner(request, FakeDatabase())  # type: ignore[arg-type]
    second = get_bid_runner(request, FakeDatabase())  # type: ignore[arg-type]

    assert first is second
    assert getattr(request.app.state, RUNNER_STATE_KEY) is first


def test_get_bid_runner_returns_the_runner_the_lifespan_stored(
    offline_settings: Settings, runner: FakeRunner
) -> None:
    state = SimpleNamespace(**{RUNNER_STATE_KEY: runner, "settings": offline_settings})
    request = SimpleNamespace(app=SimpleNamespace(state=state))

    found = get_bid_runner(request, FakeDatabase())  # type: ignore[arg-type]

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


# ------------------------------------------------------------------ POST /bids/{id}/review


AGENT_VERDICT = Verdict(
    decision=Decision.NO_GO,
    gaps=(Gap(requirement_id="a", severity=GapSeverity.BLOCKING, summary="Personal"),),
    rationale="Dieses Angebot wird nicht empfohlen.",
    mandatory_total=2,
    mandatory_supported=1,
    partially_supported_rows=0,
)


def parked_bid(read_model: InMemoryReadModel, **overrides: Any) -> tuple[BidRow, MatrixRow]:
    """A bid waiting at its interrupt, with one matrix row a reviewer could edit."""
    bid = read_model.add_bid(
        status=BidStatus.AWAITING_REVIEW,
        verdict=AGENT_VERDICT.model_dump(mode="json"),
        **overrides,
    )
    rows = [requirement(bid.id)]
    read_model.requirements[bid.id] = rows
    row = MatrixRow(
        id=str(uuid.uuid4()),
        requirement_id=rows[0].id,
        status=RowStatus.UNSUPPORTED,
        agent_rationale="Kein Nachweis im Bestand gefunden.",
    )
    read_model.matrix_rows[bid.id] = [row]
    return bid, row


def review_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"decision": "no_go"}
    return body | overrides


def test_submitting_a_review_claims_the_bid_and_resumes_the_run(
    client: TestClient, read_model: InMemoryReadModel, runner: FakeRunner
) -> None:
    # Arrange
    bid, row = parked_bid(read_model)
    body = review_body(
        row_edits=[
            {
                "matrix_row_id": row.id,
                "status": "not_applicable",
                "override_reason": "Gilt nur für Bietergemeinschaften.",
            }
        ]
    )

    # Act
    response = client.post(f"/bids/{bid.id}/review", json=body, headers=headers())

    # Assert
    assert response.status_code == 200
    assert read_model.claimed == [bid.id]
    submitted = runner.reviewed[0][1]
    assert submitted.decision is Decision.NO_GO
    assert submitted.row_edits[0].matrix_row_id == row.id


def test_the_response_shows_the_bid_as_the_review_left_it_not_as_it_was(
    client: TestClient, read_model: InMemoryReadModel, runner: FakeRunner
) -> None:
    """The reviewer clicked confirm; answering with the state they were leaving would be
    the one thing the response must not do."""
    # Arrange
    bid, _row = parked_bid(read_model)
    runner.on_review = lambda done: read_model.bids.__setitem__(
        done.id,
        read_model.bids[done.id].model_copy(
            update={"status": BidStatus.COMPLETE, "reviewed_decision": Decision.NO_GO}
        ),
    )

    # Act
    body = client.post(f"/bids/{bid.id}/review", json=review_body(), headers=headers()).json()

    # Assert
    assert body["status"] == "complete"


def test_a_second_submission_is_a_conflict(
    client: TestClient, read_model: InMemoryReadModel, runner: FakeRunner
) -> None:
    """The story's criterion. The claim is a conditional update, so the second caller loses
    it however close together the two arrive."""
    # Arrange
    bid, _row = parked_bid(read_model)

    # Act
    first = client.post(f"/bids/{bid.id}/review", json=review_body(), headers=headers())
    second = client.post(f"/bids/{bid.id}/review", json=review_body(), headers=headers())

    # Assert
    assert first.status_code == 200
    assert second.status_code == 409
    assert len(runner.reviewed) == 1


def test_reviewing_a_bid_that_is_still_running_is_the_same_conflict(
    client: TestClient, read_model: InMemoryReadModel
) -> None:
    bid = read_model.add_bid(status=BidStatus.CHECKING)

    response = client.post(f"/bids/{bid.id}/review", json=review_body(), headers=headers())

    assert response.status_code == 409


def test_another_companys_bid_is_not_found_rather_than_forbidden(
    client: TestClient, read_model: InMemoryReadModel
) -> None:
    bid, _row = parked_bid(read_model, company_id=OTHER_COMPANY_ID)

    response = client.post(f"/bids/{bid.id}/review", json=review_body(), headers=headers())

    assert response.status_code == 404


def test_an_edit_naming_a_row_this_bid_has_no_matrix_for_is_refused(
    client: TestClient, read_model: InMemoryReadModel
) -> None:
    # Arrange
    bid, _row = parked_bid(read_model)
    body = review_body(row_edits=[{"matrix_row_id": "ghost", "override_reason": "weil"}])

    # Act
    response = client.post(f"/bids/{bid.id}/review", json=body, headers=headers())

    # Assert
    assert response.status_code == 422
    assert "ghost" in response.json()["detail"]


def test_marking_a_row_supported_with_nothing_cited_is_refused_before_the_graph_runs(
    client: TestClient, read_model: InMemoryReadModel, runner: FakeRunner
) -> None:
    """The product's central promise, enforced where the reviewer can still fix it: the bid
    must stay parked rather than failing its run."""
    # Arrange
    bid, row = parked_bid(read_model)
    body = review_body(
        row_edits=[
            {
                "matrix_row_id": row.id,
                "status": "supported",
                "override_reason": "Wir erfüllen das.",
            }
        ]
    )

    # Act
    response = client.post(f"/bids/{bid.id}/review", json=body, headers=headers())

    # Assert
    assert response.status_code == 422
    assert read_model.bids[bid.id].status is BidStatus.AWAITING_REVIEW
    assert runner.reviewed == []


def test_disagreeing_with_the_agent_without_a_reason_is_refused(
    client: TestClient, read_model: InMemoryReadModel
) -> None:
    """An override without a reason is unauditable, and the reviewer is the audit trail."""
    # Arrange
    bid, _row = parked_bid(read_model)

    # Act
    response = client.post(
        f"/bids/{bid.id}/review", json=review_body(decision="go"), headers=headers()
    )

    # Assert
    assert response.status_code == 422
    assert response.json()["detail"] == bids_router.OVERRIDE_NEEDS_A_REASON_DETAIL


def test_disagreeing_with_the_agent_with_a_reason_is_accepted(
    client: TestClient, read_model: InMemoryReadModel, runner: FakeRunner
) -> None:
    # Arrange
    bid, _row = parked_bid(read_model)
    body = review_body(decision="go", override_reason="Die Referenzen liegen als Anlage vor.")

    # Act
    response = client.post(f"/bids/{bid.id}/review", json=body, headers=headers())

    # Assert
    assert response.status_code == 200
    assert runner.reviewed[0][1].decision is Decision.GO


def test_a_bid_that_was_never_scored_accepts_any_decision_without_a_reason(
    client: TestClient, read_model: InMemoryReadModel
) -> None:
    """There is no agent decision to disagree with, so requiring a reason would be asking
    the reviewer to justify a difference from nothing."""
    # Arrange
    bid, _row = parked_bid(read_model)
    read_model.bids[bid.id] = read_model.bids[bid.id].model_copy(update={"verdict": None})

    # Act
    response = client.post(
        f"/bids/{bid.id}/review", json=review_body(decision="go"), headers=headers()
    )

    # Assert
    assert response.status_code == 200


def test_attaching_another_companys_document_is_not_found(
    client: TestClient, read_model: InMemoryReadModel, runner: FakeRunner
) -> None:
    """A tenant boundary: the ids arrive in a request body and nothing else would notice."""
    # Arrange
    bid, row = parked_bid(read_model)
    theirs = read_model.add_document(*document_row(owner=OTHER_COMPANY_ID))
    body = review_body(row_edits=[{"matrix_row_id": row.id, "attached_doc_ids": [theirs.id]}])

    # Act
    response = client.post(f"/bids/{bid.id}/review", json=body, headers=headers())

    # Assert
    assert response.status_code == 404
    assert runner.reviewed == []


def test_attaching_the_companys_own_document_is_accepted(
    client: TestClient, read_model: InMemoryReadModel, runner: FakeRunner
) -> None:
    # Arrange
    bid, row = parked_bid(read_model)
    ours = read_model.add_document(*document_row(kind=DocumentKind.COMPANY_EVIDENCE))
    body = review_body(row_edits=[{"matrix_row_id": row.id, "attached_doc_ids": [ours.id]}])

    # Act
    response = client.post(f"/bids/{bid.id}/review", json=body, headers=headers())

    # Assert
    assert response.status_code == 200
    assert runner.reviewed[0][1].row_edits[0].attached_doc_ids == (ours.id,)


def test_an_attachment_id_that_is_not_a_uuid_is_refused(
    client: TestClient, read_model: InMemoryReadModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`documents_by_id` casts to `uuid.UUID` for the `= any(%s)` comparison; a bad id must
    be a 422 naming the field and not a 500 out of psycopg."""
    # Arrange
    bid, row = parked_bid(read_model)

    async def strict(db: Any, *, company_id: str, document_ids: Sequence[str]) -> Any:
        return [uuid.UUID(identifier) for identifier in document_ids]

    monkeypatch.setattr(bids_router, "documents_by_id", strict)
    body = review_body(row_edits=[{"matrix_row_id": row.id, "attached_doc_ids": ["nope"]}])

    # Act
    response = client.post(f"/bids/{bid.id}/review", json=body, headers=headers())

    # Assert
    assert response.status_code == 422


def test_a_review_that_fails_mid_flight_is_a_500_and_the_bid_records_why(
    client: TestClient, read_model: InMemoryReadModel, runner: FakeRunner
) -> None:
    """The bid was claimed off `awaiting_review` before the resume, so a silent failure
    would strand it. `submit_review` writes the reason; the router only has to say so."""
    # Arrange
    bid, _row = parked_bid(read_model)
    runner.review_error = RuntimeError("the checkpointer went away")

    # Act
    response = client.post(f"/bids/{bid.id}/review", json=review_body(), headers=headers())

    # Assert
    assert response.status_code == 500
    assert response.json()["detail"] == bids_router.REVIEW_FAILED_DETAIL


def test_reviewing_without_the_company_header_is_unauthorised(client: TestClient) -> None:
    response = client.post(f"/bids/{uuid.uuid4()}/review", json=review_body())

    assert response.status_code == 401


def test_a_review_is_refused_when_the_graph_cannot_be_built(
    client: TestClient, read_model: InMemoryReadModel, runner: FakeRunner
) -> None:
    bid, _row = parked_bid(read_model)
    runner._storage_missing = True

    response = client.post(f"/bids/{bid.id}/review", json=review_body(), headers=headers())

    assert response.status_code == 503


def test_two_edits_to_one_row_are_refused_by_the_contract(
    client: TestClient, read_model: InMemoryReadModel
) -> None:
    """`ReviewSubmission` refuses them, so the answer is FastAPI's own 422 on the body."""
    # Arrange
    bid, row = parked_bid(read_model)
    body = review_body(
        row_edits=[
            {"matrix_row_id": row.id, "override_reason": "erst"},
            {"matrix_row_id": row.id, "override_reason": "dann"},
        ]
    )

    # Act / Assert
    response = client.post(f"/bids/{bid.id}/review", json=body, headers=headers())
    assert response.status_code == 422


# ---------------------------------------------------- S3.4.4: what the bid says went wrong


def test_unread_pages_and_problems_are_both_listed_on_the_bid(
    client: TestClient, read_model: InMemoryReadModel
) -> None:
    """S3.4.4's first criterion, at the layer a reviewer meets it. The two are different
    facts and the response carries both: `unread_pages` is a per-document list of pages that
    had no text layer, and `problems` is what parsing and extraction could not do at all —
    a document with *no* readable page becomes an `unreadable_document` problem as well."""
    # Arrange
    unreadable = ExtractionProblem(
        reason=ExtractionProblemReason.UNREADABLE_DOCUMENT,
        document_name="Anlage_7_Scan.pdf",
        pages=(1, 2, 3),
    )
    bid = read_model.add_bid(
        status=BidStatus.AWAITING_REVIEW, problems=[unreadable.model_dump(mode="json")]
    )
    read_model.add_document(*document_row(bid_id=bid.id, name="Anlage_7_Scan.pdf"))

    # Act
    body = client.get(f"/bids/{bid.id}", headers=headers()).json()

    # Assert
    assert body["documents"][0]["unread_pages"] == [3]
    assert body["problems"][0]["reason"] == "unreadable_document"
    assert body["problems"][0]["pages"] == [1, 2, 3]


def test_a_reviewed_bid_carries_the_reviewers_decision_beside_the_re_scored_verdict(
    client: TestClient, read_model: InMemoryReadModel
) -> None:
    """ADR-0025's whole point, at the API. The verdict is what the rules say about the matrix
    as the reviewer left it; `decision` is what the reviewer concluded. Without both on this
    response the workspace would show the re-score while the dashboard showed the override."""
    # Arrange
    rescored = Verdict(
        decision=Decision.CONDITIONAL,
        gaps=(Gap(requirement_id="a", severity=GapSeverity.OPEN_ITEM, summary="Personal"),),
        rationale="Dieses Angebot ist mit Auflagen möglich.",
        mandatory_total=2,
        mandatory_supported=1,
        partially_supported_rows=1,
    )
    bid = read_model.add_bid(
        status=BidStatus.COMPLETE,
        verdict=rescored.model_dump(mode="json"),
        reviewed_decision=Decision.NO_GO,
    )

    # Act
    body = client.get(f"/bids/{bid.id}", headers=headers()).json()

    # Assert
    assert body["verdict"]["decision"] == "conditional"
    assert body["decision"] == "no_go"


def test_a_bid_nobody_has_reviewed_has_no_decision(
    client: TestClient, read_model: InMemoryReadModel
) -> None:
    """Null until a human has decided — the agent's advisory answer lives in `verdict`."""
    bid = read_model.add_bid(
        status=BidStatus.AWAITING_REVIEW, verdict=AGENT_VERDICT.model_dump(mode="json")
    )

    assert client.get(f"/bids/{bid.id}", headers=headers()).json()["decision"] is None


def test_a_review_already_in_flight_is_the_same_conflict_as_a_second_submission(
    client: TestClient, read_model: InMemoryReadModel, runner: FakeRunner
) -> None:
    """The database claim cannot see an in-flight review: the resumed graph rewrites
    `awaiting_review` on its way past the interrupt. The runner holds the other half of the
    guard, and a reviewer must not be able to tell the two cases apart."""
    # Arrange
    bid, _row = parked_bid(read_model)
    runner.review_error = RunnerError(f"bid {bid.id} is already being reviewed")

    # Act
    response = client.post(f"/bids/{bid.id}/review", json=review_body(), headers=headers())

    # Assert
    assert response.status_code == 409
    assert response.json()["detail"] == bids_router.NOT_AWAITING_REVIEW_DETAIL


# -------------------------------------------- S4.4.1: the buyer and deadline the list needs


def test_a_bid_may_be_started_with_the_buyer_and_a_deadline_carrying_its_offset(
    client: TestClient, read_model: InMemoryReadModel
) -> None:
    """Until S1.2.1 pulls these from TED, the bidder has the notice in front of them."""
    # Arrange
    document = read_model.add_document(*document_row())

    # Act
    response = client.post(
        "/bids",
        json=start_body(
            document.id,
            buyer="Ministère de l'Intérieur",
            deadline="2026-10-09T16:00:00+02:00",
        ),
        headers=headers(),
    )

    # Assert
    assert response.status_code == 202
    stored = read_model.bids[response.json()["id"]]
    assert stored.buyer == "Ministère de l'Intérieur"
    assert stored.deadline is not None
    # The instant, and separately the offset the notice stated — see migration 0007.
    assert stored.deadline.utcoffset() == timedelta(hours=2)
    assert stored.deadline_utc_offset_minutes == 120


def test_a_deadline_with_no_offset_is_refused_rather_than_assumed_to_be_utc(
    client: TestClient, read_model: InMemoryReadModel
) -> None:
    """Guessing a zone silently moves a deadline by hours, which is the one field where that
    is a real error rather than a tidiness one."""
    # Arrange
    document = read_model.add_document(*document_row())

    # Act
    response = client.post(
        "/bids",
        json=start_body(document.id, deadline="2026-10-09T16:00:00"),
        headers=headers(),
    )

    # Assert
    assert response.status_code == 422
    assert "offset" in response.text


def test_a_bid_started_without_them_keeps_both_null(
    client: TestClient, read_model: InMemoryReadModel
) -> None:
    # Arrange
    document = read_model.add_document(*document_row())

    # Act
    response = client.post("/bids", json=start_body(document.id), headers=headers())

    # Assert
    stored = read_model.bids[response.json()["id"]]
    assert (stored.buyer, stored.deadline, stored.deadline_utc_offset_minutes) == (
        None,
        None,
        None,
    )


def test_a_blank_buyer_is_stored_as_absent_rather_than_as_an_empty_cell(
    client: TestClient, read_model: InMemoryReadModel
) -> None:
    # Arrange
    document = read_model.add_document(*document_row())

    # Act
    response = client.post(
        "/bids", json=start_body(document.id, buyer="   "), headers=headers()
    )

    # Assert
    assert read_model.bids[response.json()["id"]].buyer is None


def test_the_list_carries_what_the_dashboard_renders(
    client: TestClient, read_model: InMemoryReadModel
) -> None:
    """S4.4.1's row: a verdict badge, a deadline countdown, and the count of open items."""
    # Arrange
    read_model.add_bid(
        status=BidStatus.AWAITING_REVIEW,
        buyer="Ministère de l'Intérieur",
        deadline=datetime(2026, 10, 9, 14, 0, tzinfo=UTC),
        deadline_utc_offset_minutes=120,
        open_items=7,
        verdict=AGENT_VERDICT.model_dump(mode="json"),
    )

    # Act
    [row] = client.get("/bids", headers=headers()).json()["bids"]

    # Assert
    assert row["buyer"] == "Ministère de l'Intérieur"
    assert row["deadline"] == "2026-10-09T14:00:00Z"
    assert row["deadline_utc_offset_minutes"] == 120
    assert row["open_items"] == 7
    assert row["decision"] == "no_go"
