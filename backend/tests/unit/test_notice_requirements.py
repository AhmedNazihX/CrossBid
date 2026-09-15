# ruff: noqa: RUF001 - the en dash below is TED's own, copied from a live answer
"""S3.2.2 — TED's structured notice fields as requirements, decided by rule.

The shortest kind of test in the system, because the code under it asks no model: a notice
goes in, rows come out, and every field is a table lookup or a quote. What is worth pinning
is the *judgements* — which row is checkable and which is the reviewer's, what is quoted
verbatim and what is written by us, and what is deliberately left empty.

The notice below is shaped like a live one (probed 2026-09-14): `selection_criteria` in the
notice's own language, a deadline with an offset and no hour, three-letter language codes.
"""

from __future__ import annotations

import logging
from datetime import date

import pytest

from crossbid.agent.notice_requirements import requirements_from_notice
from crossbid.models.requirement import (
    MAX_QUOTE_CHARS,
    Checkability,
    RequirementCategory,
    RequirementKind,
    RequirementSource,
    RequirementStage,
)
from crossbid.models.ted import TedNotice

BID_ID = "11111111-1111-4111-8111-111111111111"

CRITERION = (
    "Eigenerklärung, dass eine Eintragung im Berufs- oder Handelsregister oder ein anderer, "
    "vergleichbarer Nachweis für die erlaubte Berufsausübung vorliegt."
)

NOTICE = TedNotice(
    publication_number="629758-2026",
    title="Deutschland – Systemberatung",
    buyer="GMSH",
    description=None,
    deadline=date(2026, 10, 7),
    deadline_utc_offset_minutes=120,
    official_languages=("DEU",),
    submission_languages=("DEU", "ENG"),
    cpv=("72000000",),
    notice_pdf_url="https://ted.europa.eu/de/notice/629758-2026/pdf",
    documents_url=None,
    selection_criteria=(CRITERION,),
)


def rows_of(notice: TedNotice):
    return requirements_from_notice(notice, bid_id=BID_ID)


def test_every_row_is_sourced_to_the_notice_and_cites_no_page() -> None:
    """A notice reaches us as JSON, so there is no page to cite — and the database refuses
    to let `source` and `page` disagree (migration 0008)."""
    for row in rows_of(NOTICE):
        assert row.source is RequirementSource.NOTICE
        assert row.page is None
        assert row.bid_id == BID_ID
        assert row.document_name == "TED notice 629758-2026"


def test_no_row_carries_an_ecertis_criterion_id() -> None:
    """A notice states criteria in prose. ADR-0007 forbids inferring an id from wording:
    a wrong id is worse than none, and only a published DUME carries ones nobody guessed."""
    assert all(row.ecertis_criterion_id is None for row in rows_of(NOTICE))


def test_the_deadline_becomes_a_row_the_reviewer_settles() -> None:
    """No fact about the company settles a deadline: it is met by acting. Sending it to the
    checking loop would spend tool calls to reach `unclear` (ADR-0003)."""
    deadline = next(row for row in rows_of(NOTICE) if row.deadline is not None)

    assert deadline.deadline == date(2026, 10, 7)
    assert deadline.checkable is Checkability.DOCUMENT_SUBMISSION
    assert deadline.category is RequirementCategory.FORMAL
    assert deadline.kind is RequirementKind.MANDATORY


def test_the_deadline_row_says_that_ted_published_no_hour() -> None:
    """The row a reviewer reads to decide whether the bid is worth starting. Rendering it as
    a timestamp would invent an hour nobody published (ADR-0043)."""
    deadline = next(row for row in rows_of(NOTICE) if row.deadline is not None)

    assert "2026-10-07" in deadline.source_text
    assert "UTC+02:00" in deadline.source_text
    assert "no time of day" in deadline.source_text


def test_a_notice_with_no_offset_says_so_rather_than_assuming_utc() -> None:
    notice = NOTICE.model_copy(update={"deadline_utc_offset_minutes": None})
    deadline = next(row for row in rows_of(notice) if row.deadline is not None)

    assert "not stated" in deadline.source_text


def test_a_negative_offset_keeps_its_sign() -> None:
    notice = NOTICE.model_copy(update={"deadline_utc_offset_minutes": -180})
    deadline = next(row for row in rows_of(notice) if row.deadline is not None)

    assert "UTC-03:00" in deadline.source_text


