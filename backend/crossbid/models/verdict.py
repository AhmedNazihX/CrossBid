"""The go/no-go recommendation. Rules only — never a model's opinion.

Two scoring shapes, both taken from real tenders in the golden set:

* **Pass/fail minima** (the German federal fixture): any unmet mandatory requirement or live
  exclusion ground is fatal.
* **Weighted threshold** (the French ministry fixture): selection criteria score points on a
  scale, and the bidder is eliminated below a published cut-off — 5 of 10 in that tender.

The weights belong to the buyer and are published in the tender, so this is still a rules
engine. It is not the numeric verdict *score* that the plan deliberately cut (ADR-0006).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Decision(StrEnum):
    """The recommendation, in the design system's fixed vocabulary (ADR-0013).

    Advisory only -- a human confirms before it is final. `insufficient_evidence` is the
    agent declining to judge: nothing blocks the bid, but the documents do not settle enough
    rows for a recommendation either way.
    """

    GO = "go"
    CONDITIONAL = "conditional"
    NO_GO = "no_go"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class GapSeverity(StrEnum):
    """Whether a gap can still be closed before the deadline."""

    BLOCKING = "blocking"
    OPEN_ITEM = "open_item"


class Gap(BaseModel):
    """One reason the bidder does not yet qualify, in terms they can act on."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    requirement_id: str
    severity: GapSeverity
    summary: str = Field(description="What is missing, in the bidder's language")
    required: str | None = Field(default=None, description="e.g. '29 FTE'")
    actual: str | None = Field(default=None, description="e.g. '21 FTE'")


class WeightedScore(BaseModel):
    """A buyer's published points scale, when the tender uses one.

    Present only for tenders that score selection; absent for pass/fail tenders. `threshold`
    is the buyer's elimination cut-off, not ours.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    points: float = Field(ge=0)
    points_available: float = Field(gt=0)
    threshold: float = Field(ge=0, description="Below this the buyer eliminates the bid")

    @model_validator(mode="after")
    def _points_within_scale(self) -> Self:
        if self.points > self.points_available:
            raise ValueError("points cannot exceed points_available")
        if self.threshold > self.points_available:
            raise ValueError("threshold cannot exceed points_available")
        return self

    @property
    def clears_threshold(self) -> bool:
        return self.points >= self.threshold


class Verdict(BaseModel):
    """The scorer's output: a decision, and every reason behind it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: Decision
    gaps: tuple[Gap, ...] = ()
    score: WeightedScore | None = None

    rationale: str = Field(description="Plain-language explanation, in the bidder's language")
    mandatory_total: int = Field(ge=0)
    mandatory_supported: int = Field(ge=0)
    partially_supported_rows: int = Field(ge=0)

    @model_validator(mode="after")
    def _decision_matches_the_gaps(self) -> Self:
        """The decision must follow from the evidence, or the rules engine has a bug.

        `readmodel/` is a projection and may disagree with a checkpoint, but a verdict that
        contradicts its own gap list is never legitimate.
        """
        if self.mandatory_supported > self.mandatory_total:
            raise ValueError("mandatory_supported cannot exceed mandatory_total")

        blocking = [g for g in self.gaps if g.severity is GapSeverity.BLOCKING]
        if blocking and self.decision is not Decision.NO_GO:
            raise ValueError(
                f"decision is '{self.decision}' but {len(blocking)} blocking gap(s) are "
                "listed; a blocking gap means no_go"
            )
        if self.decision is Decision.NO_GO and not blocking:
            raise ValueError("decision is 'no_go' but no blocking gap explains why")
        if self.decision is Decision.GO and (self.gaps or self.partially_supported_rows):
            raise ValueError(
                "decision is 'go' but open items or partially supported rows remain; "
                "use 'conditional'"
            )
        if self.decision is Decision.GO and not self.mandatory_total:
            # A matrix with no mandatory requirement in it has established nothing, so a
            # clean one is not a pass: extraction that found none is the likelier reading
            # than a tender that asks for none (S3.4.1, rule 4).
            raise ValueError(
                "decision is 'go' but no mandatory requirement was scored; a bid cannot "
                "qualify on an empty matrix -- use 'insufficient_evidence'"
            )
        is_declining = self.decision is Decision.INSUFFICIENT_EVIDENCE
        if is_declining and self.partially_supported_rows == 0 and self.mandatory_total > 0:
            raise ValueError(
                "decision is 'insufficient_evidence' but every row is settled; nothing is "
                "insufficient -- use 'go', 'conditional' or 'no_go'"
            )
        if self.score is not None and not self.score.clears_threshold and blocking == []:
            raise ValueError(
                "the weighted score is below the buyer's threshold but no blocking gap "
                "records it"
            )
        return self
