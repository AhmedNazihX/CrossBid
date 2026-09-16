"""S7.1 — the retrieval answer key: what it accepts, and what it refuses to call verified.

The one behaviour worth a suite of its own is `meta.verified`. `REPORT.md` prints it beside
every reference-scored figure, so a file that claimed verification it did not have would put
an unearned word next to a number — which is the exact failure S6.4 spent a day correcting
for the extraction key.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from crossbid.eval.questions import (
    QuestionSet,
    QuestionSetError,
    QuestionSetMeta,
    RetrievalQuestion,
    VerificationState,
    dump_question_set,
    load_question_set,
    questions_by_label,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "retrieval"


def meta(**overrides: object) -> QuestionSetMeta:
    base: dict[str, object] = {
        "fixture_dir": "tests/fixtures/tenders/de",
        "source_language": "de",
        "bidder_language": "de",
        "derived_from": "golden.yaml",
        "generated_by": "openai/gpt-5.6-luna",
        "generated_on": date(2026, 9, 16),
        "method": "drafted from the verified labels",
    }
    return QuestionSetMeta.model_validate(base | overrides)


def question(identifier: str = "DE-Q-001", **overrides: object) -> RetrievalQuestion:
    base: dict[str, object] = {
        "id": identifier,
        "label_id": "DE-012",
        "question": "Welchen Mindestjahresumsatz verlangt die Vergabestelle?",
        "reference": "The bidder must show a minimum annual turnover of EUR 3,000,000.",
        "reference_contexts": ("Mindestjahresumsatz von 3.000.000 EUR",),
        "doc": "Bewerbungsbedingungen.pdf",
        "page": 7,
    }
    return RetrievalQuestion.model_validate(base | overrides)


# ------------------------------------------------------------------ what "verified" means


def test_a_draft_is_not_verified() -> None:
    assert not meta().verified


def test_a_state_without_a_name_is_not_verified() -> None:
    """`state: human_verified` alone is somebody editing one line. The report would then
    print "verified" with nobody standing behind it."""
    assert not meta(state=VerificationState.HUMAN_VERIFIED).verified


def test_a_name_without_a_date_is_not_verified() -> None:
    assert not meta(
        state=VerificationState.HUMAN_VERIFIED, verified_by="Ahmed Nazih Ali"
    ).verified


def test_state_name_and_date_together_are_verified() -> None:
    signed = meta(
        state=VerificationState.HUMAN_VERIFIED,
        verified_by="Ahmed Nazih Ali",
        verified_on=date(2026, 9, 16),
    )

    assert signed.verified


# ------------------------------------------------------------------------- what is refused


def test_a_question_must_name_the_label_its_answer_came_from() -> None:
    """Without it the answer is unattributable and nobody can check it against the key."""
    with pytest.raises(ValidationError):
        question(label_id="")


def test_a_question_without_a_reference_passage_is_refused() -> None:
    """`context_recall` has nothing to be right about without one."""
    with pytest.raises(ValidationError):
        question(reference_contexts=())


def test_an_identifier_outside_the_scheme_is_refused() -> None:
    with pytest.raises(ValidationError):
        question("DE-1")


def test_an_empty_question_set_is_refused() -> None:
    with pytest.raises(ValidationError):
        QuestionSet(meta=meta(), questions=())


# -------------------------------------------------------------------------- reading a file


def test_a_set_round_trips_through_yaml(tmp_path: Path) -> None:
    original = QuestionSet(meta=meta(), questions=(question(),))
    path = tmp_path / "de.questions.yaml"

    dump_question_set(original, path)

    assert load_question_set(path) == original


def test_a_file_that_is_not_a_mapping_names_the_path(tmp_path: Path) -> None:
    path = tmp_path / "broken.yaml"
    path.write_text("- just\n- a list\n", encoding="utf-8")

    with pytest.raises(QuestionSetError, match="expected a mapping"):
        load_question_set(path)


def test_a_missing_file_is_a_question_set_error(tmp_path: Path) -> None:
    with pytest.raises(QuestionSetError):
        load_question_set(tmp_path / "absent.yaml")


def test_questions_are_indexed_by_the_label_they_came_from() -> None:
    indexed = questions_by_label((question(), question("DE-Q-002", label_id="DE-013")))

    assert sorted(indexed) == ["DE-012", "DE-013"]


# ------------------------------------------------------- the committed keys, as they stand


@pytest.mark.parametrize("fixture", ["de", "fr", "en"])
def test_the_committed_key_reads_and_names_its_tender(fixture: str) -> None:
    question_set = load_question_set(FIXTURES / f"{fixture}.questions.yaml")

    assert question_set.fixture_name == fixture
    assert len(question_set.questions) == 30
    assert all(q.reference_contexts for q in question_set.questions)
