"""S3.1.1 — `POST /bids`, `GET /bids/{id}`, `GET /bids`.

Thin on purpose. `POST /bids` checks that the company exists and that every document named
is this company's, a tender document, unattached and `ready`; then it records a `queued`
bid, attaches the documents, hands the row to `agent.runner.BidRunner` and answers **202**.
The graph runs after the response has gone, and `GET /bids/{id}` is what the browser polls
every two seconds — it reads the `bids`, `requirements` and `matrix_rows` projections and
never a checkpoint (integration point I2: this response is the shape S4.5.1's workspace
consumes). The matrix arrives lane by lane while the status is `checking` (S3.3.1), so the
poller sees it fill in rather than appear.

Two rules about answers. A bid, a company or a document that is not the caller's answers
**404**, never 403: a "forbidden" confirms the id exists (S2.2.2's reasoning, applied to
every route here). A document that *is* the caller's but cannot start a bid answers a code
that names the problem — **422** for company evidence, **409** for a file still processing
or already attached to another bid — so the browser can say which file to fix.

`POST /bids` carries S2.3.3's per-company hourly limit: over it, the answer is **429** with
a `Retry-After` and no run is started. `crossbid/rate_limit.py` holds the counters.

The response models are the frontend's contract (`frontend/lib/api.ts` is generated from
this schema), so every field carries a description and nothing server-side (`thread_id`,
`storage_path`, `company_id`) is in them. `problems` are `ExtractionProblem`s re-validated
from the row's JSON: the read model stores them raw so that it never imports from `agent/`.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Final

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from crossbid.agent.runner import BidRunner, RunnerError, build_runner
from crossbid.agent.state import ExtractionProblem
from crossbid.auth import CompanyContext, current_company
from crossbid.db import Database
from crossbid.ingestion.storage import StorageError
from crossbid.main import get_app_settings, get_database
from crossbid.models.matrix import MatrixRow
from crossbid.models.requirement import Requirement
from crossbid.models.review import ReviewSubmission, RowEdit
from crossbid.models.tender import BidStatus, BidSummary
from crossbid.models.verdict import Decision, Verdict
from crossbid.rate_limit import RATE_LIMITED_RESPONSES, bid_start_limit
from crossbid.readmodel.bids import (
    TENDER_DOCUMENT_KINDS,
    BidDocumentRow,
    BidRow,
    BidStateError,
    attach_documents,
    bid_documents,
    claim_bid_for_review,
    company_language,
    create_bid,
    documents_by_id,
    fetch_bid,
    list_bids,
    mark_bid_failed,
)
from crossbid.readmodel.documents import DocumentStatus
from crossbid.readmodel.matrix import fetch_matrix_rows
from crossbid.readmodel.requirements import fetch_requirements
from crossbid.settings import Settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bids", tags=["bids"])

RUNNER_STATE_KEY: Final = "bid_runner"
"""Where the runner lives on `app.state`. The lifespan sets it from
`resume_unfinished_runs`; if it has not, the first request builds one and stores it there,
so startup and requests share one task registry either way."""

NO_SUCH_COMPANY_DETAIL: Final = "No such company."
NO_SUCH_BID_DETAIL: Final = "No such bid."
STORAGE_NOT_CONFIGURED_DETAIL: Final = (
    "Document storage is not configured on this server, so bids cannot be started."
)
ATTACH_FAILED_REASON_PREFIX: Final = "attaching documents failed"
MAX_BUYER_CHARS: Final = 300
"""A contracting authority's legal name, with room to spare. Bounded because it is free text
from a request body and it is rendered in a table cell."""
NOT_AWAITING_REVIEW_DETAIL: Final = (
    "This bid is not waiting for a review. It has either been reviewed already or has not "
    "finished running."
)
OVERRIDE_NEEDS_A_REASON_DETAIL: Final = (
    "Your decision differs from the agent's, so a reason is required: give override_reason."
)
REVIEW_FAILED_DETAIL: Final = (
    "The review could not be applied, and the bid is still waiting for you. Try again; if it "
    "keeps failing, the run's log says why."
)


# ------------------------------------------------------------------------ request models


class StartBidRequest(BaseModel):
    """What it takes to start a bid: the notice, the tender's language, and the pack."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    notice_number: str = Field(
        min_length=1, description="TED publication number the bid is opened against"
    )
    document_ids: list[uuid.UUID] = Field(
        min_length=1, description="Ready tender documents to parse; at least one"
    )
    source_language: str = Field(
        min_length=2,
        max_length=5,
        description="The tender's own language, BCP 47; S1.2.1 takes it from TED later",
    )
    title: str | None = Field(
        default=None, description="Dashboard title; defaults to the notice number"
    )
    buyer: str | None = Field(
        default=None,
        max_length=MAX_BUYER_CHARS,
        description="The contracting authority, as the notice names it. S1.2.1 takes it "
        "from TED later; until then the bidder has the notice in front of them.",
    )
    deadline: datetime | None = Field(
        default=None,
        description=(
            "When tenders are due, as an ISO-8601 timestamp **with the offset the notice "
            "states** — e.g. `2026-10-09T16:00:00+02:00`. The offset is kept alongside the "
            "instant so the dashboard can print the deadline on the buyer's own clock "
            "(S4.4.1); a timestamp with no offset is refused rather than assumed to be UTC, "
            "because guessing a zone silently moves a deadline by hours."
        ),
    )

    @field_validator("deadline")
    @classmethod
    def _deadline_states_its_offset(cls, value: datetime | None) -> datetime | None:
        """A naive timestamp is refused. See the field description for why.

        Pydantic parses `2026-10-09T16:00:00` happily and hands back a naive `datetime`; the
        column would then store it as whatever the session's zone happens to be. A deadline
        is the one field where that is a real error rather than a tidiness one.
        """
        if value is not None and value.utcoffset() is None:
            raise ValueError(
                "deadline must carry the notice's UTC offset, e.g. 2026-10-09T16:00:00+02:00"
            )
        return value

    @property
    def deadline_utc_offset_minutes(self) -> int | None:
        """The offset the notice stated, in minutes, for `bids.deadline_utc_offset_minutes`."""
        if self.deadline is None:
            return None
        offset = self.deadline.utcoffset()
        return None if offset is None else int(offset.total_seconds() // 60)


# ----------------------------------------------------------------------- response models


class BidDocumentResponse(BaseModel):
    """One document of the bid, as the workspace lists it beside the matrix."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID = Field(description="The document id; `GET /documents/{id}` polls it")
    name: str = Field(description="The filename the bidder uploaded")
    pages: int = Field(description="Total pages once parsed")
    unread_pages: list[int] = Field(description="Pages with no text layer, never read")

    @classmethod
    def from_row(cls, row: BidDocumentRow) -> BidDocumentResponse:
        return cls(
            id=uuid.UUID(row.id),
            name=row.name,
            pages=row.pages,
            unread_pages=list(row.unread_pages),
        )


class BidResponse(BaseModel):
    """One bid and how far its run has got. `GET /bids/{id}` is polled for it."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID = Field(description="The bid id; poll `GET /bids/{id}` with it")
    notice_number: str | None = Field(description="TED publication number")
    title: str = Field(description="What the dashboard calls this bid")
    source_language: str | None = Field(description="The tender's language, BCP 47")
    bidder_language: str = Field(description="What requirements are explained in")
    status: BidStatus = Field(
        description=(
            "queued → parsing → extracting → checking → scoring → awaiting_review; failed "
            "carries failure_reason"
        )
    )
    failure_reason: str | None = Field(
        description="Why a failed run stopped: the stage and the error type, no more"
    )
    requirements: list[Requirement] = Field(
        description="Every extracted requirement; empty until extraction has finished"
    )
    matrix_rows: list[MatrixRow] = Field(
        description=(
            "The compliance matrix, one row per checked requirement, in the same order as "
            "`requirements`. Fills in lane by lane while the status is `checking`."
        )
    )
    verdict: Verdict | None = Field(
        description=(
            "The agent's go/no-go with every gap behind it, written when the status "
            "reaches `scoring`, and re-scored on the reviewer's statuses once they have "
            "reviewed. Null before scoring. Advisory: what the *rules* say about the matrix."
        )
    )
    decision: Decision | None = Field(
        description=(
            "What the reviewer decided. Null until a human has. Deliberately not the same "
            "field as `verdict.decision`: that is what the rules say about the matrix as "
            "the reviewer left it, and this is what the reviewer concluded. The difference "
            "between them is the override."
        )
    )
    problems: list[ExtractionProblem] = Field(
        description="What parsing and extraction could not do, for the reviewer"
    )
    documents: list[BidDocumentResponse] = Field(description="The pack this bid parses")
    created_at: datetime | None = Field(description="When the bid was started")
    updated_at: datetime | None = Field(description="When the status last changed")

    @classmethod
    def assemble(
        cls,
        bid: BidRow,
        *,
        requirements: list[Requirement],
        documents: list[BidDocumentRow],
        matrix_rows: list[MatrixRow] | None = None,
    ) -> BidResponse:
        return cls(
            id=uuid.UUID(bid.id),
            notice_number=bid.notice_number,
            title=bid.title,
            source_language=bid.source_language,
            bidder_language=bid.bidder_language,
            status=bid.status,
            failure_reason=bid.failure_reason,
            requirements=requirements,
            matrix_rows=list(matrix_rows or []),
            verdict=_verdict_of(bid),
            decision=bid.reviewed_decision,
            problems=[ExtractionProblem.model_validate(problem) for problem in bid.problems],
            documents=[BidDocumentResponse.from_row(row) for row in documents],
            created_at=bid.created_at,
            updated_at=bid.updated_at,
        )


class BidListResponse(BaseModel):
    """The calling company's bids, newest first."""

    model_config = ConfigDict(frozen=True)

    bids: list[BidSummary] = Field(description="Newest first, at most 200")


# ------------------------------------------------------------------------- dependencies


def get_bid_runner(
    request: Request,
    db: Database = Depends(get_database),
    settings: Settings = Depends(get_app_settings),
) -> BidRunner:
    """The process-wide runner: one task registry for startup resumes and requests alike."""
    runner: BidRunner | None = getattr(request.app.state, RUNNER_STATE_KEY, None)
    if runner is None:
        runner = build_runner(db, settings)
        setattr(request.app.state, RUNNER_STATE_KEY, runner)
    return runner


# ------------------------------------------------------------------------------- routes


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BidResponse,
    summary="Start a bid",
    # S2.3.3. This is the expensive route -- one run is ~5 minutes and ~$1.60 -- so the
    # limit is settled before the company, the documents or the graph are even looked up.
    dependencies=[Depends(bid_start_limit)],
    responses=RATE_LIMITED_RESPONSES,
)
async def start_bid(
    body: StartBidRequest,
    company: CompanyContext = Depends(current_company),
    db: Database = Depends(get_database),
    runner: BidRunner = Depends(get_bid_runner),
) -> BidResponse:
    """Record a `queued` bid, attach its documents and start the graph in the background.

    Answers 202 at once; poll `GET /bids/{id}` until the status is `awaiting_review` or
    `failed`. Every document must be this company's, a tender document, unattached and
    `ready`, or the answer names the one that is not.
    """
    company_id = company.company_id
    bidder_language = await company_language(db, company_id=company_id)
    if bidder_language is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NO_SUCH_COMPANY_DETAIL)

    document_ids = list(dict.fromkeys(str(identifier) for identifier in body.document_ids))
    rows = await documents_by_id(db, company_id=company_id, document_ids=document_ids)
    _check_documents(document_ids, rows)
    _check_graph_available(runner)

    bid = await create_bid(
        db,
        company_id=company_id,
        notice_number=body.notice_number.strip(),
        title=(body.title or "").strip() or body.notice_number.strip(),
        source_language=body.source_language.strip(),
        bidder_language=bidder_language,
        buyer=(body.buyer or "").strip() or None,
        deadline=body.deadline,
        deadline_utc_offset_minutes=body.deadline_utc_offset_minutes,
    )
    try:
        await attach_documents(
            db, company_id=company_id, bid_id=bid.id, document_ids=document_ids
        )
    except BidStateError as exc:
        # The row exists and would otherwise sit at `queued` for ever; say why it stopped.
        reason = f"{ATTACH_FAILED_REASON_PREFIX}: {type(exc).__name__}"
        await mark_bid_failed(db, company_id=company_id, bid_id=bid.id, reason=reason)
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    runner.start(bid)
    logger.info(
        "Bid %s started for company %s with %d document(s)", bid.id, company_id, len(rows)
    )
    return BidResponse.assemble(bid, requirements=[], documents=rows)


