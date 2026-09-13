"""When an extracted requirement and a golden label describe the same obligation.

This is the heart of S3.2.3 and the part that decides the graded number, so the rule is
written down rather than tuned until it looks good.

**The rule.** A golden label and an extracted `Requirement` match when all three hold:

1. they cite the **same document** — filenames compared exactly;
2. their **pages are at most `PAGE_WINDOW` apart**;
3. their quotes share a **single unbroken run of text** that is at least
   `MIN_SHARED_CHARS` characters long and covers at least `MIN_SHARED_SPAN` of the shorter
   of the two, comparing under `extract_reqs`' own normalisation.

Quote *equality* would be wrong: the extractor is told to quote the obligation, not to guess
where the labeller cut the sentence, so it legitimately returns a longer or a shorter span of
the same clause. Containment is simply the case where the shared run covers the shorter quote
whole. Document-and-page alone would be far too loose — one page of a
Bewerbungsbedingungen carries a dozen separate duties, and crediting any of them for any
other inflates recall, which is the dangerous direction for a number a course is graded on.

**Normalisation is imported, never restated.** `extract_reqs._comparable` collapses
whitespace, strips the parser's inline markdown emphasis (`**Umsatz**`, ADR-0008) and folds
case for a sameness judgement. That is exactly the comparison `_is_verbatim` accepts a
model's citation under and `_dedupe` judges two rows the same under, and it has to be the
comparison here too: a stricter rule would demand quotes the extractor is structurally
unable to produce, and a looser one would credit it for text it never quoted.

**What deliberately does not match.**

- *A translation or a paraphrase.* Only `source_text` is compared, never `translation`. A
  golden quote is verbatim source-language text by schema; matching on the bidder-language
  rendering would credit the extractor with finding a clause it had only restated.
- *The same clause quoted from another document.* `extract_reqs._dedupe` draws the same
  line: page numbers of two files are not comparable, and one obligation cited from two
  documents is two citations, not one.
- *The same words further away in the same document.* A duty restated in a later annex is
  its own citation. One page of slack exists only because a clause broken by a page break is
  cited by whichever page each reader saw it start on.
- *A shared phrase.* Two different duties on one page routinely open with the same
  boilerplate ("Der Bieter hat mit dem Angebot"), and `MIN_SHARED_CHARS` is what stops that
  from counting. It is 20 characters, the shortest quote in any committed golden file, so
  no label is unmatchable by construction.
- *Semantic equivalence.* Nothing here understands German. Two ways of saying the same
  obligation that share no verbatim run are two obligations to this module, and the report
  hands the pair to a person instead.

**Multiplicity is asymmetric, on purpose.** One extracted row may satisfy several labels: a
single quoted enumeration genuinely carries several duties, and the question recall asks is
whether extraction surfaced the text at all. In the other direction only the best-overlapping
row is reported per label, so a reviewer reads one line per label rather than one per
coincidence — `extract_reqs._dedupe` has already run, so several rows quoting one clause is
itself unusual.
"""

from __future__ import annotations

import difflib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Final

from crossbid.agent.nodes.extract_reqs import _comparable
from crossbid.models.golden import GoldenRequirement
from crossbid.models.requirement import Requirement

PAGE_WINDOW: Final = 1
"""Pages of slack between a label's citation and an extracted row's.

One, not `extract_reqs.PAGE_PROXIMITY`'s two: that constant answers a different question
(is this a restatement of a nearby clause, to be dropped) where being generous costs a
duplicate. Here being generous costs a false credit on the graded number.
"""

MIN_SHARED_SPAN: Final = 0.6
"""How much of the shorter quote the shared run must cover.

Not the longer: the common honest case is the extractor quoting a whole paragraph that
contains the labelled sentence, where coverage of the longer text is necessarily small.
"""

MIN_SHARED_CHARS: Final = 20
"""Absolute floor on the shared run. The shortest quote in any committed golden file is 20
characters ("Anlage Unteraufträge"), so this floor excludes no label; below it the text is a
phrase rather than a clause, and phrases repeat across unrelated duties."""


