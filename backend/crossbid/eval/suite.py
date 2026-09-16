"""S7.1 — the four metrics assembled into one report a grader can read.

`scripts/run_eval.py` is a thin CLI over this, and `make eval` is a thin CLI over that. The
assembly is here rather than in the script because the interesting decisions are not the
markdown: they are what the report is allowed to claim when a piece is missing, and that is
worth testing offline.

**Nothing here runs a model or opens a database.** Every figure is read from an artefact some
earlier, paid step wrote — `tests/fixtures/extractions/*.json` from `extract_pack.py`,
`*.translation.json` from `score_translation.py`, `tests/fixtures/retrieval/*.scores.json`
from `score_retrieval.py`. Re-rendering the report is free and offline, which is what lets it
be regenerated after a wording change without spending $3.56 again.

**A missing metric is printed as missing.** The report renders whatever exists and names what
does not, rather than omitting a row and letting a reader assume it passed. That is not
hypothetical tidiness: translation adequacy for DE and EN was never measured, because the
OpenRouter key hit its spending limit partway through the suite, and a report that quietly
showed three metrics instead of four would have read as a complete evaluation.

**Provenance travels with every number.** A tender's row carries the extraction's `source`
and date, and the retrieval row carries whether its answer key was human-verified. A figure
whose provenance is unstated is the failure this project has already made once, when a
spike's 1.00 was quoted for weeks as though it measured the shipped extractor.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from crossbid.eval.extraction import ExtractionResult, ExtractionSource
from crossbid.eval.faithfulness import FaithfulnessScore
from crossbid.eval.recall import TenderScore

MISSING: Final = "not measured"
"""What a cell says when nothing produced it. Never a blank and never a dash: a reader skims
a table and a blank cell reads as zero, nothing, or fine, depending on who is reading."""

NO_KEY_VERIFICATION: Final = "draft key"
VERIFIED_KEY: Final = "verified"


@dataclass(frozen=True)
class TranslationSummary:
    """What `score_translation.py` left behind for one tender."""

    mean: float | None
    sampled: int
    translated: int
    below_threshold: int
    judge: str


@dataclass(frozen=True)
class RetrievalSummary:
    """What `score_retrieval.py` left behind for one tender."""

    means: Mapping[str, float | None]
    questions: int
    key_verified: bool
    judge: str

    @property
    def key_state(self) -> str:
        return VERIFIED_KEY if self.key_verified else NO_KEY_VERIFICATION


@dataclass(frozen=True)
class TenderReport:
    """One tender, every metric that exists for it, and what produced each."""

    name: str
    recall: TenderScore
    faithfulness: FaithfulnessScore
    translation: TranslationSummary | None = None
    retrieval: RetrievalSummary | None = None

    @property
    def extraction(self) -> ExtractionResult:
        return self.recall.extraction

    @property
    def measured(self) -> bool:
        """Whether the rows scored came from a real run rather than a hand-built fixture."""
        return self.extraction.meta.source is ExtractionSource.LIVE_RUN

    @property
    def cost_usd(self) -> float | None:
        return self.extraction.meta.cost_usd

    @property
    def elapsed_seconds(self) -> float | None:
        return self.extraction.meta.elapsed_seconds


def number(value: float | None, places: int = 3) -> str:
    """A figure, or the words that say there is no figure. Never an empty cell."""
    return MISSING if value is None else f"{value:.{places}f}"


def money(value: float | None) -> str:
    return MISSING if value is None else f"${value:.4f}"


def duration(value: float | None) -> str:
    return MISSING if value is None else f"{value:.0f} s"


def gate(score: TenderScore) -> str:
    """Pass or fail against the configured threshold, stated as a word not a tick."""
    return "PASS" if score.passes else "FAIL"


def missing_metrics(reports: Sequence[TenderReport]) -> tuple[str, ...]:
    """Every metric that no tender produced a figure for, in report order.

    Read by the script to decide the report's own honesty line, and by a test to prove the
    report cannot silently ship with three metrics where it promises four.
    """
    absent: list[str] = []
    scored_translation = (
        report.translation and report.translation.mean is not None for report in reports
    )
    if not any(scored_translation):
        absent.append("translation adequacy")
    if not any(report.retrieval for report in reports):
        absent.append("retrieval")
    return tuple(absent)


def partial_metrics(reports: Sequence[TenderReport]) -> tuple[str, ...]:
    """Metrics measured for some tenders and not others — the shape a reader mistakes for
    completeness, because the row is present and only some cells say so."""
    partial: list[str] = []
    translated = [r for r in reports if r.translation and r.translation.mean is not None]
    if translated and len(translated) != len(reports):
        names = ", ".join(sorted(r.name for r in reports if r not in translated))
        partial.append(f"translation adequacy: not measured for {names}")
    scored = [r for r in reports if r.retrieval]
    if scored and len(scored) != len(reports):
        names = ", ".join(sorted(r.name for r in reports if r not in scored))
        partial.append(f"retrieval: not measured for {names}")
    return tuple(partial)


@dataclass(frozen=True)
class PrecisionSplit:
    """Context precision, split by how many passages the agent pooled into one turn.

    The split exists because `context_precision` assumes one retrieval and the product does
    not: a ReAct agent that is unsure searches again, and every passage from every search in
    the turn lands in one list (`eval/retrieval.py` explains why it is pooled that way). Each
    extra search adds five passages, of which at most a few can be relevant, so the metric
    falls as the agent works harder. Reporting the mean alone would read as a retrieval defect.
    """

    narrow: float | None
    """Mean where the agent searched once — at most `NARROW` passages."""
    narrow_count: int
    broad: float | None
    """Mean where it searched repeatedly — `BROAD` passages or more."""
    broad_count: int


NARROW: Final = 5
"""Passages one `tender_rag_search` returns by default: one search, one question."""

BROAD: Final = 15
"""Three searches or more pooled into a single turn."""


def precision_split(
    scores: Mapping[str, float | None], counts: Mapping[str, int]
) -> PrecisionSplit:
    """Split the per-question precision by how many passages each turn pooled.

    `scores` is context precision per question id; `counts` is passages retrieved per id.
    """
    narrow = [v for qid, v in scores.items() if v is not None and counts.get(qid, 0) <= NARROW]
    broad = [v for qid, v in scores.items() if v is not None and counts.get(qid, 0) >= BROAD]
    return PrecisionSplit(
        narrow=sum(narrow) / len(narrow) if narrow else None,
        narrow_count=len(narrow),
        broad=sum(broad) / len(broad) if broad else None,
        broad_count=len(broad),
    )