@router.post(
    "/{bid_id}/review",
    response_model=BidResponse,
    summary="Submit the review that finishes a bid",
)
async def submit_review(
    bid_id: uuid.UUID,
    body: ReviewSubmission,
    company: CompanyContext = Depends(current_company),
    db: Database = Depends(get_database),
    runner: BidRunner = Depends(get_bid_runner),
) -> BidResponse:
    """Resume the parked run with the reviewer's edits and answer the finished bid.

    The safety boundary: nothing leaves this system as final until a person has been here.
    The run is waiting at its interrupt, this hands it the submission, the scorer re-runs on
    the reviewer's statuses and the bid ends `complete`.

    Answers **409** when the bid is not parked at `awaiting_review` — which is the same
    answer for "somebody already reviewed it" and "it is still running", because the claim
    is one conditional update and cannot tell them apart. That is deliberate: a second
    submission must not half-apply. **422** names a row the matrix does not have, a status
    the row cannot legally take, or a decision that differs from the agent's with no reason
    given; the check happens here, before the graph is resumed, so a rejected review leaves
    the bid exactly where it was.
    """
    company_id = company.company_id
    bid = await fetch_bid(db, company_id=company_id, bid_id=str(bid_id))
    if bid is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NO_SUCH_BID_DETAIL)
    _check_graph_available(runner)

    rows = await fetch_matrix_rows(db, company_id=company_id, bid_id=bid.id)
    _check_review(body, bid, rows)
    await _check_attachments(db, company_id=company_id, review=body)

    try:
        await claim_bid_for_review(db, company_id=company_id, bid_id=bid.id)
    except BidStateError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail=NOT_AWAITING_REVIEW_DETAIL
        ) from exc

    try:
        await runner.submit_review(bid, body)
    except RunnerError as exc:
        # A review already in flight for this bid. The database claim cannot see it — the
        # resumed graph rewrites `awaiting_review` on its way past the interrupt — so the
        # runner holds the second half of the guard, and the reviewer gets the same answer
        # they would for a second submission, because that is what it is.
        logger.info("Bid %s: a review is already in flight", bid.id)
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail=NOT_AWAITING_REVIEW_DETAIL
        ) from exc
    except Exception as exc:
        # `submit_review` has already put the bid back on `awaiting_review` with the reason,
        # so the reviewer may simply try again; say so without quoting the failure.
        logger.exception("Bid %s: the review could not be applied", bid.id)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, detail=REVIEW_FAILED_DETAIL
        ) from exc

    logger.info("Bid %s reviewed: the reviewer decided %s", bid.id, body.decision.value)
    return await _bid_response(db, company_id=company_id, bid_id=bid.id)


