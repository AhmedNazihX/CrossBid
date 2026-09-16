"""S7.1 — translation adequacy: does the bidder's language say what the tender said?

The product's promise to a cross-border bidder is that they can read a French or German
tender in their own language and act on it. `extract_reqs` fills `Requirement.translation` in
the same call that produces the quote (decision 5 in that module), so every row carries both
halves and nothing else in the system ever checks that they agree.

**This is the one metric of the four that genuinely needs a judge.** Recall is set
arithmetic, faithfulness is a substring check, retrieval precision has an answer key — but
"does this German sentence carry the same obligation as that French clause" is a judgement,
and the only alternatives to a model are a bilingual human per row or nothing. So it is
`GEval`, DeepEval's rubric-scored judge, which is what the plan named for it.

**What is being judged is adequacy, not fluency.** A translation that reads beautifully and
turns *"doit"* into *"sollte"* has broken the product: the bidder now believes a mandatory
requirement is advisory. So the steps below score the three things that change what a bidder
would *do* — the obligation itself, its modality, and any number attached to it — and
explicitly decline to reward style. `EVALUATION_STEPS` is spelled out rather than left to
`criteria` alone because GEval otherwise writes its own steps per run, and a rubric that
changes between runs makes two reports incomparable.

**The judge is a different vendor from the model under test**, which is S7.1's rule: the
translations come from an OpenAI slug through OpenRouter, and the judge is Google's
`gemini-2.5-flash-lite`.

Rows are sampled, not scored whole: the DE run carries 311 translations and judging all of
them costs far more than the extraction did, for a mean that a stratified sample of thirty
already pins. The sample is seeded, so a re-run scores the same rows.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from crossbid.eval.extraction import ExtractionResult
from crossbid.models.requirement import Requirement

SAMPLE_SEED: Final = 20260916
"""Fixed, so two runs of the report score the same rows and their means are comparable."""

DEFAULT_SAMPLE: Final = 30

CRITERIA: Final = (
    "Determine whether the bidder-language rendering states the duty the source clause "
    "imposes, with the same force and the same numbers, for a bidder who will act on it "
    "without reading the source language."
)

EVALUATION_STEPS: Final = (
    "Read the source clause and identify the duty it places on the bidder, its modality "
    "(must / shall / should / may), and every number, currency, date or period attached to "
    "that duty.",
    "Check that the rendering states the same duty. It is written to say what the bidder "
    "must DO, so making an elided subject, condition or action explicit is correct and must "
    "not be penalised: a source bullet naming a document is adequately rendered as a "
    "sentence saying that document must be submitted.",
    "Penalise heavily only if the rendering invents a duty the source clause does not "
    "support, or drops one it does state. A narrower or wider scope than the source (for "
    "example 'for each subcontractor' where the source says nothing about how many) is an "
    "error, but a smaller one than inventing or losing the duty itself.",
    "Check that the modality is preserved. Turning a mandatory duty into an advisory one, "
    "or the reverse, is the most serious error possible here, because the bidder decides "
    "what to submit on this basis.",
    "Check every number, currency, unit and period. A changed threshold is as serious as a "
    "changed modality.",
    "Ignore style, register, fluency and word order, and do not reward or penalise "
    "literalness. A clumsy rendering that conveys the duty, its force and its numbers "
    "scores highly; an elegant one that does not scores low.",
)
"""Scored against the contract `prompts/extract.md` states, which is not literal translation.

