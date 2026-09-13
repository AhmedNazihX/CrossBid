"""S2.5.1 — the DUME's criteria become requirements, mechanically, with no model involved.

The one thing every test here shares: nothing is inferred. The category comes from the ESPD
type code, the criterion id comes from the file, the wording comes from the buyer, and the
citation is the criterion rather than a page — because a DUME has no pages and a row that
claimed one would be a citation the reviewer cannot follow.
"""

from __future__ import annotations

import logging

import pytest

from crossbid.agent.espd_requirements import requirements_from_espd
from crossbid.ingestion.espd import EspdCriterion, EspdRequest, parse_espd_request
from crossbid.models.ecertis_criteria import CRITERION_IDS
from crossbid.models.requirement import (
    MAX_QUOTE_CHARS,
    Checkability,
    RequirementCategory,
    RequirementKind,
    RequirementSource,
    RequirementStage,
)
from tests.conftest import espd_request_bytes

BID_ID = "bid-1"
DOCUMENT = "DUME_acheteur.xml"
TURNOVER_TYPE = "CRITERION.SELECTION.ECONOMIC_FINANCIAL_STANDING.TURNOVER.GENERAL_YEARLY"


def criterion(
    type_code: str = TURNOVER_TYPE,
    *,
    identifier: str = CRITERION_IDS[0],
    name: str = "Chiffre d'affaires",
    description: str = "Chiffre(s) d'affaires annuel general",
) -> EspdCriterion:
    return EspdCriterion(
        id=identifier,  # type: ignore[arg-type]
        type_code=type_code,
        name=name,
        description=description,
    )


def rows_for(*criteria: EspdCriterion, language: str | None = None, fallback: str = "fr"):
    request = EspdRequest(criteria=criteria, language=language)
    return requirements_from_espd(
        request, bid_id=BID_ID, document_name=DOCUMENT, source_lang=fallback
    )


# --------------------------------------------------------------------- the whole fixture


def test_every_criterion_of_the_french_fixture_becomes_a_mapped_requirement() -> None:
    """The story's acceptance in one assertion: 30 rows, 30 criterion ids, zero inference."""
    # Arrange
    request = parse_espd_request(espd_request_bytes())

    # Act
    rows = requirements_from_espd(
        request, bid_id=BID_ID, document_name=DOCUMENT, source_lang="fr"
    )

    # Assert
    assert len(rows) == 30
    assert all(row.ecertis_criterion_id is not None for row in rows)
    assert all(row.stage is RequirementStage.BID_ELIGIBILITY for row in rows)
    assert all(row.source is RequirementSource.ESPD_REQUEST for row in rows)
    assert all(row.page is None for row in rows)
    assert all(row.document_name == DOCUMENT for row in rows)
    assert all(row.source_lang == "fr" for row in rows)
    assert all(row.bid_id == BID_ID for row in rows)


def test_the_fixture_maps_to_the_families_the_type_codes_declare() -> None:
    """24 exclusion grounds and 6 selection criteria, per the buyer's own type codes."""
    # Arrange
    request = parse_espd_request(espd_request_bytes())

    # Act
    rows = requirements_from_espd(
        request, bid_id=BID_ID, document_name=DOCUMENT, source_lang="fr"
    )

    # Assert
    categories = [row.category for row in rows]
    assert categories.count(RequirementCategory.EXCLUSION_GROUND) == 24
    assert categories.count(RequirementCategory.ECONOMIC_FINANCIAL) == 3
    assert categories.count(RequirementCategory.TECHNICAL_PROFESSIONAL) == 3


# ------------------------------------------------------------------- the type-code mapping


@pytest.mark.parametrize(
    ("type_code", "category", "checkable"),
    [
        (
            "CRITERION.EXCLUSION.CONVICTIONS.CORRUPTION",
            RequirementCategory.EXCLUSION_GROUND,
            Checkability.DOCUMENT_SUBMISSION,
        ),
        (
            "CRITERION.EXCLUSION.CONTRIBUTIONS.PAYMENT_OF_TAXES",
            RequirementCategory.EXCLUSION_GROUND,
            Checkability.DOCUMENT_SUBMISSION,
        ),
        (TURNOVER_TYPE, RequirementCategory.ECONOMIC_FINANCIAL, Checkability.COMPANY_PROPERTY),
        (
            "CRITERION.SELECTION.TECHNICAL_PROFESSIONAL_ABILITY.REFERENCES.WORKS",
            RequirementCategory.TECHNICAL_PROFESSIONAL,
            Checkability.COMPANY_PROPERTY,
        ),
        (
            "CRITERION.SELECTION.SUITABILITY.ENROLMENT_PROFESSIONAL_REGISTER",
            RequirementCategory.FORMAL,
            Checkability.COMPANY_PROPERTY,
        ),
        (
            "CRITERION.OTHER.EU_FUNDS",
            RequirementCategory.OTHER,
            Checkability.NEITHER,
        ),
        (
            "CRITERION.SELECTION.OTHER.ALL_SELECTION_CRITERIA_SATISFIED",
            RequirementCategory.OTHER,
            Checkability.NEITHER,
        ),
    ],
)
def test_the_type_code_decides_the_category_and_what_can_settle_it(
    type_code: str, category: RequirementCategory, checkable: Checkability
) -> None:
    # Act
    [row] = rows_for(criterion(type_code))

    # Assert
    assert row.category is category
    assert row.checkable is checkable