@router.get("/{bid_id}", response_model=BidResponse, summary="Poll one bid")
async def get_bid(
    bid_id: uuid.UUID,
    company: CompanyContext = Depends(current_company),
    db: Database = Depends(get_database),
) -> BidResponse:
    """One bid of the calling company with its requirements so far. Another's id is 404."""
    if await fetch_bid(db, company_id=company.company_id, bid_id=str(bid_id)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NO_SUCH_BID_DETAIL)
    return await _bid_response(db, company_id=company.company_id, bid_id=str(bid_id))


@router.get("", response_model=BidListResponse, summary="List the company's bids")
async def list_company_bids(
    company: CompanyContext = Depends(current_company),
    db: Database = Depends(get_database),
) -> BidListResponse:
    """Every bid of the calling company, newest first, from the read model only."""
    rows = await list_bids(db, company_id=company.company_id)
    return BidListResponse(bids=[row.summary() for row in rows])


# ------------------------------------------------------------------------------ helpers


async def _bid_response(db: Database, *, company_id: str, bid_id: str) -> BidResponse:
    """The polling shape, read from the four projections and never from a checkpoint.

    Re-reads the bid rather than taking the caller's copy: after a review the row has moved
    on, and answering with the one fetched before the resume would show the reviewer the
    state they were trying to leave.
    """
    bid = await fetch_bid(db, company_id=company_id, bid_id=bid_id)
    if bid is None:  # pragma: no cover -- the caller has just read the row
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NO_SUCH_BID_DETAIL)
    return BidResponse.assemble(
        bid,
        requirements=await fetch_requirements(db, company_id=company_id, bid_id=bid_id),
        documents=await bid_documents(db, company_id=company_id, bid_id=bid_id),
        matrix_rows=await fetch_matrix_rows(db, company_id=company_id, bid_id=bid_id),
    )


