"""S7.1 — what the report is allowed to claim, and what it must admit.

The markdown is not the interesting part; the honesty rules are. A report that renders three
metrics where it promises four, and says nothing, reads as a complete evaluation — and that
is exactly what would have shipped when the OpenRouter key hit its limit partway through
translation adequacy. These tests pin the two rules that stop it: a metric nothing produced
is named, and a metric measured for some tenders and not others is named as partial.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from crossbid.eval.extraction import ExtractionMeta, ExtractionResult, ExtractionSource
from crossbid.eval.faithfulness import FaithfulnessScore
from crossbid.eval.recall import TenderScore
from crossbid.eval.suite import (
    BROAD,
    MISSING,
    NO_KEY_VERIFICATION,
    VERIFIED_KEY,
    RetrievalSummary,
    TenderReport,
    TranslationSummary,
    duration,
    gate,
    missing_metrics,
    money,
    number,
    partial_metrics,
    precision_split,
)
from crossbid.models.golden import load_golden
from tests.conftest import requirement

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def extraction(source: ExtractionSource = ExtractionSource.LIVE_RUN) -> ExtractionResult:
    return ExtractionResult(
        meta=ExtractionMeta(
            fixture_dir="tests/fixtures/tenders/de",
            source=source,
            produced_on=date(2026, 9, 16),
            method="built by test_eval_suite.py",
            cost_usd=1.678,
            elapsed_seconds=294.0,
        ),
        requirements=(requirement(),),
    )


def tender_score(recall_value: float) -> TenderScore:
    golden = load_golden(FIXTURES / "tenders" / "de" / "golden.yaml")
    scored = tuple(golden.requirements[:10])
    found_count = round(recall_value * len(scored))
    return TenderScore(
        golden=golden,
        extraction=extraction(),
        threshold=0.9,
        scored=scored,
        found=tuple(object() for _ in range(found_count)),  # type: ignore[arg-type]
        missed=(),
        candidates=(),
        leaks=(),
        disagreements=(),
    )


def report(
    name: str = "de",
    *,
    recall_value: float = 0.9,
    translation: TranslationSummary | None = None,
    retrieval: RetrievalSummary | None = None,
) -> TenderReport:
    return TenderReport(
        name=name,
        recall=tender_score(recall_value),
        faithfulness=FaithfulnessScore(checks=(), unpaginated=(), unreadable=()),
        translation=translation,
        retrieval=retrieval,
    )


def translation(mean: float | None) -> TranslationSummary:
    return TranslationSummary(
        mean=mean, sampled=6, translated=114, below_threshold=2, judge="judge"
    )


def retrieval(verified: bool = False) -> RetrievalSummary:
    return RetrievalSummary(
        means={"context_recall": 0.9}, questions=30, key_verified=verified, judge="judge"
    )


# ------------------------------------------------------------------ a blank cell is banned


def test_an_absent_figure_is_words_not_an_empty_cell() -> None:
    """A blank cell reads as zero, nothing, or fine, depending on who is skimming."""
    assert number(None) == MISSING
    assert money(None) == MISSING
    assert duration(None) == MISSING


def test_a_real_figure_is_formatted_to_its_places() -> None:
    assert number(0.8312) == "0.831"
    assert number(1.0, places=4) == "1.0000"
    assert money(1.678) == "$1.6780"
    assert duration(294.0) == "294 s"


# ------------------------------------------------------------- a missing metric is named


def test_a_metric_no_tender_produced_is_reported_as_missing() -> None:
    absent = missing_metrics([report(), report("fr")])

    assert "translation adequacy" in absent
    assert "retrieval" in absent


def test_a_metric_every_tender_produced_is_not_reported_as_missing() -> None:
    reports = [
        report(translation=translation(0.7), retrieval=retrieval()),
        report("fr", translation=translation(0.8), retrieval=retrieval()),
    ]

    assert missing_metrics(reports) == ()
    assert partial_metrics(reports) == ()


def test_a_metric_measured_for_some_tenders_is_reported_as_partial() -> None:
    """The shape that reads as complete: the row is there and only some cells say otherwise.
    This is what actually happened — the key hit its limit after FR and before DE and EN."""
    reports = [report("de"), report("fr", translation=translation(0.733)), report("en")]

    partial = partial_metrics(reports)

    assert partial == ("translation adequacy: not measured for de, en",)
    assert missing_metrics(reports) == ("retrieval",)


def test_a_translation_summary_with_no_mean_counts_as_not_measured() -> None:
    """A file written by a run that judged nothing must not count as a measurement."""
    reports = [report(translation=translation(None))]

    assert "translation adequacy" in missing_metrics(reports)


def test_partial_retrieval_is_named_too() -> None:
    reports = [report("de", retrieval=retrieval()), report("fr")]

    assert partial_metrics(reports) == ("retrieval: not measured for fr",)


# ------------------------------------------------------------------------- the small stuff


def test_the_gate_is_a_word_not_a_tick() -> None:
    assert gate(tender_score(1.0)) == "PASS"
    assert gate(tender_score(0.5)) == "FAIL"


def test_a_synthetic_result_is_not_a_measurement() -> None:
    """The distinction the whole provenance column exists for (ADR-0003's 1.00)."""
    live = TenderReport(
        name="de",
        recall=tender_score(0.9),
        faithfulness=FaithfulnessScore(checks=(), unpaginated=(), unreadable=()),
    )

    assert live.measured
    assert live.cost_usd == pytest.approx(1.678)
    assert live.elapsed_seconds == pytest.approx(294.0)


def test_a_draft_answer_key_says_so() -> None:
    assert retrieval(verified=False).key_state == NO_KEY_VERIFICATION
    assert retrieval(verified=True).key_state == VERIFIED_KEY


# --------------------------------------------------------------- precision, split by effort


def test_precision_is_split_by_how_many_passages_the_turn_pooled() -> None:
    """One search and three searches are not the same measurement; see `PrecisionSplit`."""
    # Arrange
    scores = {"q1": 0.8, "q2": 0.6, "q3": 0.3, "q4": 0.1}
    counts = {"q1": 5, "q2": 4, "q3": BROAD, "q4": 20}

    # Act
    split = precision_split(scores, counts)

    # Assert
    assert split.narrow == pytest.approx(0.7)
    assert split.narrow_count == 2
    assert split.broad == pytest.approx(0.2)
    assert split.broad_count == 2


def test_a_question_between_the_two_bands_counts_in_neither() -> None:
    """Six to fourteen passages is a second search the split cannot characterise."""
    split = precision_split({"q1": 0.9}, {"q1": 9})

    assert split == precision_split({}, {})


def test_a_band_with_nothing_in_it_is_none_rather_than_zero() -> None:
    """Zero would read as perfect failure; the honest answer is that nobody measured it."""
    split = precision_split({"q1": 0.5}, {"q1": 5})

    assert split.narrow == pytest.approx(0.5)
    assert (split.broad, split.broad_count) == (None, 0)


def test_a_question_ragas_could_not_score_is_left_out_of_both_means() -> None:
    """`None` is "no score", and averaging it in as anything at all invents a measurement."""
    split = precision_split({"q1": None, "q2": 0.4}, {"q1": 5, "q2": 5})

    assert split.narrow == pytest.approx(0.4)
    assert split.narrow_count == 1


def test_a_question_with_no_recorded_count_is_treated_as_one_search() -> None:
    """`counts.get(qid, 0)` — an absent count is zero passages, which is the narrow band."""
    split = precision_split({"q1": 0.6}, {})

    assert (split.narrow_count, split.broad_count) == (1, 0)
