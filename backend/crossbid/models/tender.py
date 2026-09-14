"""The tender side: a TED notice, and the bid a company opens against it."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from crossbid.models.verdict import Decision


class BidStatus(StrEnum):
    """Where a bid has got to.

    The browser polls `GET /bids/{id}` every 2s and renders the stage, so these names are
    user-visible. `AWAITING_REVIEW` is the interrupt: the graph stops and waits for a human.
    """

    QUEUED = "queued"
    PARSING = "parsing"
    EXTRACTING = "extracting"
    CHECKING = "checking"
    SCORING = "scoring"
    AWAITING_REVIEW = "awaiting_review"
    APPLYING_REVIEW = "applying_review"
    COMPLETE = "complete"
    FAILED = "failed"


class DocumentKind(StrEnum):
    """What a stored file is — and, since S2.5.1, which reader is allowed to open it.

    A company's evidence pack outlives any single bid; a tender's documents belong to one bid
    and are deleted with it. The notice is kept apart from the procurement documents because
    it comes from TED's documented API while the rest is uploaded by the bidder.

    `TENDER_ESPD_REQUEST` is the odd one and deliberately so: it is the only kind that is not
    a PDF. A published DUME is an XML form carrying the buyer's ESPD criteria as canonical
    UUIDs, so it is read by `ingestion/espd.py` and never by the PDF parser. Keeping it a
    *kind* rather than an exception to the PDF rule is what lets the upload boundary stay an
    accept-list: every other kind is still PDF-only, and this one is XML-only (see
    `routers/documents.py`).
    """

    COMPANY_EVIDENCE = "company_evidence"
    TENDER_DOCUMENT = "tender_document"
    TENDER_NOTICE = "tender_notice"
    TENDER_ESPD_REQUEST = "tender_espd_request"


class TedNotice(BaseModel):
    """A published notice, as returned by TED's Search API v3.

    Only fields the product actually uses. `document_urls` point at national platforms and are
    shown to the bidder to click — never fetched (the no-scraping rule); across the DE and FR
    samples, none pointed at TED itself.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    publication_number: str = Field(description="e.g. '614251-2026'")
    title: str
    buyer_name: str
    buyer_country: str = Field(min_length=2, max_length=3)
    cpv_codes: tuple[str, ...] = ()

    official_language: str = Field(min_length=2, max_length=5)
    submission_languages: tuple[str, ...] = ()

    publication_date: date | None = None
    deadline: datetime | None = None

    notice_pdf_url: str | None = Field(default=None, description="TED-hosted, safe to download")
    document_urls: tuple[str, ...] = Field(
        default=(), description="National platform pages. Displayed, never fetched."
    )


class BidSummary(BaseModel):
    """A bid as the dashboard lists it. Read from the read-model tables, never a checkpoint."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    company_id: str
    ted_publication_number: str | None = None
    title: str
    buyer: str | None = None
    source_language: str | None = None
    deadline: datetime | None = None
    deadline_utc_offset_minutes: int | None = Field(
        default=None,
        description=(
            "The UTC offset the buyer's notice stated, so the deadline can be printed on "
            "the buyer's clock (S4.4.1). Null when no deadline is recorded. Only an offset "
            "and never an IANA zone: neither a notice nor TED publishes one, so a zone "
            "name would be an inference — and one that changes answer twice a year."
        ),
    )
    status: BidStatus
    decision: Decision | None = Field(
        default=None, description="Final decision once reviewed; None while in flight"
    )
    open_items: int = Field(
        default=0,
        ge=0,
        description=(
            "Matrix rows that still need somebody: `partially_supported` or `unsupported`. "
            "Counted from the matrix rather than from the verdict's gaps, because a bid that "
            "has not been scored yet has no gaps and still has work in it — and because a "
            "reviewer who confirmed a partially supported row has confirmed that it is still "
            "unproven, not that it is settled."
        ),
    )
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def is_awaiting_review(self) -> bool:
        """The one state that is owed an answer by a person. The dashboard sorts on it."""
        return self.status is BidStatus.AWAITING_REVIEW