def _check_review(review: ReviewSubmission, bid: BidRow, rows: Sequence[MatrixRow]) -> None:
    """Every edit names a row of this bid and leaves it saveable, and an override has a
    reason. Refused here rather than inside the graph: a 422 leaves the bid parked where the
    reviewer can fix their submission, where a node raising would fail the run instead.
    """
    by_id = {row.id: row for row in rows}
    for edit in review.row_edits:
        row = by_id.get(edit.matrix_row_id)
        if row is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"This bid has no matrix row {edit.matrix_row_id}.",
            )
        _check_row_edit(edit, row)
    agent = _verdict_of(bid)
    disagrees = agent is not None and review.decision is not agent.decision
    if disagrees and not review.override_reason:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail=OVERRIDE_NEEDS_A_REASON_DETAIL
        )


def _check_row_edit(edit: RowEdit, row: MatrixRow) -> None:
    """The edit, applied, must still satisfy `MatrixRow` — chiefly the rule that a
    `supported` row carries a citation or an attachment. Checking it by construction rather
    than by restating the rule keeps one definition of it (S3.3.1)."""
    try:
        MatrixRow.model_validate(
            row.model_dump()
            | {
                "status": row.status if edit.status is None else edit.status,
                "attached_doc_ids": [*row.attached_doc_ids, *edit.attached_doc_ids],
            }
        )
    except ValidationError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"Row {edit.matrix_row_id} cannot be marked {edit.status}: a supported row "
                "needs an evidence quote or an attached document."
            ),
        ) from exc


