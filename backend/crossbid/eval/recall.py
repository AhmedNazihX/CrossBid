"""S3.2.3 — recall on one tender, and the four lists a person has to adjudicate.

The story folded S6.4's human verification into this script (user decision, 2026-09-12), so
a `TenderScore` carries more than a number. `tests/unit/test_golden_labels.py` already proves
the mechanical half of an answer key: every quote is verbatim on the page it cites, every
criterion id is one eCertis knows, no document was passed over in silence. What a machine
cannot see is whether a row is really a requirement, whether its judgement fields are right,
and — the failure a verbatim check is structurally blind to — **what is missing**. So
scoring produces, per tender:

- `missed`: scored labels no extracted row evidences. The recall misses.
- `candidates`: extracted rows no label explains. Either false positives or obligations the
  labeller never wrote down; a person decides which, and that is the S6.4 judgement.
- `leaks`: matched pairs whose `stage` disagrees. In practice this can only mean the
  extractor emitted a `contract_performance` duty, because `extract_reqs` filters to
  `MATRIX_STAGE` before anything leaves the node — which is exactly why the DE file carries
  36 `contract_performance` labels beside its 177 scored rows, deliberately (ADR-0015): they
  let the filter be scored in both directions instead of only one.
- `disagreements`: matched pairs whose `kind` or `ecertis_criterion_id` differ.

**The denominator is one function with a name, not an inline filter**, because getting it
wrong is silent: dropping the stage filter would put 34 rows the extractor is forbidden to
produce into the DE denominator, moving the number by a fifth, and nothing about the output
would look wrong. The counts here are as of the 2026-09-13 answer key and are pinned by
`DE_MANDATORY_LABELS` / `DE_DENOMINATOR` in `tests/unit/test_recall_script.py`; read those
rather than trusting this paragraph.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

from crossbid.agent.nodes.extract_reqs import MATRIX_STAGE
from crossbid.eval.extraction import ExtractionResult, load_extraction
from crossbid.eval.matching import Match, match_all
from crossbid.models.golden import GoldenFile, GoldenRequirement, load_golden
from crossbid.models.requirement import Requirement, RequirementKind

SCORED_KIND: Final = RequirementKind.MANDATORY
"""The story's number is recall on *mandatory* requirements. An optional or informational
label is still matched and still reported on — it just does not move the score."""

NO_CRITERION: Final = "none"
"""How an absent `ecertis_criterion_id` prints in a disagreement, so that "the label has one
and the extractor does not" reads as a row rather than as a blank."""


class DisagreementField(StrEnum):
    """The judgement fields a matched pair can differ on and a reviewer must settle.

    `stage` is absent on purpose: a stage difference is reported as a leak instead, because
    it can only ever mean one thing (`extract_reqs` emits nothing but `MATRIX_STAGE`) and
    listing it twice would make the reviewer read the same row in two places.
    """

    KIND = "kind"
    CRITERION = "ecertis_criterion_id"


@dataclass(frozen=True)
class Disagreement:
    """One matched pair, one field, and the two answers."""

    match: Match
    field: DisagreementField
    label_value: str
    extracted_value: str

    @property
    def label(self) -> GoldenRequirement:
        return self.match.label


@dataclass(frozen=True)
class TenderScore:
    """What one tender's extraction scored, and everything left for a person to judge."""

    golden: GoldenFile
    extraction: ExtractionResult
    threshold: float
    scored: tuple[GoldenRequirement, ...]
    found: tuple[Match, ...]
    missed: tuple[GoldenRequirement, ...]
    candidates: tuple[Requirement, ...]
    leaks: tuple[Match, ...]
    disagreements: tuple[Disagreement, ...]

    @property
    def recall(self) -> float:
        """Share of the scored labels an extracted row evidences. `scored` is never empty:
        `score_tender` refuses a file with nothing to score rather than printing 1.00."""
        return len(self.found) / len(self.scored)

    @property
    def passes(self) -> bool:
        """At the threshold, not merely above it: 0.9 is the plan's figure for S3.2.1."""
        return self.recall >= self.threshold

    @property
    def fixture_name(self) -> str:
        return self.extraction.fixture_name


