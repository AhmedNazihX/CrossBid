"""What a tender demands of a bidder.

A `Requirement` is one obligation, quoted verbatim from the source-language document with the
page it came from, so the reviewer can always open the paragraph the agent read.

Three of the fields here exist because the SP.1 spike measured what happens without them
(ADR-0003) — `stage`, `checkable`, and `threshold`. They are not speculative.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from crossbid.models.ecertis_criteria import EcertisCriterionId

MAX_QUOTE_CHARS = 2000


class RequirementSource(StrEnum):
    """Which kind of artefact the requirement was read out of.

    Three, because each is read in a completely different way and a reviewer must be able
    to tell them apart at a glance. A `TENDER_DOCUMENT` row is a verbatim quote a model
    found on a numbered page of a PDF and that was checked against that page. An
    `ESPD_REQUEST` row is a criterion the buyer *declared* in machine-readable form in a
    published DUME — no model, no inference, no page — and it is the only kind that arrives
    with an `ecertis_criterion_id` nobody had to guess (S2.5.1). A `NOTICE` row is a fact
    the buyer published in TED's own structured fields — the deadline, the languages a
    tender may be written in, a stated selection criterion — read out of JSON rather than
    out of prose, and therefore also with no page and no model (S3.2.2). It carries no
    criterion id either: a notice states criteria in words, and ADR-0007 forbids inferring
    an id from wording.
    """

    TENDER_DOCUMENT = "tender_document"
    ESPD_REQUEST = "espd_request"
    NOTICE = "notice"


class RequirementCategory(StrEnum):
    """Which part of the qualification decision this requirement belongs to."""

    FORMAL = "formal"
    ECONOMIC_FINANCIAL = "economic_financial"
    TECHNICAL_PROFESSIONAL = "technical_professional"
    EXCLUSION_GROUND = "exclusion_ground"
    OTHER = "other"


class RequirementKind(StrEnum):
    """How badly non-compliance hurts."""

    MANDATORY = "mandatory"
    OPTIONAL = "optional"
    INFORMATIONAL = "informational"


class RequirementStage(StrEnum):
    """When the obligation bites.

    The test is: *would the company still have to do this if it never won the contract?*
    If no, it is `CONTRACT_PERFORMANCE` and it does not belong in a go/no-go matrix.

    Without this discriminator the SP.1 spike extracted 579 "mandatory" requirements from one
    tender, because the AGB, EVB-IT, VOL/B, framework agreement and data-processing agreement
    are all genuinely phrased as obligations. Adding it cut the set to 238 with no loss of
    recall (ADR-0003).
    """

    BID_ELIGIBILITY = "bid_eligibility"
    CONTRACT_PERFORMANCE = "contract_performance"


class Checkability(StrEnum):
    """Whether evidence can settle this requirement at all.

    SP.1's first checking round returned `unclear` for all eight rows it tried, because they
    were all document-submission duties and no corpus of company facts can establish "we
    submitted form X". Only `COMPANY_PROPERTY` rows are worth spending tool calls on;
    `DOCUMENT_SUBMISSION` rows go to the reviewer as "attach this" (ADR-0003).
    """

    COMPANY_PROPERTY = "company_property"
    DOCUMENT_SUBMISSION = "document_submission"
    NEITHER = "neither"


class ThresholdComparator(StrEnum):
    """How a measured value is compared with the required one."""

    AT_LEAST = "at_least"
    AT_MOST = "at_most"
    MAX_AGE = "max_age"
    EQUALS = "equals"


class ThresholdUnit(StrEnum):
    """What is being measured. Closed, because a free-text unit cannot be compared."""

    CURRENCY = "currency"
    FTE = "fte"
    HEADCOUNT = "headcount"
    PERSON_DAYS = "person_days"
    REFERENCES = "references"
    YEARS = "years"
    PERCENT = "percent"


class Threshold(BaseModel):
    """A number the bidder must clear.

    Every quantified requirement in the German fixture reduced to one of these — turnover
    >= EUR 3,000,000 per year, >= 29 FTE, >= 25 person-days, references no older than 3 years.
    Keeping it typed is what lets the scorer compare rather than ask a model to judge.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    comparator: ThresholdComparator
    value: float
    unit: ThresholdUnit
    currency: str | None = Field(
        default=None,
        description="ISO 4217 code, set only when unit is CURRENCY",
        min_length=3,
        max_length=3,
    )
    period: str | None = Field(
        default=None, description="e.g. 'per_year', 'last_three_fiscal_years'"
    )


class Requirement(BaseModel):
    """One obligation, with the evidence trail back to the page it was read from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    bid_id: str

    category: RequirementCategory
    kind: RequirementKind
    stage: RequirementStage
    checkable: Checkability

    source: RequirementSource = RequirementSource.TENDER_DOCUMENT
    """Which artefact this was read out of, and therefore how far the citation reaches.
    Defaulted, because extraction produces the overwhelming majority of rows."""

    source_text: str = Field(
        max_length=MAX_QUOTE_CHARS,
        description="Verbatim quote in the tender's own language. Never paraphrased.",
    )
    source_lang: str = Field(min_length=2, max_length=5, description="BCP 47, e.g. 'de'")
    document_name: str = Field(description="File the quote came from, for the citation")
    page: int | None = Field(
        default=None,
        ge=1,
        description=(
            "1-indexed, so it matches what the PDF viewer shows. Null for an ESPD request: "
            "a DUME is XML and has no pages, and the criterion id is its locator instead."
        ),
    )

    translation: str | None = Field(
        default=None, description="Bidder-language rendering; None until translated"
    )

    # Typed against the generated eCertis Literal (S1.1.3), so the extractor cannot invent an
    # id. Nullable because most requirements map to no ESPD criterion at all.
    ecertis_criterion_id: EcertisCriterionId | None = None

    threshold: Threshold | None = None
    deadline: date | None = None

    @model_validator(mode="after")
    def _the_citation_matches_the_source(self) -> Self:
        """A page exactly when the source has pages. Both directions, and both matter.

        A quote extracted from a PDF without a page cites nothing a reviewer can open, and
        that is the product's central promise. The other direction is the one S2.5.1 had to
        decide: an ESPD criterion carries no page, and giving it one — 1, or the criterion's
        position in the file — would render in the workspace as `DUME_acheteur.xml p. 1`, a
        citation that looks followable and is not. A citation a reviewer cannot follow is
        worse than none, so the row says `page: null` and names its criterion instead.

        **The rule is "only a tender document has a page", not "an ESPD request has none".**
        It read the second way until S3.2.2 added a third source, and a notice read out of
        TED's JSON has no page for exactly the reason a DUME has none. Stated as a property
        of the sources that *do* paginate, the next structured source is a name on the
        tuple below rather than another exception (migration 0008 says the same in SQL).
        """
        has_pages = self.source is RequirementSource.TENDER_DOCUMENT
        if has_pages and self.page is None:
            raise ValueError(
                "a requirement read from a tender document must carry the page it was read "
                "from; only a structured source (an ESPD request, a TED notice) has no page"
            )
        if not has_pages and self.page is not None:
            raise ValueError(
                f"a requirement read from {self.source.value} must not carry a page: it is "
                "structured data with no pages, and a page a reviewer cannot open is a "
                "false citation"
            )
        return self