**The first version of these steps measured the wrong thing, and it is recorded here rather
than quietly corrected.** They scored literal fidelity — "penalise if it adds a requirement
the source does not contain" — and on the FR pack that scored the extractor's *specified*
behaviour as a defect: two of the first three rows came back at 0.20 and 0.30 because the
model had turned a document-list bullet ("Le pouvoir habilitant le signataire a engager le
sous-traitant") into a sentence saying that document must be submitted. The prompt requires
exactly that: "Say what the bidder must do, not what the clause is about." A rubric that
penalises the instruction the system was given measures the rubric's author, not the system.

The steps were rewritten to the documented contract, **not** to raise the number: invention,
lost duties, flipped modality and changed figures are all still failures, and the scope error
in that same FR row is still called an error. What changed is that making an elided subject
explicit is no longer one.
"""

THRESHOLD: Final = 0.8
"""What counts as adequate for one row. Not a gate on the report — the report quotes the
mean and the rows below this — but the number the per-row pass/fail column uses."""


@dataclass(frozen=True)
class TranslationCase:
    """One row's two halves, and where a reviewer can read them side by side."""

    requirement_id: str
    source_text: str
    translation: str
    source_lang: str
    document_name: str
    page: int | None

    @classmethod
    def of(cls, row: Requirement) -> TranslationCase:
        if row.translation is None:  # pragma: no cover - callers filter first
            raise ValueError(f"{row.id}: no translation to score")
        return cls(
            requirement_id=row.id,
            source_text=row.source_text,
            translation=row.translation,
            source_lang=row.source_lang,
            document_name=row.document_name,
            page=row.page,
        )


@dataclass(frozen=True)
class CaseScore:
    """One judged row."""

    case: TranslationCase
    score: float
    reason: str

    @property
    def adequate(self) -> bool:
        return self.score >= THRESHOLD


@dataclass(frozen=True)
class TranslationScore:
    """One tender's translation adequacy: the mean, and the rows that dragged it down."""

    fixture_name: str
    judge: str
    scored: tuple[CaseScore, ...]
    translated: int
    """How many rows carried a translation at all — the population the sample came from."""

    @property
    def mean(self) -> float | None:
        """`None` when nothing was scored, never 0.0 — see `recall.py` on empty numerators."""
        if not self.scored:
            return None
        return sum(entry.score for entry in self.scored) / len(self.scored)

    @property
    def inadequate(self) -> tuple[CaseScore, ...]:
        """Below `THRESHOLD`, worst first: the reviewer's list."""
        return tuple(sorted((e for e in self.scored if not e.adequate), key=lambda e: e.score))


def translated_rows(extraction: ExtractionResult) -> tuple[Requirement, ...]:
    """Every row that carries a translation.

    A row without one is not a failure to score as zero: `extract_reqs` leaves `translation`
    empty when the bidder's language *is* the source language, and an ESPD row is a criterion
    id rather than prose. Counting those as inadequate would report the FR pack's 30 DUME
    rows as thirty translation defects.
    """
    return tuple(row for row in extraction.requirements if row.translation)


def sample_cases(
    extraction: ExtractionResult, *, limit: int = DEFAULT_SAMPLE
) -> tuple[TranslationCase, ...]:
    """`limit` rows spread across the pack's documents, deterministically.

    Spread for the same reason the retrieval key is: thirty rows drawn in file order would
    all come from the first two documents of a twenty-nine document pack, and the mean would
    describe those two.
    """
    rows = translated_rows(extraction)
    by_document: dict[str, list[Requirement]] = {}
    for row in rows:
        by_document.setdefault(row.document_name, []).append(row)

    # S311 is not a concern: this shuffle chooses which rows to judge, not a secret.
    rng = random.Random(SAMPLE_SEED)  # noqa: S311
    for entries in by_document.values():
        rng.shuffle(entries)

    spread: list[Requirement] = []
    for index in range(max((len(v) for v in by_document.values()), default=0)):
        for name in sorted(by_document):
            if index < len(by_document[name]):
                spread.append(by_document[name][index])
    return tuple(TranslationCase.of(row) for row in spread[:limit])


def score_of(scores: Mapping[str, float], cases: Sequence[TranslationCase]) -> float | None:
    """Mean over the cases a judge actually returned a number for."""
    values = [scores[case.requirement_id] for case in cases if case.requirement_id in scores]
    return sum(values) / len(values) if values else None
