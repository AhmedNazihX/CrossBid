"""S1.1.1 — the run-time half: read the committed JSON, never open a socket.

Half of these run against the real committed cache (that is the artefact the graph will
use, so it is worth asserting on directly); the rest repoint `DATA_DIR` at a `tmp_path` so
that a corruption test never writes to a tracked file.
"""

from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from crossbid.models.ecertis_criteria import CRITERION_IDS, CRITERION_NAMES
from crossbid.reference import ecertis_client
from crossbid.reference.ecertis_client import (
    EcertisCacheError,
    canonical_json,
    content_hash,
    criteria_path,
    evidence_path,
    find_evidence,
    load_criteria,
    load_evidence,
)

TAXES_ID = "b61bbeb7-690e-4a40-bc68-d6d4ecfaa3d4"
UNKNOWN_ID = "iso-27001"
COUNTRIES = ("de", "fr")


@pytest.fixture
def cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway cache directory, seeded from the committed one.

    `DATA_DIR` is read inside `criteria_path()` on every call, so repointing it here is
    enough; the autouse `_reset_ecertis_caches` fixture clears the `lru_cache`s around it.
    """
    for source in (criteria_path(), *(evidence_path(code) for code in COUNTRIES)):
        (tmp_path / source.name).write_bytes(source.read_bytes())
    monkeypatch.setattr(ecertis_client, "DATA_DIR", tmp_path)
    ecertis_client.clear_caches()
    return tmp_path


def _rehash(path: Path, mutate: Any) -> None:
    """Apply `mutate` to a cache file and re-stamp its hash, so it still loads."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    payload.pop("content_sha256", None)
    payload["content_sha256"] = content_hash(payload)
    path.write_text(canonical_json(payload), encoding="utf-8")


# ------------------------------------------------------------------- the committed cache


def test_the_committed_criteria_cache_loads() -> None:
    # Act
    cache = load_criteria()

    # Assert
    assert len(cache.criteria) == len(CRITERION_IDS)
    assert cache.source_date
    assert cache.ecertis_spec_version == "0.6"
    assert cache.source.startswith("https://ec.europa.eu/")


@pytest.mark.parametrize("country", COUNTRIES)
def test_every_evidence_file_is_keyed_on_the_criterion_list(country: str) -> None:
    """A row per EU criterion, present or not — so a lookup can tell absent from unknown."""
    # Act
    cache = load_evidence(country)

    # Assert
    assert {row.criterion_id for row in cache.criteria} == set(CRITERION_IDS)
    assert cache.country == country


@pytest.mark.parametrize("country", COUNTRIES)
def test_evidence_rows_carry_the_criterion_name_from_the_criteria_cache(country: str) -> None:
    # Act
    cache = load_evidence(country)

    # Assert
    assert {row.criterion_id: row.criterion_name for row in cache.criteria} == dict(
        CRITERION_NAMES
    )


def test_the_committed_cache_is_the_cross_border_wedge() -> None:
    """The S1.1.2 case, straight off disk: same criterion, different national paper."""
    # Act
    german = find_evidence(TAXES_ID, "de")
    french = find_evidence(TAXES_ID, "fr")

    # Assert
    assert german is not None and french is not None
    german_docs = {e.name for sub in german.sub_criteria for e in sub.evidences}
    french_docs = {e.name for sub in french.sub_criteria for e in sub.evidences}
    assert "Freistellungsbescheinigung" in german_docs
    assert any(name.startswith("Tax attestation") for name in french_docs)
    assert german_docs.isdisjoint(french_docs)


def test_loading_opens_no_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run-time code must work with the network unplugged (docs/project-plan.md)."""

    # Arrange
    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the cache loader tried to open a socket")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    ecertis_client.clear_caches()

    # Act / Assert
    assert load_criteria().criteria
    assert find_evidence(TAXES_ID, "de") is not None


# ------------------------------------------------------------------------------- lookups


def test_find_evidence_returns_none_for_an_unknown_criterion() -> None:
    """S1.1.2's `not_found`: never an exception."""
    # Act / Assert
    assert find_evidence(UNKNOWN_ID, "de") is None


def test_find_evidence_returns_none_for_a_national_sub_criterion_id() -> None:
    """National ids are a different id space; asking with one is a miss, not a hit."""
    # Arrange
    national = next(sub.id for row in load_evidence("de").criteria for sub in row.sub_criteria)

    # Act / Assert
    assert find_evidence(national, "de") is None


def test_a_criterion_with_no_national_entry_returns_an_empty_row() -> None:
    """ "France files no paper for that" is an answer; it must not look like a miss."""
    # Arrange
    silent = [row for row in load_evidence("fr").criteria if not row.sub_criteria]

    # Act
    found = find_evidence(silent[0].criterion_id, "fr")

    # Assert
    assert silent, "the FR cache is expected to have criteria with no national entry"
    assert found is not None
    assert found.sub_criteria == ()
    assert found.criterion_name


def test_find_evidence_accepts_an_uppercase_country_code() -> None:
    # Act / Assert
    assert find_evidence(TAXES_ID, "DE") is not None


