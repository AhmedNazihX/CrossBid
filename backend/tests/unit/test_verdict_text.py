"""S3.4.1 — the phrasebooks: every pair exists, and every placeholder resolves.

`verdict_text.py` is nine tables of format strings, and the failure mode of a table of
format strings is a typo that only shows up in the one language nobody reads. So the table
is walked exhaustively here rather than sampled: every `(language, tone)` pair, every
`Decision`, every field, rendered with real numbers and asserted to contain no unresolved
brace. A German bidder reading `{blockng}` is the bug these tests exist to prevent.
"""

from __future__ import annotations

from dataclasses import fields

import pytest

from crossbid.agent.verdict_text import (
    BULLET,
    FALLBACK_LANGUAGE,
    GROUP_SEPARATORS,
    MAX_LISTED_GAPS,
    PHRASEBOOKS,
    SUPPORTED_LANGUAGES,
    Phrasebook,
    group_digits,
    phrasebook_for,
    primary_subtag,
    rationale,
)
from crossbid.models.company import Tone
from crossbid.models.verdict import Decision, Gap, GapSeverity

NUMBERS = {"blocking": 2, "open_items": 3, "supported": 7, "total": 9, "partial": 4}

LANGUAGES = sorted(SUPPORTED_LANGUAGES)
PAIRS = [(language, tone) for language in LANGUAGES for tone in Tone]


def gap(
    identifier: str = "a",
    severity: GapSeverity = GapSeverity.BLOCKING,
    *,
    required: str | None = None,
    actual: str | None = None,
) -> Gap:
    return Gap(
        requirement_id=identifier,
        severity=severity,
        summary=f"Anforderung {identifier}",
        required=required,
        actual=actual,
    )


# ------------------------------------------------------------------------- the table itself


def test_every_language_is_written_in_every_tone() -> None:
    """A missing pair would be a `KeyError` on a real bid, not a fallback."""
    assert set(PHRASEBOOKS) == set(PAIRS)


@pytest.mark.parametrize(("language", "tone"), PAIRS)
def test_every_headline_covers_every_decision(language: str, tone: Tone) -> None:
    assert set(PHRASEBOOKS[(language, tone)].headline) == set(Decision)


@pytest.mark.parametrize(("language", "tone"), PAIRS)
def test_every_string_in_every_book_resolves_with_the_numbers_it_is_given(
    language: str, tone: Tone
) -> None:
    """Renders every field of every book. A typo in a placeholder fails here, not on a bid."""
    # Arrange
    book = PHRASEBOOKS[(language, tone)]
    arguments = {**NUMBERS, "rest": 12, "required": "29 FTE", "actual": "21 FTE"}

    # Act / Assert
    for headline in book.headline.values():
        assert "{" not in headline.format(**arguments)
    for field in fields(Phrasebook):
        if field.name == "headline":
            continue
        template = getattr(book, field.name)
        assert "{" not in template.format(**arguments)


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_brief_tone_prints_a_headline_and_nothing_else(language: str) -> None:
    """Decision 2: every other field is empty, which is what makes it brief."""
    # Arrange
    book = PHRASEBOOKS[(language, Tone.BRIEF)]

    # Act / Assert
    for field in fields(Phrasebook):
        if field.name != "headline":
            assert getattr(book, field.name) == ""


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_language_groups_its_thousands(language: str) -> None:
    assert language in GROUP_SEPARATORS


def test_the_three_languages_group_three_million_differently() -> None:
    # Act / Assert
    assert group_digits(3_000_000, "de") == "3.000.000"
    assert group_digits(3_000_000, "en") == "3,000,000"
    assert group_digits(3_000_000, "fr") == "3 000 000"


def test_grouping_rounds_rather_than_inventing_precision() -> None:
    assert group_digits(28.5, "en") == "28"
    assert group_digits(21.0, "de") == "21"


def test_an_unknown_language_groups_the_english_way() -> None:
    assert group_digits(3_000_000, "cs") == "3,000,000"


# ------------------------------------------------------------------------- choosing a book


def test_a_regional_tag_resolves_to_its_primary_subtag() -> None:
    assert primary_subtag("de-AT") == "de"
    assert primary_subtag("  FR  ") == "fr"


def test_an_unsupported_language_falls_back_rather_than_raising() -> None:
    assert phrasebook_for("cs", Tone.PLAIN) is PHRASEBOOKS[(FALLBACK_LANGUAGE, Tone.PLAIN)]


