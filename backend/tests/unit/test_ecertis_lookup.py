"""S1.1.2 — the run-time join: English cache + bidder-language overlay, in one answer.

Every test here runs against the real committed cache, because the answer the graph will
show a reviewer is exactly this one, and a fixture would only prove that the join works on
data we made up.

The contract this file exists to pin is negative: `lookup_evidence` never raises. An
unknown id, an uncached country, an uncached language and a criterion the country files no
paper for are four different ways of having nothing to say, and all four have to come back
as a value the model can read.
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

from crossbid.reference import ecertis_client, ecertis_lookup
from crossbid.reference.ecertis_lookup import (
    UNKNOWN_COUNTRY,
    EvidenceStatus,
    lookup_evidence,
)
from crossbid.reference.ecertis_schema import (
    CachedCriterionEvidence,
    CachedEvidence,
    CachedSubCriterion,
)

TAXES_ID = "b61bbeb7-690e-4a40-bc68-d6d4ecfaa3d4"
UNKNOWN_ID = "iso-27001"


@pytest.fixture
def empty_cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A cache directory with nothing in it, so every loader raises."""
    monkeypatch.setattr(ecertis_client, "DATA_DIR", tmp_path)
    ecertis_client.clear_caches()
    return tmp_path


# ---------------------------------------------------------------------------- the hit


def test_the_story_case_answers_in_german_and_english() -> None:
    """ "Payment of taxes", bidder country DE: name, issuer and description, both languages."""
    # Act
    answer = lookup_evidence(TAXES_ID, "de", "de")

    # Assert
    assert answer.status is EvidenceStatus.FOUND
    assert answer.criterion_name == "Payment of taxes"
    assert answer.criterion_name_localised.startswith("Entrichtung von Steuern")
    named = {evidence.name: evidence for evidence in answer.evidences}
    freistellung = named["Freistellungsbescheinigung"]
    assert freistellung.issuers == ("competent tax office",)
    assert freistellung.issuers_localised == ("zuständiges Finanzamt",)
    certificate = named["Certificate on the payment of taxes"]
    assert certificate.name_localised.startswith("Bescheinigung in Steuersachen")
    assert "48b EStG" in certificate.description
    assert "48b EStG" in certificate.description_localised


def test_the_same_criterion_yields_a_different_paper_in_france() -> None:
    """The cross-border wedge, as one call per country."""
    # Act
    german = lookup_evidence(TAXES_ID, "de", "de")
    french = lookup_evidence(TAXES_ID, "fr", "de")

    # Assert
    assert french.status is EvidenceStatus.FOUND
    assert {e.name for e in german.evidences}.isdisjoint({e.name for e in french.evidences})
    assert any(e.name.startswith("Tax attestation") for e in french.evidences)


def test_the_answer_reports_the_country_and_language_it_used() -> None:
    # Act
    answer = lookup_evidence(TAXES_ID, "DE", "DE")

    # Assert
    assert answer.country == "de"
    assert answer.language == "de"


def test_evidences_are_deduplicated_and_ordered_by_name() -> None:
    """Sub-criteria are an eCertis implementation detail; a reviewer wants a document list."""
    # Act
    answer = lookup_evidence(TAXES_ID, "de", "de")

    # Assert
    ids = [evidence.id for evidence in answer.evidences]
    assert len(ids) == len(set(ids))
    assert [e.name for e in answer.evidences] == sorted(e.name for e in answer.evidences)


def test_one_document_under_two_sub_criteria_is_listed_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defensive, not observed: no committed criterion does this today, but eCertis does
    not promise it never will, and a reviewer must not be told to attach the same paper
    twice. Built by hand for that reason — the real cache cannot exercise it."""
    # Arrange
    paper = CachedEvidence(
        id="evidence-shared",
        type_code="Certificate",
        name="Führungszeugnis",
        description="",
        issuers=("Bundesamt für Justiz",),
        addressee="",
        jurisdictions=(),
        validity_period="",
        intended_use="",
        detail_url="",
        groups=(),
    )
    row = CachedCriterionEvidence(
        criterion_id=TAXES_ID,
        criterion_name="Payment of taxes",
        sub_criteria=(
            CachedSubCriterion(
                id="sub-a", name="", description="", legislation=(), evidences=(paper,)
            ),
            CachedSubCriterion(
                id="sub-b", name="", description="", legislation=(), evidences=(paper,)
            ),
        ),
    )
    monkeypatch.setattr(ecertis_lookup, "find_evidence", lambda *_args: row)

    # Act
    answer = lookup_evidence(TAXES_ID, "de", "de")

    # Assert
    assert [evidence.id for evidence in answer.evidences] == ["evidence-shared"]


def test_every_evidence_carries_its_ecertis_detail_url() -> None:
    """The reviewer's way out of a machine translation: the page the text came from."""
    # Act
    answer = lookup_evidence(TAXES_ID, "de", "de")

    # Assert
    assert any(evidence.detail_url.startswith("https://") for evidence in answer.evidences)