def test_load_evidence_is_case_insensitive_and_memoised() -> None:
    """One file, one parse: `lru_cache` keys must not split on letter case."""
    # Act / Assert
    assert load_evidence("DE") is load_evidence("de")


def test_load_criteria_is_memoised() -> None:
    # Act / Assert
    assert load_criteria() is load_criteria()


def test_clear_caches_forces_a_reread() -> None:
    # Arrange
    first = load_criteria()

    # Act
    ecertis_client.clear_caches()

    # Assert
    assert load_criteria() is not first


def test_loaded_models_are_frozen() -> None:
    """Shared, memoised objects: a caller must not be able to edit them for everyone."""
    # Arrange
    cache = load_criteria()

    # Act / Assert
    with pytest.raises(ValidationError):
        cache.criteria[0].name = "edited"  # type: ignore[misc]


# ------------------------------------------------------------------- corruption handling


def test_a_missing_criteria_file_names_the_build_script(
    cache_dir: Path,
) -> None:
    # Arrange
    (cache_dir / criteria_path().name).unlink()

    # Act / Assert
    with pytest.raises(EcertisCacheError, match="build_ecertis_cache"):
        load_criteria()


def test_a_missing_evidence_file_is_reported_with_its_path(cache_dir: Path) -> None:
    # Arrange
    (cache_dir / evidence_path("fr").name).unlink()

    # Act / Assert
    with pytest.raises(EcertisCacheError, match=r"evidence_fr\.json is missing"):
        load_evidence("fr")


def test_a_hand_edited_cache_is_refused(cache_dir: Path) -> None:
    """The point of `content_sha256`: the file is generated, never edited."""
    # Arrange
    path = cache_dir / criteria_path().name
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["criteria"][0]["name"] = "ISO 27001"
    path.write_text(canonical_json(payload), encoding="utf-8")

    # Act / Assert
    with pytest.raises(EcertisCacheError, match="has been hand-edited"):
        load_criteria()


def test_a_hand_edited_evidence_file_is_refused(cache_dir: Path) -> None:
    # Arrange
    path = cache_dir / evidence_path("de").name
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["criteria"][0]["criterion_name"] = "tampered"
    path.write_text(canonical_json(payload), encoding="utf-8")

    # Act / Assert
    with pytest.raises(EcertisCacheError, match="has been hand-edited"):
        load_evidence("de")


def test_a_stripped_hash_is_refused(cache_dir: Path) -> None:
    """Deleting the hash must not be a way to bypass the check."""
    # Arrange
    path = cache_dir / criteria_path().name
    payload = json.loads(path.read_text(encoding="utf-8"))
    del payload["content_sha256"]
    path.write_text(canonical_json(payload), encoding="utf-8")

    # Act / Assert
    with pytest.raises(EcertisCacheError, match="has been hand-edited"):
        load_criteria()


def test_malformed_json_is_reported_as_unreadable(cache_dir: Path) -> None:
    # Arrange
    (cache_dir / criteria_path().name).write_text("{ not json", encoding="utf-8")

    # Act / Assert
    with pytest.raises(EcertisCacheError, match="could not be read"):
        load_criteria()


def test_a_json_array_instead_of_an_object_is_refused(cache_dir: Path) -> None:
    # Arrange
    (cache_dir / criteria_path().name).write_text("[1, 2, 3]", encoding="utf-8")

    # Act / Assert
    with pytest.raises(EcertisCacheError, match="not a JSON object"):
        load_criteria()


def test_a_correctly_hashed_but_wrongly_shaped_cache_is_refused(cache_dir: Path) -> None:
    """A valid hash proves the file was generated, not that it matches today's schema."""
    # Arrange
    path = cache_dir / criteria_path().name
    _rehash(path, lambda payload: payload.__setitem__("criteria", [{"id": "x"}]))

    # Act / Assert
    with pytest.raises(EcertisCacheError, match="does not match CriteriaCache"):
        load_criteria()


def test_an_unknown_field_in_the_cache_is_refused(cache_dir: Path) -> None:
    """`extra="forbid"` on our own shape: the cache is not a place for stray keys."""
    # Arrange
    path = cache_dir / evidence_path("de").name
    _rehash(path, lambda payload: payload.__setitem__("surprise", 1))

    # Act / Assert
    with pytest.raises(EcertisCacheError, match="does not match EvidenceCache"):
        load_evidence("de")


def test_a_bad_country_code_in_the_cache_is_refused(cache_dir: Path) -> None:
    # Arrange
    path = cache_dir / evidence_path("de").name
    _rehash(path, lambda payload: payload.__setitem__("country", "DEU"))

    # Act / Assert
    with pytest.raises(EcertisCacheError, match="does not match EvidenceCache"):
        load_evidence("de")


# --------------------------------------------------------------------------------- paths


def test_criteria_path_points_inside_the_reference_package() -> None:
    # Act / Assert
    assert criteria_path().name == "criteria.json"
    assert criteria_path().parent.parts[-2:] == ("data", "ecertis")


@pytest.mark.parametrize(
    ("given", "expected"), [("de", "evidence_de.json"), ("FR", "evidence_fr.json")]
)
def test_evidence_path_lowercases_the_country_code(given: str, expected: str) -> None:
    # Act / Assert
    assert evidence_path(given).name == expected
