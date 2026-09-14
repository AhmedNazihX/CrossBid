"""S4.6.3 — `POST /bids/{id}/feedback` and `GET /bids/{id}/feedback`: the bidder's own word.

A thumb, optionally about one matrix row, optionally with a comment. That is the whole
story: the ratings are *kept*, and nothing learns from them — feedback-driven learning is
cut from the course build (docs/project-plan.md), so this router stores and reads and does
nothing else with what it stores.

**Why the routes hang off a bid rather than living at `/feedback`.** The bid is the scope.
Putting it in the path means the tenant check and the target check are the same lookup — the
insert selects the bid, proves it is the caller's and writes `company_id` from it
(`readmodel/feedback.py`) — and it means a client cannot name a bid in a body while the URL
says nothing. `POST /bids/{id}/review` is shaped the same way for the same reason.

**One 404 for two causes.** A bid that is not the caller's and a matrix row that is not that
bid's both leave the insert with nothing to insert, and both answer 404 rather than 403: a
"forbidden" would confirm the id exists, which is `routers/bids.py`'s rule applied here.

**The comment never reaches a log line.** It is free text a bidder wrote about their own
tender, so the log records that a rating happened, for which bid, and which way the thumb
pointed — never what was said.

Response fields carry a description where the name does not already say it:
`frontend/lib/api.ts` is generated from this schema.
"""

from __future__ import annotations

import logging
import uuid
from typing import Final

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from crossbid.auth import CompanyContext, current_company
from crossbid.db import Database
from crossbid.main import get_database
from crossbid.models.review import MAX_COMMENT_CHARS
from crossbid.readmodel.feedback import (
    FeedbackRecord,
    Rating,
    fetch_feedback,
    record_feedback,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bids", tags=["feedback"])

NOTHING_TO_RATE_DETAIL: Final = (
    "No such bid, or that matrix row does not belong to it, so there was nothing to rate."
)


# ------------------------------------------------------------------------ request models


class FeedbackSubmission(BaseModel):
    """A thumb about one answer, and what the bidder would have said instead."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rating: Rating = Field(description="1 for a thumb up, -1 for a thumb down")
    matrix_row_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "The matrix row being rated. Null rates the bid's own answer, which is what a "
            "chat answer will be when F3.5 lands"
        ),
    )
    comment: str | None = Field(
        default=None,
        max_length=MAX_COMMENT_CHARS,
        description="The correction, in the bidder's words. Optional: a thumb is a rating",
    )


class FeedbackListResponse(BaseModel):
    """Every target of this bid the bidder has rated, with what they last said about it."""

    model_config = ConfigDict(frozen=True)

    feedback: list[FeedbackRecord] = Field(
        description=(
            "The latest rating per target, so re-rating a row replaces what the screen "
            "shows without losing the earlier answer from the table"
        )
    )


# ------------------------------------------------------------------------------- routes


@router.post(
    "/{bid_id}/feedback",
    status_code=status.HTTP_201_CREATED,
    response_model=FeedbackRecord,
    summary="Rate one matrix row, or the bid's answer",
)
async def post_feedback(
    bid_id: uuid.UUID,
    body: FeedbackSubmission,
    company: CompanyContext = Depends(current_company),
    db: Database = Depends(get_database),
) -> FeedbackRecord:
    """Store the rating and answer with the row as it was written.

    Rating the same target again appends rather than replacing: the bidder's first answer is
    part of the record this story exists to keep, and `GET` shows only the latest of them.

    A comment of nothing but whitespace is stored as no comment at all, so "rated, said
    nothing" is one state in the database rather than two.
    """
    company_id = company.company_id
    comment = (body.comment or "").strip() or None
    stored = await record_feedback(
        db,
        company_id=company_id,
        bid_id=str(bid_id),
        rating=body.rating,
        matrix_row_id=None if body.matrix_row_id is None else str(body.matrix_row_id),
        comment=comment,
    )
    if stored is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOTHING_TO_RATE_DETAIL)
    logger.info(
        "Bid %s: rating %d recorded for %s",
        bid_id,
        stored.rating.value,
        "row " + stored.matrix_row_id if stored.matrix_row_id is not None else "the bid",
    )
    return stored


@router.get(
    "/{bid_id}/feedback",
    response_model=FeedbackListResponse,
    summary="What this company has rated on this bid",
)
async def get_feedback(
    bid_id: uuid.UUID,
    company: CompanyContext = Depends(current_company),
    db: Database = Depends(get_database),
) -> FeedbackListResponse:
    """The latest rating of each target, so the workspace can show a thumb it already has.

    A bid that is not the caller's is an empty list rather than a 404: the statement is
    scoped by company, so there is nothing to find and nothing to distinguish it from a bid
    nobody has rated yet — and answering 404 here would tell a caller which bid ids exist.
    """
    stored = await fetch_feedback(db, company_id=company.company_id, bid_id=str(bid_id))
    return FeedbackListResponse(feedback=stored)
