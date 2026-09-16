"""One row of the compliance matrix: a requirement, and what we can prove about it.

The product's safety rule lives here: **every row carries a citation or is marked unclear.**
`MatrixRow.status` may only be `MET` when `evidence` is non-empty, and the model enforces it
rather than trusting the caller.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from crossbid.models.ecertis_criteria import EcertisCriterionId

MAX_QUOTE_CHARS = 2000


class RowStatus(StrEnum):
    """The agent's finding for one requirement, in the design system's words (ADR-0013).

    `supported` is cited evidence; `partially_supported` is the honest answer when the
    documents do not settle it and the reviewer must; `unsupported` is evidence *against*.
    """

    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"
    NOT_APPLICABLE = "not_applicable"


class ReviewerStatus(StrEnum):
    """What the human did with the agent's finding. The review step is the safety boundary."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    OVERRIDDEN = "overridden"


class Evidence(BaseModel):
    """A pointer into the bidder's own documents. Never a summary — a locatable quote."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: str
    document_name: str
    page: int = Field(ge=1)
    quote: str = Field(max_length=MAX_QUOTE_CHARS)


class EcertisEvidence(BaseModel):
    """Which national document proves an EU criterion, per eCertis.

    This is the cross-border wedge in one object: the same `criterion_id` yields
    `Freistellungsbescheinigung` for DE and `Cerfa n. 3666` for FR.

    A country with no national entry is normal, not an error — France has none for 17 of the
    56 criteria (ADR-0007). `evidence_names` is then empty and `found` is False.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    criterion_id: EcertisCriterionId
    criterion_name: str
    country: str = Field(
        min_length=2, max_length=2, description="ISO 3166-1 alpha-2, lowercase"
    )
    found: bool = Field(description="False means this country records no evidence")
    evidence_names: tuple[str, ...] = ()
    issuers: tuple[str, ...] = ()
    description: str | None = None


class MatrixRow(BaseModel):
    """The agent's verdict on one requirement, plus the reviewer's disposition."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    requirement_id: str

    status: RowStatus
    evidence: tuple[Evidence, ...] = ()
    ecertis_evidence: EcertisEvidence | None = None
    agent_rationale: str = Field(
        description="Why the agent chose this status, in one or two sentences"
    )

    agent_status: RowStatus | None = Field(
        default=None,
        description="What the agent decided, kept even after a reviewer overrules `status`",
    )
    """Written once, by the check loop, and never rewritten.

    `status` is the row's *effective* answer: `apply_review` puts the reviewer's verdict there
    because that is what the scorer re-runs on and what the dashboard counts. That left the
    agent's own verdict nowhere a request could reach — only in the checkpoint — so the
    workspace could say a row was overridden and never say what it was overridden from
    (H24; S4.5.2 asks for exactly that).

    Nullable because rows written before migration 0009 have no answer and inventing one
    would be worse than saying nothing: for an already-overridden row, copying `status` would
    assert the agent agreed when the record says it did not.
    """

    reviewer_status: ReviewerStatus = ReviewerStatus.PENDING
    override_reason: str | None = None
    attached_doc_ids: tuple[str, ...] = ()
    reviewed_at: datetime | None = None

    @model_validator(mode="after")
    def _supported_requires_evidence(self) -> Self:
        """No uncited `supported`. The product's central promise, so a hard invariant.

        A row the agent believes is satisfied but cannot cite is `PARTIALLY_SUPPORTED`, which
        sends it to the reviewer instead of quietly counting towards a `go`.
        """
        if (
            self.status is RowStatus.SUPPORTED
            and not self.evidence
            and not self.attached_doc_ids
        ):
            raise ValueError(
                "a row with status 'supported' must carry at least one evidence citation or "
                "an attached document; use 'partially_supported' when nothing can be cited"
            )
        return self

    @model_validator(mode="after")
    def _override_needs_a_reason(self) -> Self:
        """An override without a reason is unauditable, and the reviewer is the audit trail."""
        if self.reviewer_status is ReviewerStatus.OVERRIDDEN and not self.override_reason:
            raise ValueError("an overridden row must record override_reason")
        return self