async def _check_attachments(
    db: Database, *, company_id: str, review: ReviewSubmission
) -> None:
    """Every attached document is one of this company's. A tenant boundary, so it is a
    lookup and not a format check: the ids arrive in a request body and nothing else in the
    path would notice one belonging to somebody else."""
    wanted = sorted({doc_id for edit in review.row_edits for doc_id in edit.attached_doc_ids})
    if not wanted:
        return
    try:
        owned = await documents_by_id(db, company_id=company_id, document_ids=wanted)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Attached document ids must be UUIDs."
        ) from exc
    found = {row.id for row in owned}
    missing = [doc_id for doc_id in wanted if doc_id not in found]
    if missing:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"No such document: {', '.join(missing)}."
        )


def _verdict_of(bid: BidRow) -> Verdict | None:
    """The stored verdict, re-validated on the way out, or `None` if there is none.

    A stored shape the contract no longer recognises answers `None` rather than a 500: the
    column is a projection, the checkpoint is the authority (S3.4.3), and a bid whose
    verdict predates a vocabulary change must still be openable so its reviewer can re-run
    it. The row's own `decision` property makes the same choice for the dashboard.
    """
    if bid.verdict is None:
        return None
    try:
        return Verdict.model_validate(bid.verdict)
    except ValidationError:
        logger.warning("Bid %s: the stored verdict no longer validates; omitting it", bid.id)
        return None


def _check_documents(document_ids: list[str], rows: list[BidDocumentRow]) -> None:
    """Every id names one of the caller's ready, unattached tender documents, or a 4xx says
    which does not. Ids of other companies are simply absent from `rows`, hence 404."""
    found = {row.id for row in rows}
    missing = [identifier for identifier in document_ids if identifier not in found]
    if missing:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"No such document: {', '.join(missing)}."
        )
    for row in rows:
        if row.kind not in TENDER_DOCUMENT_KINDS:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Document {row.name} is company evidence, not a tender document.",
            )
        if row.bid_id is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=f"Document {row.name} already belongs to another bid.",
            )
        if row.status is not DocumentStatus.READY:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=f"Document {row.name} is {row.status.value}, not ready.",
            )


def _check_graph_available(runner: BidRunner) -> None:
    """Build the graph before the bid row exists, so a missing Storage is a 503 and not a
    `queued` bid that fails a moment later."""
    try:
        runner.graph  # noqa: B018 -- the access is the check
    except StorageError as exc:
        logger.error("bids unavailable: %s", exc)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail=STORAGE_NOT_CONFIGURED_DETAIL
        ) from exc
