"""S3.4.1 — the scorer: rules only, and every rule is asserted here.

Offline and pure. `score` takes requirements, matrix rows and the bidder's profile and
returns a `Verdict`; no model, no database, no clock. That is the story's whole point, so
these tests are the specification: if a decision cannot be derived from the four inputs,
it is not a decision this module is allowed to make.
"""

from __future__ import annotations

import uuid

import pytest

from crossbid.agent.scoring import ELLIPSIS, MAX_GAP_SUMMARY_CHARS, score
from crossbid.agent.verdict_text import BULLET, MAX_LISTED_GAPS
from crossbid.models.company import CompanyProfile, LegalForm, Tone, TurnoverYear
from crossbid.models.matrix import Evidence, MatrixRow, RowStatus
from crossbid.models.requirement import (
    Requirement,
    RequirementCategory,
    RequirementKind,
    RequirementStage,
    Threshold,
    ThresholdComparator,
    ThresholdUnit,
)
from crossbid.models.verdict import Decision, GapSeverity
from tests.conftest import requirement

BID_ID = "1f0e5e9e-1b7a-4b0a-9a3f-2c9f5b6d7e80"


# ------------------------------------------------------------------------ hand-built input


def row(
    req: Requirement,
    status: RowStatus = RowStatus.SUPPORTED,
    *,
    rationale: str = "Belegt durch den Jahresabschluss 2025.",
) -> MatrixRow:
    """The matrix row checking produced for `req`, with evidence when the status needs it."""
    cited = Evidence(
        document_id=BID_ID,
        document_name="Jahresabschluss_2025.pdf",
        page=2,
        quote="7,4 Mio. EUR",
    )
    evidence = (cited,) if status is RowStatus.SUPPORTED else ()
    return MatrixRow(
        id=str(uuid.uuid5(uuid.NAMESPACE_URL, req.id)),
        requirement_id=req.id,
        status=status,
        evidence=evidence,
        agent_rationale=rationale,
    )


def profile(**overrides: object) -> CompanyProfile:
    values: dict[str, object] = {
        "name": "Musterfirma IT-Dienstleistungen GmbH",
        "country": "de",
        "legal_form": LegalForm.GMBH,
        "language": "de",
        "tone": Tone.PLAIN,
    }
    return CompanyProfile(**(values | overrides))  # type: ignore[arg-type]


# --------------------------------------------------------------------------- the decisions


def test_every_mandatory_requirement_supported_is_a_go() -> None:
    # Arrange
    reqs = [requirement("Umsatz", identifier="a"), requirement("Personal", identifier="b")]
    rows = [row(req) for req in reqs]

    # Act
    result = score(reqs, rows, language="de", tone=Tone.PLAIN)

    # Assert
    assert result.decision is Decision.GO
    assert result.gaps == ()
    assert (result.mandatory_supported, result.mandatory_total) == (2, 2)


def test_a_mandatory_row_that_is_unsupported_blocks_the_bid() -> None:
    # Arrange
    reqs = [requirement("Umsatz", identifier="a"), requirement("Personal", identifier="b")]
    rows = [row(reqs[0]), row(reqs[1], RowStatus.UNSUPPORTED)]

    # Act
    result = score(reqs, rows, language="de")

    # Assert
    assert result.decision is Decision.NO_GO
    assert [gap.severity for gap in result.gaps] == [GapSeverity.BLOCKING]
    assert result.gaps[0].requirement_id == reqs[1].id


def test_an_unsupported_exclusion_ground_blocks_however_its_kind_reads() -> None:
    """An exclusion ground is fatal by nature; `optional` on the row does not soften it."""
    # Arrange
    reqs = [
        requirement("Umsatz", identifier="a"),
        requirement(
            "Keine Verurteilung wegen Bestechung",
            identifier="b",
            category=RequirementCategory.EXCLUSION_GROUND,
            kind=RequirementKind.OPTIONAL,
        ),
    ]
    rows = [row(reqs[0]), row(reqs[1], RowStatus.UNSUPPORTED)]

    # Act
    result = score(reqs, rows, language="de")

    # Assert
    assert result.decision is Decision.NO_GO
    assert result.gaps[0].requirement_id == reqs[1].id


def test_a_mandatory_row_that_is_only_partially_supported_is_conditional() -> None:
    # Arrange
    reqs = [requirement("Umsatz", identifier="a"), requirement("Personal", identifier="b")]
    rows = [row(reqs[0]), row(reqs[1], RowStatus.PARTIALLY_SUPPORTED)]

    # Act
    result = score(reqs, rows, language="de")

    # Assert
    assert result.decision is Decision.CONDITIONAL
    assert [gap.severity for gap in result.gaps] == [GapSeverity.OPEN_ITEM]
    assert result.partially_supported_rows == 1


