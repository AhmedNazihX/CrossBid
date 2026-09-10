"""S1.1.1 — wire payload to cache row, and the sort stability the cache depends on.

The shuffle test at the bottom is the one that matters for "a second run changes nothing":
eCertis promises no ordering for any of its arrays, so the normaliser has to be a pure
function of the *set* of things it was given, not of the order they arrived in.
"""

from __future__ import annotations

import json
import random
from typing import Any

import pytest

from crossbid.reference.ecertis_client import (
    _stable_text,
    _sub_criteria,
    _text,
    canonical_json,
)
from crossbid.reference.ecertis_schema import WireCriterionDetail, WireText

SHUFFLE_SEEDS = (0, 1, 7, 42, 1234)
ARRAY_KEYS = (
    "SubCriterion",
    "RequirementGroup",
    "TypeOfEvidence",
    "LegislationReference",
    "JurisdictionLevelCode",
    "EvidenceIssuerParty",
    "PartyName",
    "EvidenceDocumentReference",
    "criterion",
)


def _normalise(payload: dict[str, Any]) -> str:
    """The cache rows this payload produces, in canonical form."""
    detail = WireCriterionDetail.model_validate(payload)
    rows = [sub.model_dump(mode="json") for sub in _sub_criteria(detail)]
    return canonical_json({"sub_criteria": rows})


def _shuffle_deep(value: Any, rng: random.Random) -> Any:
    """A copy of `value` with every eCertis array reordered. Never mutates the input."""
    if isinstance(value, dict):
        items = [(key, _shuffle_deep(item, rng)) for key, item in value.items()]
        rng.shuffle(items)
        return dict(items)
    if isinstance(value, list):
        shuffled = [_shuffle_deep(item, rng) for item in value]
        rng.shuffle(shuffled)
        return shuffled
    return value


# ------------------------------------------------------------------------- scalar helpers


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ({"value": "Freistellungsbescheinigung"}, "Freistellungsbescheinigung"),
        ({"value": "competent tax office\n"}, "competent tax office"),
        ({"value": "  Has  extra   spaces\nand a newline  "}, "Has extra spaces and a newline"),
        ({"value": ""}, ""),
        ({}, ""),
        ({"value": None}, ""),
    ],
)
def test_text_collapses_whitespace_and_tolerates_absence(
    raw: dict[str, Any], expected: str
) -> None:
    # Act / Assert
    assert _text(WireText.model_validate(raw)) == expected


def test_text_of_none_is_empty() -> None:
    # Act / Assert
    assert _text(None) == ""


def test_stable_text_handles_the_object_form() -> None:
    # Act / Assert
    assert _stable_text(WireText(value="1 Years")) == "1 Years"


def test_stable_text_handles_the_list_form() -> None:
    # Act / Assert
    assert _stable_text([WireText(value="1 Years")]) == "1 Years"


def test_stable_text_skips_empty_entries() -> None:
    # Act / Assert
    assert _stable_text([WireText(), WireText(value="3 Months")]) == "3 Months"


def test_stable_text_is_independent_of_list_order() -> None:
    """A reordered list must not change the cache — see the docstring on `_stable_text`."""
    # Arrange
    forward = [WireText(value="b"), WireText(value="a")]
    backward = [WireText(value="a"), WireText(value="b")]

    # Act / Assert
    assert _stable_text(forward) == _stable_text(backward) == "a"


@pytest.mark.parametrize("empty", [None, [], WireText(), WireText(value="")])
def test_stable_text_of_nothing_is_empty(empty: Any) -> None:
    # Act / Assert
    assert _stable_text(empty) == ""


# -------------------------------------------------------------- the recorded DE criterion


def test_recorded_detail_normalises_to_the_expected_shape(ecertis_fixture: Any) -> None:
    # Arrange
    detail = WireCriterionDetail.model_validate(ecertis_fixture("criterion_detail_de_taxes"))

    # Act
    subs = _sub_criteria(detail)

    # Assert
    assert [sub.id for sub in subs] == sorted(sub.id for sub in subs)
    assert len(subs) == 3
    assert sum(len(sub.evidences) for sub in subs) == 7