def test_an_exclusion_ground_and_a_selection_criterion_are_both_mandatory() -> None:
    """A buyer that declares a criterion in the DUME requires an answer to it."""
    # Act
    [exclusion] = rows_for(criterion("CRITERION.EXCLUSION.BUSINESS.BANKRUPTCY"))
    [selection] = rows_for(criterion(TURNOVER_TYPE))

    # Assert
    assert exclusion.kind is RequirementKind.MANDATORY
    assert selection.kind is RequirementKind.MANDATORY


def test_a_criterion_outside_the_two_families_is_informational() -> None:
    """`CRITERION.OTHER.*` is about the contract, not about the bidder's qualification."""
    [row] = rows_for(criterion("CRITERION.OTHER.EU_FUNDS"))

    assert row.kind is RequirementKind.INFORMATIONAL


def test_the_type_code_is_matched_case_insensitively() -> None:
    """The code list is upper case; a buyer's generator that lower-cased it still maps."""
    [row] = rows_for(criterion(TURNOVER_TYPE.lower()))

    assert row.category is RequirementCategory.ECONOMIC_FINANCIAL


# ---------------------------------------------------------------------- wording and citation


def test_the_buyers_description_is_the_quote_and_the_name_is_the_fallback() -> None:
    """One fixture criterion has a description of a single space; the name carries it."""
    # Act
    [described] = rows_for(criterion(description="Chiffre(s) d'affaires"))
    [named] = rows_for(criterion(name="Effectifs moyens annuels", description="  "))

    # Assert
    assert described.source_text == "Chiffre(s) d'affaires"
    assert named.source_text == "Effectifs moyens annuels"


def test_a_row_carries_no_translation_because_nothing_translated_it() -> None:
    """Honest absence: the eCertis lookup names the criterion in the bidder's language."""
    [row] = rows_for(criterion())

    assert row.translation is None


def test_the_language_the_file_declares_wins_over_the_tenders_own() -> None:
    # Act
    [declared] = rows_for(criterion(), language="fr", fallback="de")
    [fallen_back] = rows_for(criterion(), language=None, fallback="de")

    # Assert
    assert declared.source_lang == "fr"
    assert fallen_back.source_lang == "de"


# ------------------------------------------------------------------------------- row ids


def test_ids_are_deterministic_so_a_resumed_run_updates_rather_than_doubles() -> None:
    """The `requirements` upsert is keyed on the id (S3.1.1)."""
    # Act
    first = rows_for(criterion())
    second = rows_for(criterion())

    # Assert
    assert [row.id for row in first] == [row.id for row in second]


def test_two_criteria_of_one_document_get_two_ids() -> None:
    # Act
    rows = rows_for(
        criterion(identifier=CRITERION_IDS[0]),
        criterion("CRITERION.EXCLUSION.CONVICTIONS.FRAUD", identifier=CRITERION_IDS[1]),
    )

    # Assert
    assert len({row.id for row in rows}) == 2


def test_the_same_criterion_in_two_bids_gets_two_ids() -> None:
    """The id is scoped to the bid, or two bids would fight over one row."""
    # Arrange
    request = EspdRequest(criteria=(criterion(),))

    # Act
    [first] = requirements_from_espd(
        request, bid_id="bid-1", document_name=DOCUMENT, source_lang="fr"
    )
    [second] = requirements_from_espd(
        request, bid_id="bid-2", document_name=DOCUMENT, source_lang="fr"
    )

    # Assert
    assert first.id != second.id


# -------------------------------------------------------------------------- what is dropped


def test_wording_too_long_to_be_a_quote_is_dropped_rather_than_truncated(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`Requirement` caps a quote; truncating one would make it no longer the buyer's words."""
    # Arrange
    long_text = "x" * (MAX_QUOTE_CHARS + 1)

    # Act
    with caplog.at_level(logging.WARNING):
        rows = rows_for(criterion(name=long_text, description=long_text))

    # Assert
    assert rows == ()
    assert "source_text" in caplog.text


def test_a_request_with_no_criteria_yields_no_rows() -> None:
    assert rows_for() == ()