def scored_labels(golden: GoldenFile) -> tuple[GoldenRequirement, ...]:
    """The recall denominator: mandatory labels that bind the bidder at qualification time.

    **Both filters matter, and the stage one is the easy one to forget.** `extract_reqs`
    lets only `MATRIX_STAGE` rows leave the node (ADR-0003: without the discriminator one
    German pack yields 579 "mandatory" requirements, because the AGB, EVB-IT, VOL/B and the
    data-processing agreement are all genuinely phrased as obligations). A
    `contract_performance` label is therefore something the extractor *must not* produce, so
    counting one against recall would penalise it for working correctly — and the DE file
    carries 36 `contract_performance` labels on purpose (ADR-0015), 34 of them mandatory,
    beside its 177 scored rows. Forget the filter and those 34 join the denominator as
    permanent misses: the number moves and nothing about the output looks wrong.

    `conditional_not_scored` is excluded by reading `golden.requirements` rather than
    `golden.entries`: those bind a Bietergemeinschaft, an Eignungsleihe or a subcontractor,
    and the base case is a single bidder submitting alone (SP.1).
    """
    return tuple(
        entry
        for entry in golden.requirements
        if entry.kind is SCORED_KIND and entry.stage is MATRIX_STAGE
    )


def _disagreements_of(match: Match) -> tuple[Disagreement, ...]:
    """Every judgement field this matched pair answers differently."""
    label, row = match.label, match.requirement
    found: list[Disagreement] = []
    if label.kind is not row.kind:
        found.append(
            Disagreement(
                match=match,
                field=DisagreementField.KIND,
                label_value=label.kind.value,
                extracted_value=row.kind.value,
            )
        )
    if label.ecertis_criterion_id != row.ecertis_criterion_id:
        found.append(
            Disagreement(
                match=match,
                field=DisagreementField.CRITERION,
                label_value=label.ecertis_criterion_id or NO_CRITERION,
                extracted_value=row.ecertis_criterion_id or NO_CRITERION,
            )
        )
    return tuple(found)


def score_tender(
    golden: GoldenFile, extraction: ExtractionResult, *, threshold: float
) -> TenderScore:
    """Score one tender and assemble the reviewer's lists.

    Matching runs against **every** entry — optional, informational and conditional included
    — while recall is counted over `scored_labels` alone. That split is what keeps a row
    quoting an informational label out of the candidate-missing-label list: it is explained,
    it just does not score.
    """
    scored = scored_labels(golden)
    if not scored:
        raise ValueError(
            f"{golden.meta.fixture_dir}: no mandatory bid-eligibility labels to score against"
        )

    index = match_all(golden.entries, extraction.requirements)
    scored_ids = {entry.id for entry in scored}
    found = tuple(match for match in index.matches if match.label.id in scored_ids)
    found_ids = {match.label.id for match in found}
    return TenderScore(
        golden=golden,
        extraction=extraction,
        threshold=threshold,
        scored=scored,
        found=found,
        missed=tuple(entry for entry in scored if entry.id not in found_ids),
        candidates=index.unmatched_requirements,
        leaks=tuple(
            match for match in index.matches if match.label.stage is not match.requirement.stage
        ),
        disagreements=tuple(
            disagreement for match in index.matches for disagreement in _disagreements_of(match)
        ),
    )


def score_paths(
    paths: Iterable[Path], *, backend_dir: Path, threshold: float
) -> tuple[TenderScore, ...]:
    """Score every saved extraction result, each against the golden file it names."""
    scores: list[TenderScore] = []
    for path in paths:
        extraction = load_extraction(path)
        scores.append(
            score_tender(
                load_golden(extraction.golden_path(backend_dir)),
                extraction,
                threshold=threshold,
            )
        )
    return tuple(scores)


def exit_code_for(scores: Sequence[TenderScore]) -> int:
    """0 when every tender clears the threshold, 1 otherwise.

    No scores at all is a failure, not a pass: a run that read nothing has not shown that
    extraction is good enough, and a green exit code would say it had.
    """
    return 0 if scores and all(score.passes for score in scores) else 1