def test_recorded_detail_keeps_the_national_legislation_reference(
    ecertis_fixture: Any,
) -> None:
    """The German § reference is the citation the matrix shows next to the evidence."""
    # Arrange
    detail = WireCriterionDetail.model_validate(ecertis_fixture("criterion_detail_de_taxes"))

    # Act
    subs = _sub_criteria(detail)
    articles = {law.article for sub in subs for law in sub.legislation}

    # Assert
    assert any(article.startswith("§") for article in articles)
    assert all(law.jurisdiction == "de" for sub in subs for law in sub.legislation)


def test_recorded_detail_carries_issuer_and_validity(ecertis_fixture: Any) -> None:
    # Arrange
    detail = WireCriterionDetail.model_validate(ecertis_fixture("criterion_detail_de_taxes"))

    # Act
    evidences = [e for sub in _sub_criteria(detail) for e in sub.evidences]
    named = {e.name: e for e in evidences}

    # Assert
    assert "Freistellungsbescheinigung" in named
    assert named["Freistellungsbescheinigung"].issuers == ("competent tax office",)
    assert named["Freistellungsbescheinigung"].validity_period == "1 Years"
    assert named["Freistellungsbescheinigung"].type_code == "Certificate"
    assert named["Freistellungsbescheinigung"].detail_url.startswith("https://")


# ------------------------------------------------------------------------------ edge cases


@pytest.fixture
def edge_subs(ecertis_fixture: Any) -> Any:
    detail = WireCriterionDetail.model_validate(ecertis_fixture("criterion_detail_edge_cases"))
    return _sub_criteria(detail)


def test_sub_criteria_without_an_id_are_dropped(edge_subs: Any) -> None:
    """An id-less row cannot be looked up, so keeping it would only pollute the cache."""
    # Assert
    assert len(edge_subs) == 2
    assert all(sub.id for sub in edge_subs)


def test_sub_criteria_are_sorted_by_id(edge_subs: Any) -> None:
    # Assert
    assert [sub.id for sub in edge_subs] == sorted(sub.id for sub in edge_subs)
    assert edge_subs[0].id.startswith("00000000")


def test_a_sub_criterion_with_no_requirement_group_has_no_evidence(edge_subs: Any) -> None:
    """ "This country files no paperwork for that" is an answer, not a failure."""
    # Assert
    assert edge_subs[0].evidences == ()
    assert edge_subs[0].legislation == ()


def test_evidence_without_an_id_is_dropped(edge_subs: Any) -> None:
    # Arrange
    evidences = edge_subs[1].evidences

    # Assert
    assert {e.id for e in evidences} == {"evidence-shared", "evidence-no-issuer"}


def test_an_evidence_in_two_groups_appears_once_and_records_both_groups(
    edge_subs: Any,
) -> None:
    """`RequirementGroup`s are alternatives; the row is the document, not the alternative."""
    # Arrange
    shared = next(e for e in edge_subs[1].evidences if e.id == "evidence-shared")

    # Assert
    assert shared.groups == ("group-1111", "group-2222")


def test_evidences_are_sorted_by_name_then_id(edge_subs: Any) -> None:
    # Arrange
    evidences = edge_subs[1].evidences

    # Assert
    assert [(e.name, e.id) for e in evidences] == sorted((e.name, e.id) for e in evidences)


def test_issuers_are_deduplicated_sorted_and_whitespace_collapsed(edge_subs: Any) -> None:
    # Arrange
    shared = next(e for e in edge_subs[1].evidences if e.id == "evidence-shared")

    # Assert
    assert shared.issuers == ("Erstes Amt", "Zweites Amt")


def test_an_evidence_with_no_issuer_party_gets_an_empty_tuple(edge_subs: Any) -> None:
    # Arrange
    lonely = next(e for e in edge_subs[1].evidences if e.id == "evidence-no-issuer")

    # Assert
    assert lonely.issuers == ()
    assert lonely.addressee == ""
    assert lonely.jurisdictions == ()
    assert lonely.detail_url == ""
    assert lonely.validity_period == ""