@dataclass(frozen=True)
class Overlap:
    """How much verbatim text two quotes share, and whether that is enough to call it one.

    `shortest` is carried rather than recomputed so that `ratio` and `is_enough` answer from
    the same measurement a caller can print.
    """

    chars: int
    shortest: int

    @property
    def ratio(self) -> float:
        """Share of the shorter quote covered by the run; 0.0 when there is no text."""
        return self.chars / self.shortest if self.shortest else 0.0

    @property
    def is_enough(self) -> bool:
        """The quote half of the rule in the module docstring."""
        return self.chars >= MIN_SHARED_CHARS and self.ratio >= MIN_SHARED_SPAN


@dataclass(frozen=True)
class Match:
    """One golden label and the extracted row credited with finding it."""

    label: GoldenRequirement
    requirement: Requirement
    overlap: Overlap


@dataclass(frozen=True)
class MatchIndex:
    """The result of matching one tender's labels against one extraction result.

    `unmatched_requirements` is the half a verbatim check cannot see: rows the extractor
    produced that no label explains, which are either false positives or — the reason S6.4
    needs a person — obligations the labeller missed.

    There is deliberately no "unmatched labels" here. Which labels count as missed depends on
    the denominator, and only `recall.scored_labels` knows that (mandatory, bid-eligibility);
    a whole-file list beside it would be a second answer to the same question, and the wrong
    one would look just as usable.
    """

    matches: tuple[Match, ...]
    unmatched_requirements: tuple[Requirement, ...]


def quote_overlap(left: str, right: str) -> Overlap:
    """The longest run of text the two quotes share, under the extractor's normalisation.

    `autojunk=False` for the reason `extract_reqs._is_repeat` gives: the heuristic it
    disables calls any character recurring in more than 1% of a long string junk, which for
    a 2000-character legal clause is most of the alphabet.
    """
    first, second = _comparable(left), _comparable(right)
    shortest = min(len(first), len(second))
    if not shortest:
        return Overlap(chars=0, shortest=0)
    block = difflib.SequenceMatcher(None, first, second, autojunk=False).find_longest_match()
    return Overlap(chars=block.size, shortest=shortest)


def cites_same_place(label: GoldenRequirement, requirement: Requirement) -> bool:
    """Same file, and pages close enough to be the same clause. See the module docstring."""
    return (
        label.doc == requirement.document_name
        # A row read from a published ESPD request carries no page (S2.5.1). A golden label
        # is a page-anchored quote by schema, so such a row can never evidence one, and
        # scoring it against the labels would credit recall to a different kind of finding.
        and requirement.page is not None
        and abs(label.page - requirement.page) <= PAGE_WINDOW
    )


def overlap_of(label: GoldenRequirement, requirement: Requirement) -> Overlap | None:
    """The pair's overlap, or `None` when they do not even cite the same place."""
    if not cites_same_place(label, requirement):
        return None
    return quote_overlap(label.quote, requirement.source_text)


def _qualifying(
    label: GoldenRequirement, requirements: Iterable[Requirement]
) -> tuple[Match, ...]:
    """Every row that satisfies the rule for `label`, in the order the rows were given."""
    return tuple(
        Match(label=label, requirement=requirement, overlap=overlap)
        for requirement in requirements
        if (overlap := overlap_of(label, requirement)) is not None and overlap.is_enough
    )


def _best(candidates: Sequence[Match]) -> Match | None:
    """The strongest of several rows evidencing one label.

    Ties break on the nearer page and then on the row id, so two runs over the same inputs
    report the same pair and a report can be diffed.
    """
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda match: (
            -match.overlap.ratio,
            # Not None: `cites_same_place` has already refused a row without a page.
            abs((match.requirement.page or 0) - match.label.page),
            match.requirement.id,
        ),
    )


def match_all(
    labels: Sequence[GoldenRequirement], requirements: Sequence[Requirement]
) -> MatchIndex:
    """Match every label against every row, in label order.

    Each pair is judged once: the per-label candidate lists are what both the credited
    matches and the set of explained rows are read off, so the two answers cannot disagree.
    """
    hits = [_qualifying(label, requirements) for label in labels]
    explained = {match.requirement.id for group in hits for match in group}
    return MatchIndex(
        matches=tuple(best for group in hits if (best := _best(group)) is not None),
        unmatched_requirements=tuple(row for row in requirements if row.id not in explained),
    )
