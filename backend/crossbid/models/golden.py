"""S6.4 — the shape of a golden tender's labels, and the loader that refuses a bad one.

A golden file is the answer key S3.2.3 scores extraction against: for one fixture tender,
every obligation a bidder must satisfy, each with the document, the page and the *verbatim*
source-language sentence it was read from. It is a fixture, not a runtime artefact — nothing
in the request path imports this module — but it is typed here rather than parsed ad hoc in
the scorer because a wrong page or an invented quote in the answer key is worse than a bug
in the thing being scored: it would silently move the number the course is graded on.

Three deliberate choices.

**The entry mirrors `Requirement`, but is not one.** `Requirement` carries a `bid_id`, a
`source_lang` per row and an id the extractor mints as a `uuid5`; none of those exist before
a bid runs. What the two do share — `RequirementCategory`, `RequirementKind`,
`RequirementStage`, `Checkability`, `Threshold`, `EcertisCriterionId` — is imported rather
than restated, so a label can never name a category the extractor cannot produce, and the
day an enum gains a member the golden files are checked against the new one.

**Provenance is part of the schema, not a comment.** `labelled_by` and `verified_by` are
fields because S6.4's acceptance criterion is about *how* the labels were made: LLM-drafted
and human-verified. A draft that has not been read by a person is not a scoring reference,
and `_verification_is_consistent` is what stops one being mistaken for a finished file — a
file that still says `verified_by: pending` may only claim `labelled_by: llm_draft`.

**Every document in the pack is accounted for.** `documents_scanned` and
`documents_excluded` are not documentation: the test asserts they partition the pack exactly,
so a document nobody looked at cannot be passed over in silence. That is the failure mode an
answer key has — recall is measured against what the key contains, so an obligation the
labeller never opened lowers nobody's score and is invisible.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Final, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from crossbid.models.ecertis_criteria import EcertisCriterionId
from crossbid.models.requirement import (
    MAX_QUOTE_CHARS,
    Checkability,
    RequirementCategory,
    RequirementKind,
    RequirementStage,
    Threshold,
)

NonEmptyStr = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]

PENDING_VERIFIER: Final = "pending"
"""`verified_by` while no person has read the file. Any other value names the verifier."""

LabelId = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2,3}-[A-Z0-9-]{2,12}$")]
"""`DE-001`, `FR-C01`. Prefixed by fixture so an id stays unambiguous once the three
files are scored together, and shaped so a typo cannot collide with a neighbour."""


class LabelSource(StrEnum):
    """How a golden file's labels were produced.

    The distinction matters because it is graded. `HAND` is SP.1's prototype: a person read
    the PDFs and typed the entries. `LLM_DRAFT` is a model's proposal that no person has
    checked — real work, but not yet an answer key. `LLM_ASSISTED_HUMAN_VERIFIED` is the
    only value S6.4 accepts as done.
    """

    LLM_DRAFT = "llm_draft"
    HAND = "hand"
    LLM_ASSISTED_HUMAN_VERIFIED = "llm_assisted_human_verified"


class GoldenMeta(BaseModel):
    """Which tender these labels are for, and how far along they are."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ted_publication_number: NonEmptyStr = Field(description="e.g. '614251-2026'")
    fixture_dir: NonEmptyStr = Field(description="Repo-relative, from `backend/`")
    source_language: str = Field(min_length=2, max_length=5, description="BCP 47")

    labelled_by: LabelSource
    verified_by: NonEmptyStr = Field(description=f"'{PENDING_VERIFIER}', or who checked it")
    verified_on: date | None = Field(default=None, description="None while pending")
    labelled_on: date
    story: NonEmptyStr

    method: NonEmptyStr = Field(
        description="Prose: how these labels were produced, honestly and specifically"
    )
    documents_scanned: tuple[NonEmptyStr, ...] = Field(
        description="Filenames actually read, whether or not they bore a requirement"
    )
    documents_excluded: Mapping[NonEmptyStr, NonEmptyStr] = Field(
        description="Filename -> one line on why it states no bidder requirement"
    )

    @model_validator(mode="after")
    def _verification_is_consistent(self) -> Self:
        """An unverified file may only claim to be a draft, and carries no verified date.

        Without this a file could say `labelled_by: llm_assisted_human_verified` while
        `verified_by` is still `pending` — which is exactly the claim S6.4's acceptance
        criterion turns on, so it is enforced rather than trusted.
        """
        if self.verified_by != PENDING_VERIFIER:
            return self
        if self.labelled_by is not LabelSource.LLM_DRAFT:
            raise ValueError(
                f"verified_by '{PENDING_VERIFIER}' but labelled_by "
                f"'{self.labelled_by}': an unverified file is a draft"
            )
        if self.verified_on is not None:
            raise ValueError(f"verified_by '{PENDING_VERIFIER}' but verified_on is set")
        return self


class GoldenRequirement(BaseModel):
    """One labelled obligation: what it is, and the page it can be read on."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: LabelId
    category: RequirementCategory
    kind: RequirementKind
    stage: RequirementStage
    checkable: Checkability

    doc: NonEmptyStr = Field(description="Filename inside the fixture's `documents/`")
    page: int = Field(ge=1, description="1-based, the page the quote is ON")
    quote: str = Field(
        min_length=1,
        max_length=MAX_QUOTE_CHARS,
        description="Verbatim source-language text, never paraphrased or translated",
    )
    summary: NonEmptyStr = Field(description="One line of English")

    ecertis_criterion_id: EcertisCriterionId | None = Field(
        default=None,
        description="Only where the ESPD mapping is determinate; None is usually right",
    )
    threshold: Threshold | None = None
    notes: str | None = Field(default=None, description="Why a judgement call went this way")


class GoldenFile(BaseModel):
    """One tender's answer key.

    `conditional_not_scored` keeps SP.1's scope decision visible instead of losing it:
    the base case is a single bidder submitting alone, so an obligation that binds only a
    Bietergemeinschaft, an Eignungsleihe or a subcontractor is recorded with the same rigour
    but kept out of the recall denominator. Deleting those entries would make the file look
    complete while quietly answering a different question.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    meta: GoldenMeta
    requirements: tuple[GoldenRequirement, ...]
    conditional_not_scored: tuple[GoldenRequirement, ...] = ()

    @property
    def entries(self) -> tuple[GoldenRequirement, ...]:
        """Every labelled entry, scored or not. What the validator walks."""
        return self.requirements + self.conditional_not_scored


def load_golden(path: Path) -> GoldenFile:
    """Read one golden YAML file, or raise `ValidationError` naming what is wrong with it."""
    return GoldenFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