def test_the_fallback_language_is_one_that_exists() -> None:
    assert FALLBACK_LANGUAGE in SUPPORTED_LANGUAGES


# ----------------------------------------------------------------------------- rendering


def test_the_plain_rationale_leads_with_the_headline_then_counts_then_the_list() -> None:
    # Act
    text = rationale(
        Decision.NO_GO,
        [gap("a"), gap("b")],
        language="en",
        tone=Tone.PLAIN,
        mandatory_total=9,
        mandatory_supported=7,
        partially_supported_rows=0,
    )

    # Assert
    assert text.startswith("This bid is not recommended.")
    assert "7 of 9 mandatory requirements are supported." in text
    assert "2 requirement(s) block this bid:" in text
    assert text.count(BULLET) == 2


def test_a_long_gap_list_is_truncated_with_a_note_that_is_not_itself_a_bullet() -> None:
    # Arrange
    gaps = [gap(str(n)) for n in range(MAX_LISTED_GAPS + 4)]

    # Act
    text = rationale(
        Decision.NO_GO,
        gaps,
        language="en",
        tone=Tone.PLAIN,
        mandatory_total=9,
        mandatory_supported=0,
        partially_supported_rows=0,
    )

    # Assert
    assert text.count(BULLET) == MAX_LISTED_GAPS
    assert "and 4 more." in text


def test_blocking_and_open_items_are_listed_under_their_own_leads() -> None:
    # Act
    text = rationale(
        Decision.NO_GO,
        [gap("a"), gap("b", GapSeverity.OPEN_ITEM)],
        language="en",
        tone=Tone.PLAIN,
        mandatory_total=9,
        mandatory_supported=7,
        partially_supported_rows=1,
    )

    # Assert
    assert "1 requirement(s) block this bid:" in text
    assert "1 requirement(s) still need evidence:" in text


def test_a_bullet_carries_the_numbers_when_both_are_known() -> None:
    # Act
    text = rationale(
        Decision.NO_GO,
        [gap("a", required="29 FTE", actual="21 FTE")],
        language="en",
        tone=Tone.PLAIN,
        mandatory_total=9,
        mandatory_supported=7,
        partially_supported_rows=0,
    )

    # Assert
    assert "Anforderung a (required 29 FTE, recorded 21 FTE)" in text


def test_a_bullet_names_only_what_was_required_when_the_profile_could_not_answer() -> None:
    # Act
    text = rationale(
        Decision.NO_GO,
        [gap("a", required="29 FTE")],
        language="en",
        tone=Tone.PLAIN,
        mandatory_total=9,
        mandatory_supported=7,
        partially_supported_rows=0,
    )

    # Assert
    assert "Anforderung a (required 29 FTE)" in text


def test_the_counts_sentence_is_dropped_when_nothing_mandatory_was_scored() -> None:
    """ "0 of 0 mandatory requirements are supported" says nothing and reads as a failure."""
    # Act
    text = rationale(
        Decision.INSUFFICIENT_EVIDENCE,
        [],
        language="en",
        tone=Tone.PLAIN,
        mandatory_total=0,
        mandatory_supported=0,
        partially_supported_rows=0,
    )

    # Assert
    assert "of 0 mandatory" not in text
    assert text == "The documents do not settle enough requirements for a recommendation."


def test_the_brief_tone_never_lists_a_gap_however_many_there_are() -> None:
    # Act
    text = rationale(
        Decision.NO_GO,
        [gap(str(n)) for n in range(40)],
        language="de",
        tone=Tone.BRIEF,
        mandatory_total=40,
        mandatory_supported=0,
        partially_supported_rows=0,
    )

    # Assert
    assert text == "Kein Angebot. 40 blockierende Lücken."
    assert BULLET not in text


def test_no_rendering_leaves_a_blank_paragraph_behind() -> None:
    """`\\n\\n`.join over a skipped section would otherwise open a hole in the prose."""
    # Act
    text = rationale(
        Decision.CONDITIONAL,
        [gap("a", GapSeverity.OPEN_ITEM)],
        language="fr",
        tone=Tone.FORMAL,
        mandatory_total=9,
        mandatory_supported=8,
        partially_supported_rows=1,
    )

    # Assert
    assert "\n\n\n" not in text
    assert text == text.strip()
