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
    ReviewFlag,
    VerificationState,
    content_words,
    dump_question_set,
    flagged_questions,
    load_question_set,
    questions_by_label,
    review_flags,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "retrieval"

MINIMUM_KEY = 20
"""Below this a tender's retrieval figures are too few to read as a rate."""


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
    assert all(q.reference_contexts for q in question_set.questions)
    # Not a fixed 30. The generator skips a label whose summary cannot carry a specific
    # question, and the FR pack has only 30 scored labels to draw from in the first place, so
    # its key is 23. A key shorter than asked for is a fact about the answer key, not a bug --
    # what must never happen is a key padded with questions that measure nothing.
    assert len(question_set.questions) >= MINIMUM_KEY
    assert len({q.id for q in question_set.questions}) == len(question_set.questions)


# ------------------------------------------------------- narrowing a draft key for a reviewer


def test_a_question_in_the_forms_own_voice_is_flagged() -> None:
    """The defect a human found that no overlap measure could: the model copied the register
    of the document instead of asking about it. A bidder does not type "which variant would
    you like to choose?" into a search box — the form asks them that."""
    drafted = question(
        question=(
            "Welche Variante des Plausibilitätsnachweises möchten Sie mit Ihrem Angebot wählen?"
        )
    )

    assert ReviewFlag.FORM_VOICE in review_flags(drafted)


def test_a_question_that_reuses_the_clause_is_flagged() -> None:
    asked = question(
        question="Muss der Teilnahmeantrag vor Ablauf der Frist vollständig eingegangen sein?",
        reference_contexts=(
            "Der Teilnahmeantrag/das Angebot muss vor Ablauf der jeweiligen Frist "
            "vollständig eingegangen sein (i.d.R. 11:30:00 Uhr).",
        ),
    )

    assert ReviewFlag.ECHOES_CLAUSE in review_flags(asked)


def test_an_ordinary_question_is_not_flagged() -> None:
    assert review_flags(question()) == ()


def test_the_echo_check_compares_the_question_with_the_clause_not_the_reference() -> None:
    """The bug this pins, which shipped for one commit and flagged 86 of 90 questions.

    The question is in the bidder's language and `reference` is one line of English, so any
    lexical comparison between them measures the language gap and nothing else. Comparing the
    question with its *clause* compares like with like — both are in the tender's language.
    """
    german = question(
        question="Wie lange muss mein Angebot gültig bleiben?",
        reference="The offer must remain valid for eight months.",
        reference_contexts=("Dauer, während der das Angebot gültig bleiben muss: 8 Monate",),
    )

    # Shares nothing with the English reference, and plenty with the German clause.
    assert ReviewFlag.ECHOES_CLAUSE in review_flags(german)


def test_flagged_questions_returns_only_the_ones_with_flags() -> None:
    clean = question("DE-Q-001")
    voiced = question("DE-Q-002", question="Welche Variante möchten Sie wählen?")
    question_set = QuestionSet(meta=meta(), questions=(clean, voiced))

    flagged = flagged_questions(question_set)

    assert [q.id for q, _ in flagged] == ["DE-Q-002"]


def test_content_words_ignore_short_tokens() -> None:
    assert content_words("Der Bieter muss Umsatz nachweisen") == {
        "bieter",
        "umsatz",
        "nachweisen",
    }
