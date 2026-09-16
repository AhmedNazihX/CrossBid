"""The text `scripts/recall.py` prints: a number, and four lists a person adjudicates.

This is the deliverable half of S3.2.3's amendment. Nobody is going to re-read 449 labels to
verify S6.4, so the report's job is to put in front of a reviewer exactly the rows where a
judgement is owed, with enough context — the document, the page, the quote — to decide
without opening the PDF, and in the order that matters: what recall is, then what was missed,
then what might be an unlabelled obligation, then the disagreements.

Two rules about what is printed. A section with nothing in it does not appear at all: a list
is only useful if everything on it needs an answer. And a quote is excerpted at
`QUOTE_EXCERPT_CHARS` — a 2000-character clause would bury the list it is an item of.

The closing block tells the reviewer what to do with their conclusions, because the report is
the artefact they have in front of them and a docstring in the repo is not.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from crossbid.eval.extraction import ExtractionSource
from crossbid.eval.matching import Match
from crossbid.eval.recall import Disagreement, TenderScore
from crossbid.models.golden import GoldenRequirement
from crossbid.models.requirement import Requirement, RequirementKind

TITLE: Final = "recall · S3.2.3 — extraction scored against the golden answer keys"
NOTHING_SCORED: Final = "No extraction results were read, so nothing was scored."

MISSES_HEADING: Final = "MISSES — scored labels no extracted row evidences"
CANDIDATES_HEADING: Final = "CANDIDATE MISSING LABELS — extracted rows no label explains"
LEAKS_HEADING: Final = "STAGE-FILTER LEAKS — matched pairs whose stage disagrees"
DISAGREEMENTS_HEADING: Final = "DISAGREEMENTS — matched pairs whose judgement fields differ"

SYNTHETIC_WARNING: Final = (
    "SYNTHETIC INPUT — these rows were built from the answer key by "
    "scripts/build_extraction_fixtures.py, not extracted. The figure below exercises the "
    "script; it measures nothing."
)
"""Named rather than described: "built by hand" was true until the generator was committed
(ADR-0078), and a reader who wants to check the claim can now run the thing that made it."""

CLOSING_S6_4: Final = "How a reviewer closes S6.4"
CLOSING_BODY: Final = (
    "Adjudicate the lists above — a candidate is either a false positive or a label that\n"
    "was missed, a disagreement is either a mislabelled field or a wrong extraction. Add\n"
    "or correct entries in tests/fixtures/tenders/<fixture>/golden.yaml, keeping every\n"
    "quote verbatim (tests/unit/test_golden_labels.py re-derives them from the PDFs).\n"
    "Then, in each file's `meta`, set labelled_by: llm_assisted_human_verified,\n"
    "verified_by: <your name> and verified_on: <the date>. That, and only that, closes\n"
    "S6.4 — and with it S3.2.1's recall criterion and Milestone 1."
)

QUOTE_EXCERPT_CHARS: Final = 200
ELLIPSIS: Final = " …"
INDENT: Final = "    "

_KIND_ORDER: Final = tuple(RequirementKind)
"""Mandatory first, then optional, then informational — the enum's own declaration order,
read rather than restated so a new member cannot make this table stale."""


def _excerpt(text: str) -> str:
    """One line of quote: whitespace collapsed, cut at `QUOTE_EXCERPT_CHARS`."""
    flat = " ".join(text.split())
    if len(flat) <= QUOTE_EXCERPT_CHARS:
        return flat
    return flat[:QUOTE_EXCERPT_CHARS] + ELLIPSIS


def _section(heading: str, rows: Sequence[Sequence[str]]) -> list[str]:
    """A heading with its count, then the rows — or nothing at all when there are none."""
    if not rows:
        return []
    lines = [f"  {heading} ({len(rows)})"]
    for row in rows:
        lines.extend(f"{INDENT}{line}" for line in row)
    return [*lines, ""]


def _label_lines(entry: GoldenRequirement) -> list[str]:
    return [
        f"{entry.id}  {entry.doc} p.{entry.page}  {entry.kind.value}/{entry.category.value}",
        f'  "{_excerpt(entry.quote)}"',
        f"  → {entry.summary}",
    ]


def _row_lines(row: Requirement) -> list[str]:
    return [
        f"{row.document_name} p.{row.page}  {row.kind.value}/{row.category.value}",
        f'  "{_excerpt(row.source_text)}"',
    ]


def _leak_lines(leak: Match) -> list[str]:
    return [
        f"{leak.label.id}  {leak.label.doc} p.{leak.label.page}  "
        f"golden {leak.label.stage.value} ≠ extracted {leak.requirement.stage.value}",
        f'  "{_excerpt(leak.label.quote)}"',
    ]


def _disagreement_lines(disagreement: Disagreement) -> list[str]:
    label = disagreement.label
    return [
        f"{disagreement.field.value}  {label.id}  {label.doc} p.{label.page}  "
        f"golden {disagreement.label_value} ≠ extracted {disagreement.extracted_value}",
        f'  "{_excerpt(label.quote)}"',
    ]


def _headline(score: TenderScore) -> list[str]:
    """Which tender, how good, and against what — the four lines above every list."""
    meta, extraction = score.golden.meta, score.extraction.meta
    verdict = "PASS" if score.passes else "FAIL"
    unscored = len(score.golden.entries) - len(score.scored)
    lines = [
        f"{score.fixture_name} · {meta.ted_publication_number} · {meta.fixture_dir}",
        f"  recall {score.recall:.2f}  ({len(score.found)} of {len(score.scored)} mandatory "
        f"bid-eligibility labels)  threshold {score.threshold:.2f}  {verdict}",
        f"  labels     {len(score.golden.entries)} in the file · {len(score.scored)} scored · "
        f"{unscored} not scored (optional, informational, contract_performance, conditional)",
        f"  extracted  {len(score.extraction.requirements)} rows · "
        f"{len(score.extraction.problems)} problems · {extraction.source.value} "
        f"{extraction.produced_on.isoformat()} · labels {meta.labelled_by.value}",
    ]
    if extraction.source is ExtractionSource.SYNTHETIC:
        lines.append(f"  {SYNTHETIC_WARNING}")
    return [*lines, ""]


def _tender(score: TenderScore) -> list[str]:
    """One tender: the headline, then the reviewer's four lists in order of consequence."""
    candidates = sorted(
        score.candidates,
        key=lambda row: (_KIND_ORDER.index(row.kind), row.document_name, row.page),
    )
    disagreements = sorted(
        score.disagreements, key=lambda item: (item.field.value, item.label.id)
    )
    return [
        *_headline(score),
        *_section(MISSES_HEADING, [_label_lines(entry) for entry in score.missed]),
        *_section(CANDIDATES_HEADING, [_row_lines(row) for row in candidates]),
        *_section(LEAKS_HEADING, [_leak_lines(leak) for leak in score.leaks]),
        *_section(DISAGREEMENTS_HEADING, [_disagreement_lines(item) for item in disagreements]),
    ]


def render(scores: Sequence[TenderScore]) -> str:
    """The whole report, one tender after another, with the S6.4 instructions at the end."""
    if not scores:
        return NOTHING_SCORED
    lines = [TITLE, ""]
    for score in scores:
        lines.extend(_tender(score))
    return "\n".join([*lines, CLOSING_S6_4, CLOSING_BODY])