def test_a_mandatory_requirement_with_no_row_at_all_is_never_a_go() -> None:
    """Checking that never reached a requirement must not be read as a pass."""
    # Arrange
    reqs = [requirement("Umsatz", identifier="a"), requirement("Personal", identifier="b")]
    rows = [row(reqs[0])]

    # Act
    result = score(reqs, rows, language="de")

    # Assert
    assert result.decision is Decision.CONDITIONAL
    assert [gap.requirement_id for gap in result.gaps] == [reqs[1].id]


def test_nothing_settled_is_the_agent_declining_to_judge() -> None:
    # Arrange
    reqs = [requirement("Umsatz", identifier="a"), requirement("Personal", identifier="b")]
    rows = [row(req, RowStatus.PARTIALLY_SUPPORTED) for req in reqs]

    # Act
    result = score(reqs, rows, language="de")

    # Assert
    assert result.decision is Decision.INSUFFICIENT_EVIDENCE
    assert result.mandatory_supported == 0


def test_an_empty_matrix_is_insufficient_evidence_and_never_a_go() -> None:
    """Extraction that found nothing has settled nothing; zero of zero is not a pass."""
    # Act
    result = score([], [], language="de")

    # Assert
    assert result.decision is Decision.INSUFFICIENT_EVIDENCE
    assert result.mandatory_total == 0
    assert result.gaps == ()


def test_a_blocking_gap_outranks_every_open_item() -> None:
    # Arrange
    reqs = [
        requirement("Umsatz", identifier="a"),
        requirement("Personal", identifier="b"),
        requirement("Referenzen", identifier="c"),
    ]
    rows = [
        row(reqs[0], RowStatus.PARTIALLY_SUPPORTED),
        row(reqs[1], RowStatus.UNSUPPORTED),
        row(reqs[2], RowStatus.PARTIALLY_SUPPORTED),
    ]

    # Act
    result = score(reqs, rows, language="de")

    # Assert
    assert result.decision is Decision.NO_GO
    assert result.gaps[0].severity is GapSeverity.BLOCKING
    assert [gap.severity for gap in result.gaps[1:]] == [GapSeverity.OPEN_ITEM] * 2


def test_not_applicable_settles_a_row_without_supporting_it() -> None:
    # Arrange
    reqs = [requirement("Umsatz", identifier="a"), requirement("Konzern", identifier="b")]
    rows = [row(reqs[0]), row(reqs[1], RowStatus.NOT_APPLICABLE)]

    # Act
    result = score(reqs, rows, language="de")

    # Assert
    assert result.decision is Decision.GO
    assert result.gaps == ()
    assert (result.mandatory_supported, result.mandatory_total) == (1, 2)


# ---------------------------------------------------------------------------- what counts


def test_contract_performance_requirements_are_not_scored_at_all() -> None:
    """The go/no-go question is about bidding, not about delivering (ADR-0003)."""
    # Arrange
    reqs = [
        requirement("Umsatz", identifier="a"),
        requirement(
            "Wartung binnen vier Stunden",
            identifier="b",
            stage=RequirementStage.CONTRACT_PERFORMANCE,
        ),
    ]
    rows = [row(reqs[0]), row(reqs[1], RowStatus.UNSUPPORTED)]

    # Act
    result = score(reqs, rows, language="de")

    # Assert
    assert result.decision is Decision.GO
    assert result.mandatory_total == 1


def test_an_optional_requirement_that_fails_is_an_open_item_not_a_block() -> None:
    # Arrange
    reqs = [
        requirement("Umsatz", identifier="a"),
        requirement("Zertifikat erwünscht", identifier="b", kind=RequirementKind.OPTIONAL),
    ]
    rows = [row(reqs[0]), row(reqs[1], RowStatus.UNSUPPORTED)]

    # Act
    result = score(reqs, rows, language="de")

    # Assert
    assert result.decision is Decision.CONDITIONAL
    assert [gap.severity for gap in result.gaps] == [GapSeverity.OPEN_ITEM]


def test_an_informational_requirement_is_neither_counted_nor_gapped() -> None:
    # Arrange
    reqs = [
        requirement("Umsatz", identifier="a"),
        requirement(
            "Hinweis auf das Vergabeportal",
            identifier="b",
            kind=RequirementKind.INFORMATIONAL,
        ),
    ]
    rows = [row(reqs[0]), row(reqs[1], RowStatus.UNSUPPORTED)]

    # Act
    result = score(reqs, rows, language="de")

    # Assert
    assert result.decision is Decision.GO
    assert result.mandatory_total == 1