def test_lookup_opens_no_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the lookup tried to open a socket")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    ecertis_client.clear_caches()

    # Act / Assert
    assert lookup_evidence(TAXES_ID, "de", "de").evidences


# ------------------------------------------------------------------ the four ways to miss


def test_an_unknown_criterion_is_not_found_not_an_exception() -> None:
    """The acceptance criterion, and the reason the tool cannot throw at the model."""
    # Act
    answer = lookup_evidence(UNKNOWN_ID, "de", "de")

    # Assert
    assert answer.status is EvidenceStatus.NOT_FOUND
    assert answer.evidences == ()
    assert answer.criterion_id == UNKNOWN_ID


def test_a_country_with_no_national_entry_is_not_found() -> None:
    """DE files no paper for 1 of the 56 criteria; that is an answer, not a failure."""
    # Arrange
    silent = next(
        row.criterion_id
        for row in ecertis_client.load_evidence("fr").criteria
        if not row.sub_criteria
    )

    # Act
    answer = lookup_evidence(silent, "fr", "de")

    # Assert
    assert answer.status is EvidenceStatus.NOT_FOUND
    assert answer.evidences == ()
    assert answer.criterion_name, "the criterion is known even though France files nothing"


def test_an_uncached_country_is_not_found() -> None:
    """Only DE and FR are built. Asking for IT must not blow up a requirement check."""
    # Act
    answer = lookup_evidence(TAXES_ID, "it", "de")

    # Assert
    assert answer.status is EvidenceStatus.NOT_FOUND
    assert answer.evidences == ()


@pytest.mark.parametrize("country", ["deu", "d", "", "../../etc/passwd"])
def test_a_country_that_is_not_a_country_code_is_not_found_under_the_unknown_code(
    country: str,
) -> None:
    """The answer's country is carried onto a matrix row, where two letters is the contract.

    Echoing the caller's string back would push the failure one call downstream, into
    `to_matrix_evidence` and so into the ReAct loop. `zz` is ISO 3166-1's user-assigned code
    for exactly this. The path-shaped case matters twice: the country names a cache file.
    """
    # Act
    answer = lookup_evidence(TAXES_ID, country)

    # Assert
    assert answer.status is EvidenceStatus.NOT_FOUND
    assert answer.country == UNKNOWN_COUNTRY
    assert answer.evidences == ()


def test_a_missing_cache_directory_is_not_found(empty_cache_dir: Path) -> None:
    """A corrupt deployment must degrade to "I cannot prove it", never to a crashed run."""
    # Act
    answer = lookup_evidence(TAXES_ID, "de", "de")

    # Assert
    assert answer.status is EvidenceStatus.NOT_FOUND


# ------------------------------------------------------------------ degrading to English


def test_an_uncached_language_falls_back_to_the_english_text() -> None:
    """Only `l10n_de.json` is built. A Polish bidder still gets the eCertis answer."""
    # Act
    answer = lookup_evidence(TAXES_ID, "de", "pl")

    # Assert
    assert answer.status is EvidenceStatus.FOUND
    assert answer.language == "pl"
    assert answer.criterion_name_localised == answer.criterion_name
    assert all(e.name_localised == e.name for e in answer.evidences)
    assert all(e.issuers_localised == e.issuers for e in answer.evidences)


def test_english_is_a_language_like_any_other() -> None:
    """`lang=en` is what the cache already holds, so the overlay is simply absent."""
    # Act
    answer = lookup_evidence(TAXES_ID, "de", "en")

    # Assert
    assert answer.criterion_name_localised == answer.criterion_name


def test_the_answer_is_frozen() -> None:
    """It is handed to a matrix row and to the model; nobody edits it on the way."""
    # Arrange
    answer = lookup_evidence(TAXES_ID, "de", "de")

    # Act / Assert
    with pytest.raises(ValueError, match="frozen"):
        answer.status = EvidenceStatus.NOT_FOUND  # type: ignore[misc]