def test_jurisdictions_are_sorted_and_blanks_dropped(edge_subs: Any) -> None:
    # Arrange
    shared = next(e for e in edge_subs[1].evidences if e.id == "evidence-shared")

    # Assert
    assert shared.jurisdictions == ("at", "de")


def test_intended_use_reads_both_the_object_and_the_list_form(edge_subs: Any) -> None:
    # Arrange
    by_id = {e.id: e for e in edge_subs[1].evidences}

    # Assert
    assert by_id["evidence-shared"].intended_use == "Intended use as a list"
    assert by_id["evidence-no-issuer"].intended_use == "Intended use as an object"


def test_the_first_usable_document_reference_wins_over_an_empty_one(edge_subs: Any) -> None:
    """One reference has an empty URI and no validity; the populated one must be picked."""
    # Arrange
    shared = next(e for e in edge_subs[1].evidences if e.id == "evidence-shared")

    # Assert
    assert shared.detail_url == "https://example.invalid/e1"
    assert shared.validity_period == "1 Years"


def test_legislation_is_sorted_by_title(edge_subs: Any) -> None:
    # Arrange
    laws = edge_subs[1].legislation

    # Assert
    assert [law.title for law in laws] == ["AAA", "ZZZ"]
    assert laws[0].uri == ""


def test_whitespace_is_collapsed_in_descriptions(edge_subs: Any) -> None:
    # Assert
    assert edge_subs[1].description == "Has extra spaces and a newline"


def test_an_unknown_future_field_does_not_break_validation(ecertis_fixture: Any) -> None:
    """`extra="ignore"`: a new eCertis field must not fail a build."""
    # Arrange
    payload = ecertis_fixture("criterion_detail_edge_cases")

    # Act / Assert — the fixture carries `SomeFutureFieldWeHaveNotSeenYet`
    assert "SomeFutureFieldWeHaveNotSeenYet" in payload
    assert WireCriterionDetail.model_validate(payload).sub_criterion


def test_normalising_does_not_mutate_the_payload(ecertis_fixture: Any) -> None:
    """Immutable style: the wire payload is read, never edited in place."""
    # Arrange
    payload = ecertis_fixture("criterion_detail_de_taxes")
    before = json.dumps(payload, sort_keys=True)

    # Act
    _normalise(payload)

    # Assert
    assert json.dumps(payload, sort_keys=True) == before


# ----------------------------------------------------------------------- sort stability


@pytest.mark.parametrize("seed", SHUFFLE_SEEDS)
@pytest.mark.parametrize(
    "fixture_name", ["criterion_detail_de_taxes", "criterion_detail_edge_cases"]
)
def test_a_reordered_response_normalises_to_identical_bytes(
    ecertis_fixture: Any, fixture_name: str, seed: int
) -> None:
    """The core of "a second run changes nothing": output depends on content, not order."""
    # Arrange
    payload = ecertis_fixture(fixture_name)
    expected = _normalise(payload)
    shuffled = _shuffle_deep(payload, random.Random(seed))  # noqa: S311  (not cryptographic)

    # Act
    actual = _normalise(shuffled)

    # Assert
    assert actual == expected


def test_the_shuffler_actually_reorders_something(ecertis_fixture: Any) -> None:
    """Guards the test above from passing because the shuffle was a no-op."""
    # Arrange
    payload = ecertis_fixture("criterion_detail_de_taxes")

    # Act
    shuffled = _shuffle_deep(payload, random.Random(0))  # noqa: S311  (not cryptographic)

    # Assert
    assert json.dumps(shuffled) != json.dumps(payload)
    assert any(key in json.dumps(shuffled) for key in ARRAY_KEYS)


def test_normalising_twice_gives_identical_bytes(ecertis_fixture: Any) -> None:
    # Arrange
    payload = ecertis_fixture("criterion_detail_de_taxes")

    # Act / Assert
    assert _normalise(payload) == _normalise(payload)