def test_a_row_without_a_requirement_is_ignored_rather_than_scored() -> None:
    """The matrix is a projection; a row whose requirement is gone cannot be interpreted."""
    # Arrange
    reqs = [requirement("Umsatz", identifier="a")]
    orphan = requirement("Verschwunden", identifier="ghost")
    rows = [row(reqs[0]), row(orphan, RowStatus.UNSUPPORTED)]

    # Act
    result = score(reqs, rows, language="de")

    # Assert
    assert result.decision is Decision.GO


# -------------------------------------------------------------------- what a gap tells you


def test_a_gap_says_what_is_missing_in_the_bidders_language() -> None:
    # Arrange
    reqs = [
        requirement(
            "Mindestjahresumsatz von 3.000.000 EUR",
            identifier="a",
            translation="Minimum annual turnover of EUR 3,000,000",
        )
    ]
    rows = [row(reqs[0], RowStatus.UNSUPPORTED)]

    # Act
    result = score(reqs, rows, language="en")

    # Assert
    assert result.gaps[0].summary == "Minimum annual turnover of EUR 3,000,000"


def test_a_gap_falls_back_to_the_source_quote_when_nothing_was_translated() -> None:
    # Arrange
    reqs = [requirement("Mindestjahresumsatz von 3.000.000 EUR", identifier="a")]
    rows = [row(reqs[0], RowStatus.UNSUPPORTED)]

    # Act
    result = score(reqs, rows, language="de")

    # Assert
    assert result.gaps[0].summary == "Mindestjahresumsatz von 3.000.000 EUR"


def test_a_threshold_gap_names_the_number_required_and_the_number_recorded() -> None:
    # Arrange
    reqs = [
        requirement(
            "Mindestens 29 Vollzeitäquivalente",
            identifier="a",
            threshold=Threshold(
                comparator=ThresholdComparator.AT_LEAST, value=29, unit=ThresholdUnit.FTE
            ),
        )
    ]
    rows = [row(reqs[0], RowStatus.UNSUPPORTED)]

    # Act
    result = score(reqs, rows, language="de", profile=profile(staff_fte_relevant=21))

    # Assert
    assert result.gaps[0].required == "29 FTE"
    assert result.gaps[0].actual == "21 FTE"


def test_a_currency_threshold_reads_the_most_recent_matching_year() -> None:
    # Arrange
    reqs = [
        requirement(
            "Mindestjahresumsatz 3.000.000 EUR",
            identifier="a",
            threshold=Threshold(
                comparator=ThresholdComparator.AT_LEAST,
                value=3_000_000,
                unit=ThresholdUnit.CURRENCY,
                currency="EUR",
            ),
        )
    ]
    rows = [row(reqs[0], RowStatus.UNSUPPORTED)]
    turnover = (
        TurnoverYear(year=2024, amount=2_100_000, currency="EUR"),
        TurnoverYear(year=2025, amount=2_400_000, currency="EUR"),
    )

    # Act
    result = score(reqs, rows, language="de", profile=profile(turnover=turnover))

    # Assert
    assert result.gaps[0].required == "3.000.000 EUR"
    assert result.gaps[0].actual == "2.400.000 EUR"


def test_a_currency_the_company_does_not_report_in_leaves_actual_unstated() -> None:
    """A figure in the wrong currency is not the bidder's answer, and converting is a tool's
    job, not the scorer's — an unstated `actual` is the honest one."""
    # Arrange
    reqs = [
        requirement(
            "Mindestjahresumsatz 3.000.000 PLN",
            identifier="a",
            threshold=Threshold(
                comparator=ThresholdComparator.AT_LEAST,
                value=3_000_000,
                unit=ThresholdUnit.CURRENCY,
                currency="PLN",
            ),
        )
    ]
    rows = [row(reqs[0], RowStatus.UNSUPPORTED)]
    turnover = (TurnoverYear(year=2025, amount=2_400_000, currency="EUR"),)

    # Act
    result = score(reqs, rows, language="de", profile=profile(turnover=turnover))

    # Assert
    assert result.gaps[0].required == "3.000.000 PLN"
    assert result.gaps[0].actual is None


def test_a_gap_with_no_profile_to_compare_against_still_names_what_was_required() -> None:
    # Arrange
    reqs = [
        requirement(
            "Mindestens 29 Vollzeitäquivalente",
            identifier="a",
            threshold=Threshold(
                comparator=ThresholdComparator.AT_LEAST, value=29, unit=ThresholdUnit.FTE
            ),
        )
    ]
    rows = [row(reqs[0], RowStatus.UNSUPPORTED)]

    # Act
    result = score(reqs, rows, language="de", profile=None)

    # Assert
    assert result.gaps[0].required == "29 FTE"
    assert result.gaps[0].actual is None


