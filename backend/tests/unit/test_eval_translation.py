"""S7.1 — translation adequacy: the sampling and the arithmetic, not the judge.

What GEval decides is measured live and elsewhere; what is pinned here is everything around
it, including the two rules that decide whether the number means anything: which rows are
eligible to be scored, and which rows get sampled.

The eligibility rule is the one with teeth. `translation` is nullable by design — a row whose
bidder language *is* the source language has nothing to translate, and an ESPD row is a
criterion id rather than prose — so treating an absent translation as a failure would have
reported the FR pack's 30 DUME rows as thirty translation defects.
"""

from __future__ import annotations

from datetime import date

import pytest

from crossbid.eval.extraction import ExtractionMeta, ExtractionResult, ExtractionSource
from crossbid.eval.translation import (
    DEFAULT_SAMPLE,
    EVALUATION_STEPS,
    THRESHOLD,
    CaseScore,
    TranslationCase,
    TranslationScore,
    sample_cases,
    score_of,
    translated_rows,
)
from crossbid.models.requirement import RequirementSource
from tests.conftest import requirement


def extraction(*rows: object) -> ExtractionResult:
    return ExtractionResult(
        meta=ExtractionMeta(
            fixture_dir="tests/fixtures/tenders/de",
            source=ExtractionSource.LIVE_RUN,
            produced_on=date(2026, 9, 16),
            method="built by test_eval_translation.py",
        ),
        requirements=tuple(rows),  # type: ignore[arg-type]
    )


def case(identifier: str = "r1") -> TranslationCase:
    return TranslationCase(
        requirement_id=identifier,
        source_text="Le candidat doit justifier d'un chiffre d'affaires de 3 000 000 EUR.",
        translation="Der Bieter muss einen Umsatz von 3.000.000 EUR nachweisen.",
        source_lang="fr",
        document_name="RC.pdf",
        page=7,
    )


# --------------------------------------------------------------- which rows may be scored


def test_a_row_with_no_translation_is_not_eligible_rather_than_a_failure() -> None:
    translated = requirement("Umsatz 3 Mio", translation="Turnover EUR 3m")
    espd = requirement(
        "Chiffre d'affaires annuel général",
        page=None,
        source=RequirementSource.ESPD_REQUEST,
        document_name="DUME_acheteur.xml",
    )

    eligible = translated_rows(extraction(translated, espd))

    assert eligible == (translated,)


def test_a_case_refuses_to_be_built_from_a_row_with_nothing_to_score() -> None:
    with pytest.raises(ValueError, match="no translation"):
        TranslationCase.of(requirement("Umsatz", translation=None))


# ---------------------------------------------------------------------------- the sample


def test_the_sample_is_spread_across_documents_rather_than_taken_in_file_order() -> None:
    """Thirty rows in file order would all come from the first documents of a 29-document
    pack, and the mean would describe those rather than the tender."""
    rows = [
        requirement(f"Klausel {index}", translation=f"Clause {index}", document_name=name)
        for name in ("a.pdf", "b.pdf", "c.pdf")
        for index in range(10)
    ]

    sampled = sample_cases(extraction(*rows), limit=3)

    assert len({entry.document_name for entry in sampled}) == 3


def test_the_sample_is_the_same_on_every_run() -> None:
    rows = [
        requirement(f"Klausel {index}", translation=f"Clause {index}", document_name="a.pdf")
        for index in range(20)
    ]
    result = extraction(*rows)

    assert sample_cases(result, limit=5) == sample_cases(result, limit=5)


def test_a_sample_larger_than_the_population_returns_the_population() -> None:
    rows = [requirement("Klausel", translation="Clause", document_name="a.pdf")]

    assert len(sample_cases(extraction(*rows), limit=DEFAULT_SAMPLE)) == 1


def test_a_result_with_nothing_translated_samples_nothing() -> None:
    assert sample_cases(extraction(requirement("Klausel", translation=None))) == ()


# ------------------------------------------------------------------------- the arithmetic


def test_the_mean_is_none_when_nothing_was_scored_not_zero() -> None:
    empty = TranslationScore(fixture_name="de", judge="j", scored=(), translated=0)

    assert empty.mean is None


def test_rows_below_the_threshold_come_back_worst_first() -> None:
    scored = TranslationScore(
        fixture_name="fr",
        judge="google/gemini-2.5-flash-lite",
        translated=114,
        scored=(
            CaseScore(case=case("a"), score=0.9, reason="ok"),
            CaseScore(case=case("b"), score=0.3, reason="added a duty"),
            CaseScore(case=case("c"), score=0.4, reason="widened the scope"),
        ),
    )

    assert scored.mean == pytest.approx(0.5333, abs=1e-3)
    assert [entry.score for entry in scored.inadequate] == [0.3, 0.4]
    assert scored.scored[0].adequate
    assert not scored.scored[1].adequate


def test_a_score_exactly_at_the_threshold_counts_as_adequate() -> None:
    assert CaseScore(case=case(), score=THRESHOLD, reason="borderline").adequate


def test_the_mean_over_a_mapping_skips_cases_the_judge_never_returned() -> None:
    cases = (case("a"), case("b"))

    assert score_of({"a": 1.0}, cases) == 1.0
    assert score_of({}, cases) is None


# ------------------------------------------------------------------------------ the rubric


def test_the_rubric_still_penalises_a_flipped_modality() -> None:
    """The rewrite of these steps relaxed one thing only — making an elided subject explicit.
    Modality, numbers and invented duties all stayed failures, and that is what keeps the
    rewrite a correction rather than a way of raising the number."""
    joined = " ".join(EVALUATION_STEPS).lower()

    assert "modality is preserved" in joined
    assert "invents a duty" in joined
    assert "changed threshold" in joined


def test_a_document_that_runs_out_of_rows_does_not_stop_the_others() -> None:
    """Real packs are uneven: the DE pack has 29 documents and its labels are not spread
    evenly across them. The round-robin has to keep dealing from the documents that still
    have rows once the short ones are exhausted, or the sample silently truncates at the
    length of the smallest document."""
    rows = [
        requirement(f"Lange {index}", translation=f"Long {index}", document_name="long.pdf")
        for index in range(4)
    ] + [requirement("Kurz", translation="Short", document_name="short.pdf")]

    sampled = sample_cases(extraction(*rows), limit=5)

    assert len(sampled) == 5
    assert sum(1 for entry in sampled if entry.document_name == "short.pdf") == 1
