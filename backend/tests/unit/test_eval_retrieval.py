"""S7.1 — the retrieval score's aggregation rules, which decide what the report may claim.

Nothing here calls ragas or a judge: what those return is their business, and the two
metrics that matter were measured discriminating correctly (1.00 on the right passage, 0.00
on a wrong one) before they were wired in. What is tested here is the arithmetic around them,
because that is where a retrieval figure can be quietly wrong — an absent score averaged as a
zero turns a broken judge into a bad retriever, and both look like "0.42" in a table.
"""

from __future__ import annotations

from datetime import date

from crossbid.eval.questions import (
    QuestionSet,
    QuestionSetMeta,
    RetrievalQuestion,
    VerificationState,
)
from crossbid.eval.retrieval import (
    ANSWER_RELEVANCY,
    CONTEXT_PRECISION,
    CONTEXT_RECALL,
    FAITHFULNESS,
    METRIC_NAMES,
    REFERENCE_FREE,
    QuestionScore,
    RetrievalSample,
    RetrievalScore,
    contexts_of,
)


def question(identifier: str = "DE-Q-001") -> RetrievalQuestion:
    return RetrievalQuestion(
        id=identifier,
        label_id="DE-012",
        question="Welchen Mindestjahresumsatz verlangt die Vergabestelle?",
        reference="EUR 3,000,000 minimum annual turnover.",
        reference_contexts=("Mindestjahresumsatz von 3.000.000 EUR",),
        doc="Bewerbungsbedingungen.pdf",
        page=7,
    )


def question_set(**overrides: object) -> QuestionSet:
    base: dict[str, object] = {
        "fixture_dir": "tests/fixtures/tenders/de",
        "source_language": "de",
        "bidder_language": "de",
        "derived_from": "golden.yaml",
        "generated_by": "openai/gpt-5.6-luna",
        "generated_on": date(2026, 9, 16),
        "method": "drafted from the verified labels",
    }
    return QuestionSet(
        meta=QuestionSetMeta.model_validate(base | overrides), questions=(question(),)
    )


def sample(*contexts: str, identifier: str = "DE-Q-001") -> RetrievalSample:
    return RetrievalSample(
        question=question(identifier),
        answer="Drei Millionen Euro.",
        retrieved_contexts=contexts,
        citations=(),
    )


def score(*pairs: tuple[RetrievalSample, dict[str, float]]) -> RetrievalScore:
    return RetrievalScore(
        fixture_name="de",
        question_set=question_set(),
        scored=tuple(QuestionScore(sample=s, scores=v) for s, v in pairs),
    )


# -------------------------------------------------------- absent is not the same as zero


def test_a_metric_no_sample_produced_is_absent_rather_than_zero() -> None:
    """The failure this guards: a judge that errored on every sample would otherwise print
    as a retriever that found nothing, and the two call for opposite work."""
    result = score((sample("passage"), {CONTEXT_RECALL: 1.0}))

    assert result.mean(CONTEXT_RECALL) == 1.0
    assert result.mean(ANSWER_RELEVANCY) is None


def test_a_metric_is_averaged_only_over_the_samples_it_was_computed_for() -> None:
    result = score(
        (sample("a"), {CONTEXT_RECALL: 1.0}),
        (sample("b", identifier="DE-Q-002"), {}),
        (sample("c", identifier="DE-Q-003"), {CONTEXT_RECALL: 0.0}),
    )

    assert result.mean(CONTEXT_RECALL) == 0.5


def test_a_real_zero_still_counts() -> None:
    result = score((sample("wrong passage"), {CONTEXT_RECALL: 0.0}))

    assert result.mean(CONTEXT_RECALL) == 0.0


# ------------------------------------------------------------------------ what the report reads


def test_a_question_that_retrieved_nothing_is_counted_apart() -> None:
    """Two of the thirty DE questions retrieved nothing. That is a retrieval finding in its
    own right and must be visible, not buried in a mean."""
    result = score(
        (sample("found something"), {CONTEXT_RECALL: 1.0}),
        (sample(identifier="DE-Q-002"), {}),
    )

    assert result.answered == 1
    assert result.scored[1].sample.retrieved_nothing


def test_the_worst_questions_come_back_worst_first() -> None:
    result = score(
        (sample("a"), {CONTEXT_RECALL: 0.9}),
        (sample("b", identifier="DE-Q-002"), {CONTEXT_RECALL: 0.1}),
        (sample("c", identifier="DE-Q-003"), {CONTEXT_RECALL: 0.5}),
    )

    assert [s.scores[CONTEXT_RECALL] for s in result.worst(CONTEXT_RECALL, limit=2)] == [
        0.1,
        0.5,
    ]


def test_means_covers_every_reported_metric() -> None:
    result = score((sample("a"), {CONTEXT_RECALL: 1.0}))

    assert set(result.means) == set(METRIC_NAMES)


def test_verification_is_read_from_the_key_not_asserted_by_the_score() -> None:
    draft = RetrievalScore(fixture_name="de", question_set=question_set(), scored=())
    signed = RetrievalScore(
        fixture_name="de",
        question_set=question_set(
            state=VerificationState.HUMAN_VERIFIED,
            verified_by="Ahmed Nazih Ali",
            verified_on=date(2026, 9, 16),
        ),
        scored=(),
    )

    assert not draft.verified
    assert signed.verified


def test_the_two_reference_free_metrics_are_named() -> None:
    """The report quotes these two even against a draft key; the other two it qualifies."""
    assert {FAITHFULNESS, ANSWER_RELEVANCY} == REFERENCE_FREE
    assert CONTEXT_PRECISION not in REFERENCE_FREE


def test_passages_are_counted_across_a_tender() -> None:
    assert contexts_of([sample("a", "b"), sample("c", identifier="DE-Q-002")]) == 3