def test_the_submission_languages_become_one_row_naming_them_all() -> None:
    """A bid in the wrong language is rejected unread, which is a requirement like any other."""
    languages = next(row for row in rows_of(NOTICE) if "DEU, ENG" in row.source_text)

    assert languages.checkable is Checkability.DOCUMENT_SUBMISSION
    assert "rejected without being read" in languages.source_text


def test_a_stated_criterion_is_quoted_verbatim_and_is_checkable() -> None:
    """The quote is evidence: `eval/matching.py` compares `source_text` and never
    `translation`, and a machine translation of a legal criterion is not the criterion."""
    criterion = next(row for row in rows_of(NOTICE) if row.source_text == CRITERION)

    assert criterion.checkable is Checkability.COMPANY_PROPERTY
    assert criterion.category is RequirementCategory.OTHER
    assert criterion.translation is None


def test_every_row_is_bid_eligibility() -> None:
    """A notice's structured fields decide whether a bidder may be considered at all; none
    of them governs performance after award."""
    assert all(row.stage is RequirementStage.BID_ELIGIBILITY for row in rows_of(NOTICE))


def test_the_source_language_is_two_letters_from_teds_three() -> None:
    assert all(row.source_lang == "de" for row in rows_of(NOTICE))


def test_an_unmapped_language_falls_back_to_its_first_two_letters() -> None:
    """Right far more often than it is wrong, and never worse than refusing the row."""
    notice = NOTICE.model_copy(update={"official_languages": ("xyz",)})

    assert all(row.source_lang == "xy" for row in rows_of(notice))


def test_a_notice_with_no_language_at_all_still_produces_rows() -> None:
    notice = NOTICE.model_copy(update={"official_languages": ()})

    assert all(row.source_lang == "en" for row in rows_of(notice))


def test_a_notice_with_nothing_structured_produces_nothing() -> None:
    """The common case, and not a failure: most notices state no criteria at all. The pack
    is the source of record; this is the buyer's own words in addition to it."""
    bare = NOTICE.model_copy(
        update={
            "deadline": None,
            "deadline_utc_offset_minutes": None,
            "submission_languages": (),
            "selection_criteria": (),
        }
    )

    assert rows_of(bare) == ()


def test_the_rows_have_distinct_ids() -> None:
    rows = rows_of(NOTICE)

    assert len({row.id for row in rows}) == len(rows)


def test_a_criterion_longer_than_a_quote_may_be_is_dropped_and_not_raised(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The defect this guard exists for: TED does not cap the field, `source_text` does.

    Constructing inline, one verbose buyer raised a `ValidationError` out of `parse_docs`,
    which the stage wrapper turned into a failed bid — losing a pack the bidder had already
    uploaded. The notice is a bonus source, so the row goes and the run stays.
    """
    verbose = NOTICE.model_copy(
        update={"selection_criteria": (CRITERION, "x" * (MAX_QUOTE_CHARS + 1))}
    )

    with caplog.at_level(logging.WARNING, logger="crossbid.agent.notice_requirements"):
        rows = rows_of(verbose)

    quotes = [row.source_text for row in rows]
    assert CRITERION in quotes
    assert not any(quote.startswith("xxxx") for quote in quotes)
    assert "source_text" in caplog.text


def test_a_dropped_criterion_never_logs_the_buyers_own_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The text could be anything, including the planted instructions S2.3.1 looks for."""
    secret = "ZZZ" + "y" * MAX_QUOTE_CHARS
    verbose = NOTICE.model_copy(update={"selection_criteria": (secret,)})

    with caplog.at_level(logging.WARNING, logger="crossbid.agent.notice_requirements"):
        rows_of(verbose)

    assert "ZZZ" not in caplog.text


def test_the_ids_are_derived_and_not_minted() -> None:
    """A re-run upserts instead of doubling.

    `readmodel/requirements.py` states the contract: the id is a `uuid5` so that a crash
    between the projection write and the checkpoint write does not leave two deadline rows.
    Extraction and the DUME path already held it; the notice path used `uuid4` and did not.
    """
    first = rows_of(NOTICE)
    second = rows_of(NOTICE)

    assert [row.id for row in first] == [row.id for row in second]


def test_a_different_bid_gets_different_ids_for_the_same_notice() -> None:
    """The bid is in the key, so two bids on one notice do not collide on the primary key."""
    other = requirements_from_notice(NOTICE, bid_id="22222222-2222-4222-8222-222222222222")

    assert {row.id for row in rows_of(NOTICE)}.isdisjoint({row.id for row in other})