def test_an_at_most_threshold_reports_no_actual_because_it_is_not_a_shortfall() -> None:
    # Arrange
    reqs = [
        requirement(
            "Höchstens 10 Unterauftragnehmer",
            identifier="a",
            threshold=Threshold(
                comparator=ThresholdComparator.AT_MOST, value=10, unit=ThresholdUnit.HEADCOUNT
            ),
        )
    ]
    rows = [row(reqs[0], RowStatus.UNSUPPORTED)]

    # Act
    result = score(reqs, rows, language="de", profile=profile(staff_fte=21))

    # Assert
    assert result.gaps[0].required == "10 headcount"
    assert result.gaps[0].actual is None


def test_a_threshold_the_profile_records_nothing_for_names_only_what_was_required() -> None:
    """References, years, person-days: real units with no field on `CompanyProfile`."""
    # Arrange
    reqs = [
        requirement(
            "Mindestens 3 Referenzen aus den letzten 3 Jahren",
            identifier="a",
            threshold=Threshold(
                comparator=ThresholdComparator.AT_LEAST,
                value=3,
                unit=ThresholdUnit.REFERENCES,
            ),
        )
    ]
    rows = [row(reqs[0], RowStatus.UNSUPPORTED)]

    # Act
    result = score(reqs, rows, language="de", profile=profile(staff_fte=21))

    # Assert
    assert result.gaps[0].required == "3 references"
    assert result.gaps[0].actual is None


def test_a_gap_summary_is_truncated_rather_than_quoting_a_whole_clause() -> None:
    """A gap is a prompt to act; the row beside it carries the clause and its page."""
    # Arrange
    clause = "Der Bieter " + "sehr lange Bedingung " * 30
    reqs = [requirement(clause, identifier="a")]
    rows = [row(reqs[0], RowStatus.UNSUPPORTED)]

    # Act
    result = score(reqs, rows, language="de")

    # Assert
    assert len(result.gaps[0].summary) <= MAX_GAP_SUMMARY_CHARS
    assert result.gaps[0].summary.endswith(ELLIPSIS)


# ----------------------------------------------------------------------------- the prose


@pytest.mark.parametrize("language", ["de", "en", "fr"])
@pytest.mark.parametrize("tone", list(Tone))
def test_the_rationale_is_written_in_every_supported_language_and_tone(
    language: str, tone: Tone
) -> None:
    # Arrange
    reqs = [requirement("Umsatz", identifier="a"), requirement("Personal", identifier="b")]
    rows = [row(reqs[0]), row(reqs[1], RowStatus.UNSUPPORTED)]

    # Act
    result = score(reqs, rows, language=language, tone=tone)

    # Assert
    assert result.rationale.strip()
    assert "{" not in result.rationale


def test_the_brief_tone_is_shorter_than_the_plain_one() -> None:
    # Arrange
    reqs = [requirement("Umsatz", identifier="a"), requirement("Personal", identifier="b")]
    rows = [row(reqs[0]), row(reqs[1], RowStatus.UNSUPPORTED)]

    # Act
    plain = score(reqs, rows, language="de", tone=Tone.PLAIN)
    brief = score(reqs, rows, language="de", tone=Tone.BRIEF)

    # Assert
    assert len(brief.rationale) < len(plain.rationale)


def test_an_unsupported_language_falls_back_rather_than_failing_the_run() -> None:
    # Arrange
    reqs = [requirement("Umsatz", identifier="a")]
    rows = [row(reqs[0], RowStatus.UNSUPPORTED)]

    # Act
    result = score(reqs, rows, language="cs")

    # Assert
    assert result.rationale.strip()
    assert result.decision is Decision.NO_GO


def test_a_regional_language_tag_is_matched_on_its_primary_subtag() -> None:
    # Arrange
    reqs = [requirement("Umsatz", identifier="a")]
    rows = [row(reqs[0], RowStatus.UNSUPPORTED)]

    # Act
    regional = score(reqs, rows, language="de-AT")
    plain = score(reqs, rows, language="de")

    # Assert
    assert regional.rationale == plain.rationale


def test_the_rationale_lists_the_gaps_but_not_hundreds_of_them() -> None:
    # Arrange
    reqs = [requirement(f"Anforderung {n}", identifier=str(n)) for n in range(40)]
    rows = [row(req, RowStatus.UNSUPPORTED) for req in reqs]

    # Act
    result = score(reqs, rows, language="de")

    # Assert
    assert len(result.gaps) == 40
    assert result.rationale.count(BULLET) <= MAX_LISTED_GAPS
