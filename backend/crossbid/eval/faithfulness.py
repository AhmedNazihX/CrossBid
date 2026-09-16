"""S7.1 — citation faithfulness: is the quote really on the page the row cites?

**This metric asks no model anything, and that is the decision worth defending.** The plan
named DeepEval's `GEval` for faithfulness (project-plan.md, tech stack), which would put a
judge in front of a quote and a page and ask it to rate agreement on a 0-1 scale. For a
claim about a *summary* that is the right instrument, because agreement is a matter of
degree. For this claim it is the wrong one: "the row's `source_text` occurs on page `p` of
document `d`" is decidable, the repository already owns the decision procedure, and a judge
can only add noise and cost to an answer that is exactly true or exactly false.

So faithfulness here is `extract_reqs._is_verbatim`, the extractor's own predicate, run
again over the *parsed pack* rather than over the section the model was shown. That is not
circular. The extractor checks a quote against the one page range it had in front of it,
inside the call that produced it, and drops a row that fails (`NO_VERBATIM_QUOTE`). This
checks every surviving row against the document it *claims*, parsed independently — so it
catches the failure that check cannot see: a row attributed to the wrong document or the
wrong page, which is a citation a reviewer cannot follow and therefore the product's central
promise broken.

**Normalisation is imported, never restated** — the same rule `eval/matching.py` states. A
second definition of "verbatim" would let this metric and the extractor disagree about the
same quote, and the number would stop meaning what the extractor was measured on.

**Three sources, two of which have no page, and they are reported apart from the score.** A
`TENDER_DOCUMENT` row cites a page and is checkable here. An `ESPD_REQUEST` row cites a
canonical criterion id and an `NOTICE` row cites a TED field; neither has a page, both are
correct not to (`Requirement._the_citation_matches_the_source`), and counting them as passes
would inflate the score with rows this metric never examined. The FR pack is 30 of 144 rows
that way, so the inflation would have been a fifth of the tender.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

from crossbid.agent.nodes.extract_reqs import _is_verbatim
from crossbid.eval.extraction import ExtractionResult
from crossbid.eval.packrun import pack_paths
from crossbid.ingestion.parser import ParsedDocument, ParserError
from crossbid.ingestion.pymupdf_parser import PyMuPDFParser
from crossbid.models.requirement import Requirement, RequirementSource

PAGINATED_SOURCE: Final = RequirementSource.TENDER_DOCUMENT
"""The one source that carries a page, and therefore the one this metric can check.

Stated as a property of the source that paginates rather than as a list of the two that do
not — the same way `Requirement` states it — so that a fourth source is a decision here
rather than a silent pass.
"""


class CitationVerdict(StrEnum):
    """What checking one row's citation found.

    Four outcomes and not two, because a reviewer does different things about each. A quote
    that is not on its page is an extraction defect. A page beyond the end of the document,
    or a document that is not in the pack, is an *attribution* defect — the row was filed
    against the wrong file — and it renders in the workspace as a citation that opens the
    wrong page or nothing at all, which is worse than a wrong quote because it looks right.
    """

    FAITHFUL = "faithful"
    NOT_ON_PAGE = "not_on_page"
    NO_SUCH_PAGE = "no_such_page"
    NO_SUCH_DOCUMENT = "no_such_document"


@dataclass(frozen=True)
class CitationCheck:
    """One row, and whether the page it cites really carries the words it quotes."""

    requirement: Requirement
    verdict: CitationVerdict

    @property
    def faithful(self) -> bool:
        return self.verdict is CitationVerdict.FAITHFUL


@dataclass(frozen=True)
class FaithfulnessScore:
    """One tender's citations: what was checked, what passed, and what was not checkable."""

    checks: tuple[CitationCheck, ...]
    unpaginated: tuple[Requirement, ...]
    """Rows whose source carries no page. Not failures, and deliberately not in the score."""
    unreadable: tuple[str, ...]
    """Documents in the pack that would not parse, named so a score of 0 has a cause."""

    @property
    def faithful(self) -> tuple[CitationCheck, ...]:
        return tuple(check for check in self.checks if check.faithful)

    @property
    def failures(self) -> tuple[CitationCheck, ...]:
        return tuple(check for check in self.checks if not check.faithful)

    @property
    def score(self) -> float:
        """Share of checkable citations that are verbatim on the page they name.

        A tender with nothing checkable scores 0.0 rather than 1.0: no citation was verified,
        so nothing was shown, and a perfect score for an empty check is the single most
        misleading number this file could produce.
        """
        return len(self.faithful) / len(self.checks) if self.checks else 0.0


@dataclass(frozen=True)
class _Pack:
    """The pack's PDFs, parsed once each, and the names of those that would not open."""

    documents: Mapping[str, ParsedDocument]
    unreadable: tuple[str, ...]


def _parsed_pack(pack_dir: Path, names: Sequence[str]) -> _Pack:
    """Every named PDF of the pack, parsed once.

    Parsed here rather than reused from the run: the whole point of the check is that the
    page text comes from the file independently of whatever the extractor was shown.
    """
    wanted = set(names)
    parser = PyMuPDFParser()
    parsed: dict[str, ParsedDocument] = {}
    unreadable: list[str] = []
    for path in pack_paths(pack_dir):
        if path.name not in wanted or path.suffix.lower() != ".pdf":
            continue
        try:
            parsed[path.name] = parser.parse(path.read_bytes(), document_id=path.name)
        except ParserError:
            unreadable.append(path.name)
    return _Pack(documents=parsed, unreadable=tuple(unreadable))


def _verdict_for(row: Requirement, documents: Mapping[str, ParsedDocument]) -> CitationVerdict:
    document = documents.get(row.document_name)
    if document is None:
        return CitationVerdict.NO_SUCH_DOCUMENT
    page = row.page or 0
    if not 1 <= page <= len(document.pages):
        return CitationVerdict.NO_SUCH_PAGE
    text = document.pages[page - 1].text
    return (
        CitationVerdict.FAITHFUL
        if _is_verbatim(row.source_text, text)
        else CitationVerdict.NOT_ON_PAGE
    )


def score_faithfulness(extraction: ExtractionResult, *, pack_dir: Path) -> FaithfulnessScore:
    """Check every paginated row of `extraction` against the pack it was extracted from."""
    rows = extraction.requirements
    paginated = tuple(row for row in rows if row.source is PAGINATED_SOURCE)
    pack = _parsed_pack(pack_dir, [row.document_name for row in paginated])
    return FaithfulnessScore(
        checks=tuple(
            CitationCheck(requirement=row, verdict=_verdict_for(row, pack.documents))
            for row in paginated
        ),
        unpaginated=tuple(row for row in rows if row.source is not PAGINATED_SOURCE),
        unreadable=pack.unreadable,
    )
