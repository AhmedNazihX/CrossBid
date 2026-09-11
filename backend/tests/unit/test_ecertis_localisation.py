"""S1.1.2 — the bidder-language overlay: normalising it, fetching it, reading it back.

The overlay is a *separate* file (`l10n_de.json`) rather than extra fields on the three
S1.1.1 files, and two of these tests exist only to pin that: `criteria.json` feeds the
generated `EcertisCriterionId` Literal (S1.1.3) and every cache file carries a
`content_sha256`, so touching them would churn the enum and the hashes for text no run-time
consumer of those files reads.

The join is on the eCertis UUID, which works only because the three id spaces never
collide: 56 EU criterion ids, 172 national sub-criterion ids and 89 evidence ids across the
DE and FR caches, with zero overlap (measured 2026-09-11). That is asserted here rather
than assumed, because the day it stops being true the overlay silently returns the wrong
German words.
"""

from __future__ import annotations

import contextlib
import json
import socket
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from crossbid.models.ecertis_criteria import CRITERION_IDS
from crossbid.reference import ecertis_client
from crossbid.reference.ecertis_client import (
    MAX_ATTEMPTS,
    EcertisCacheError,
    EcertisRestClient,
    EcertisUnavailableError,
    _localised_criteria,
    _localised_entities,
    canonical_json,
    content_hash,
    criteria_path,
    evidence_path,
    l10n_path,
    load_evidence,
    load_localisation,
)
from crossbid.reference.ecertis_schema import (
    CachedCriterion,
    LocalisationCache,
    WireCriteriaList,
    WireCriterionDetail,
)

BASE_URL = "https://ecertis.invalid/rest/"
TAXES_ID = "b61bbeb7-690e-4a40-bc68-d6d4ecfaa3d4"
FREISTELLUNG_ID = "08900ccb-9a3c-4a2d-ba4c-25197539db6c"
TAXES_SUB_ID = "a9e2613e-0891-4ae8-8fe4-db45eee58997"
COUNTRIES = ("de", "fr")

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture
def cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway cache directory seeded from the committed one, overlay included."""
    sources = (
        criteria_path(),
        *(evidence_path(code) for code in COUNTRIES),
        l10n_path("de"),
    )
    for source in sources:
        (tmp_path / source.name).write_bytes(source.read_bytes())
    monkeypatch.setattr(ecertis_client, "DATA_DIR", tmp_path)
    ecertis_client.clear_caches()
    return tmp_path


def _rest_client(handler: Handler) -> EcertisRestClient:
    transport = httpx.MockTransport(handler)
    return EcertisRestClient(client=httpx.Client(base_url=BASE_URL, transport=transport))


def _scripted(*responses: httpx.Response) -> tuple[Handler, list[httpx.Request]]:
    """Plays `responses` in order, then repeats the last one forever."""
    seen: list[httpx.Request] = []
    queue: Iterator[httpx.Response] = iter(responses)
    last: list[httpx.Response] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        with contextlib.suppress(StopIteration):
            last.append(next(queue))
        return last[-1]

    return handler, seen


def _criterion() -> CachedCriterion:
    return CachedCriterion(
        id=TAXES_ID, name="Payment of taxes", description="", type_name="", version="3"
    )


# ------------------------------------------------------------------------- the normaliser


def test_localised_entities_keys_sub_criteria_and_evidence_on_their_own_uuids(
    ecertis_fixture: Any,
) -> None:
    """One flat map over two id spaces — the join key the overlay is built on."""
    # Arrange
    detail = WireCriterionDetail.model_validate(
        ecertis_fixture("criterion_detail_de_taxes_lang_de")
    )

    # Act
    entries = _localised_entities(detail)

    # Assert
    assert TAXES_SUB_ID in entries
    assert FREISTELLUNG_ID in entries
    assert entries[TAXES_SUB_ID].name.startswith("Entrichtung von Steuern")
    assert entries[FREISTELLUNG_ID].name.startswith("Freistellungsbescheinigung")


def test_localised_entities_keeps_the_machine_translation_marker(
    ecertis_fixture: Any,
) -> None:
    """eCertis stamps `(Automatische Übersetzung)` on translated strings. That is honest
    provenance for a reviewer, so it is cached verbatim rather than stripped."""
    # Arrange
    detail = WireCriterionDetail.model_validate(
        ecertis_fixture("criterion_detail_de_taxes_lang_de")
    )

    # Act
    entries = _localised_entities(detail)

    # Assert
    assert entries[FREISTELLUNG_ID].name.endswith("(Automatische Übersetzung)")
    assert entries[FREISTELLUNG_ID].issuers == ("zuständiges Finanzamt",)


def test_localised_entities_is_independent_of_array_order(ecertis_fixture: Any) -> None:
    """Same reason as `_sub_criteria`: the committed file must not depend on arrival order."""
    # Arrange
    payload = ecertis_fixture("criterion_detail_de_taxes_lang_de")
    reversed_payload = json.loads(json.dumps(payload))
    reversed_payload["SubCriterion"].reverse()
    for sub in reversed_payload["SubCriterion"]:
        sub.get("RequirementGroup", []).reverse()

    # Act
    forward = _localised_entities(WireCriterionDetail.model_validate(payload))
    backward = _localised_entities(WireCriterionDetail.model_validate(reversed_payload))

    # Assert
    assert {k: v.model_dump() for k, v in forward.items()} == {
        k: v.model_dump() for k, v in backward.items()
    }


def test_localised_entities_merges_an_evidence_seen_twice(ecertis_fixture: Any) -> None:
    """The merge rule of `_merge_evidence`, applied to text: smallest non-empty, issuers
    unioned, so a stub occurrence cannot erase a populated one."""
    # Arrange
    payload = ecertis_fixture("criterion_detail_edge_cases")

    # Act
    entries = _localised_entities(WireCriterionDetail.model_validate(payload))

    # Assert
    assert "evidence-shared" in entries
    assert entries["evidence-shared"].name


def test_localised_entities_drops_entities_without_an_id(ecertis_fixture: Any) -> None:
    # Arrange
    payload = ecertis_fixture("criterion_detail_edge_cases")

    # Act
    entries = _localised_entities(WireCriterionDetail.model_validate(payload))

    # Assert
    assert all(entries)


def test_localised_criteria_covers_the_eu_level_ids(ecertis_fixture: Any) -> None:
    # Arrange
    listing = WireCriteriaList.model_validate(ecertis_fixture("criteria_list_lang_de"))

    # Act
    entries = _localised_criteria(listing)

    # Assert
    assert entries[TAXES_ID].name.startswith("Entrichtung von Steuern")
    assert entries[TAXES_ID].description
    assert entries[TAXES_ID].issuers == ()


# ------------------------------------------------------------------------ the REST client


def test_fetch_localised_criteria_asks_for_the_bidder_language(
    ecertis_fixture: Any,
) -> None:
    # Arrange
    handler, seen = _scripted(
        httpx.Response(200, json=ecertis_fixture("criteria_list_lang_de"))
    )

    # Act
    entries = _rest_client(handler).fetch_localised_criteria("de")

    # Assert
    assert seen[0].url.params["lang"] == "de"
    assert TAXES_ID in entries


def test_fetch_localised_evidence_sends_both_the_country_and_the_language(
    ecertis_fixture: Any,
) -> None:
    """`countryFilter` picks the id space, `lang` picks the words. Both are needed."""
    # Arrange
    detail = ecertis_fixture("criterion_detail_de_taxes_lang_de")
    handler, seen = _scripted(httpx.Response(200, json=detail))

    # Act
    entries = _rest_client(handler).fetch_localised_evidence(_criterion(), "de", "de")

    # Assert
    assert seen[0].url.params["countryFilter"] == "de"
    assert seen[0].url.params["lang"] == "de"
    assert FREISTELLUNG_ID in entries


def test_fetch_localised_evidence_of_a_silent_criterion_is_empty_not_an_error(
    no_sleep: None,
) -> None:
    """17 of 56 FR criteria answer `200` with nothing. No German words is not a failure."""
    # Arrange
    handler, seen = _scripted(httpx.Response(200, content=b""))

    # Act
    entries = _rest_client(handler).fetch_localised_evidence(_criterion(), "fr", "de")

    # Assert
    assert entries == {}
    assert len(seen) == MAX_ATTEMPTS


def test_fetch_localised_evidence_still_rejects_a_structurally_wrong_payload(
    no_sleep: None,
) -> None:
    # Arrange
    handler, _seen = _scripted(httpx.Response(200, json={"SubCriterion": "not a list"}))

    # Act / Assert
    with pytest.raises(EcertisUnavailableError, match="unexpected shape"):
        _rest_client(handler).fetch_localised_evidence(_criterion(), "de", "de")


# ------------------------------------------------------------------- the committed overlay


def test_the_committed_overlay_loads() -> None:
    # Act
    cache = load_localisation("de")

    # Assert
    assert isinstance(cache, LocalisationCache)
    assert cache.language == "de"
    assert cache.source_date
    assert cache.ecertis_spec_version == "0.6"


def test_the_overlay_covers_every_eu_criterion() -> None:
    """A criterion the overlay misses would show an English name to a German bidder."""
    # Act
    entries = load_localisation("de").entries

    # Assert
    assert set(CRITERION_IDS) <= set(entries)


@pytest.mark.parametrize("country", COUNTRIES)
def test_the_overlay_covers_every_cached_sub_criterion_and_evidence(country: str) -> None:
    # Arrange
    cache = load_evidence(country)
    cached_ids = {sub.id for row in cache.criteria for sub in row.sub_criteria} | {
        evidence.id
        for row in cache.criteria
        for sub in row.sub_criteria
        for evidence in sub.evidences
    }

    # Act
    entries = load_localisation("de").entries

    # Assert
    assert cached_ids <= set(entries)


def test_the_three_id_spaces_do_not_collide() -> None:
    """The whole flat-map design rests on this. See the module docstring."""
    # Arrange
    criteria = set(CRITERION_IDS)
    subs: set[str] = set()
    evidences: set[str] = set()
    for country in COUNTRIES:
        for row in load_evidence(country).criteria:
            subs |= {sub.id for sub in row.sub_criteria}
            evidences |= {e.id for sub in row.sub_criteria for e in sub.evidences}

    # Assert
    assert criteria.isdisjoint(subs)
    assert criteria.isdisjoint(evidences)
    assert subs.isdisjoint(evidences)


def test_the_overlay_answers_the_story_case() -> None:
    """S1.1.2: "payment of taxes", bidder DE — name, issuer and description in German."""
    # Act
    entries = load_localisation("de").entries

    # Assert
    assert entries[TAXES_ID].name.startswith("Entrichtung von Steuern")
    assert entries[FREISTELLUNG_ID].name.startswith("Freistellungsbescheinigung")
    assert entries[FREISTELLUNG_ID].issuers == ("zuständiges Finanzamt",)


def test_the_overlay_entries_are_read_only() -> None:
    """The cache is memoised and shared; one caller must not be able to edit it for all."""
    # Arrange
    entries = load_localisation("de").entries

    # Act / Assert
    with pytest.raises(TypeError):
        entries["x"] = entries[TAXES_ID]  # type: ignore[index]


def test_the_overlay_round_trips_through_a_dump() -> None:
    """The read-only map needs a serialiser of its own: pydantic-core refuses a
    `mappingproxy`, and a cache that cannot be dumped cannot be diffed or re-validated."""
    # Arrange
    cache = load_localisation("de")

    # Act
    dumped = cache.model_dump(mode="json")

    # Assert
    assert dumped["entries"][TAXES_ID]["name"].startswith("Entrichtung von Steuern")
    assert LocalisationCache.model_validate(dumped) == cache


def test_load_localisation_is_case_insensitive_and_memoised() -> None:
    # Act / Assert
    assert load_localisation("DE") is load_localisation("de")


def test_loading_the_overlay_opens_no_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the overlay loader tried to open a socket")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    ecertis_client.clear_caches()

    # Act / Assert
    assert load_localisation("de").entries


def test_clear_caches_drops_the_overlay_too() -> None:
    # Arrange
    first = load_localisation("de")

    # Act
    ecertis_client.clear_caches()

    # Assert
    assert load_localisation("de") is not first


def test_an_uncached_language_names_the_build_script() -> None:
    # Act / Assert
    with pytest.raises(EcertisCacheError, match="build_ecertis_cache"):
        load_localisation("pl")


def test_a_hand_edited_overlay_is_refused(cache_dir: Path) -> None:
    # Arrange
    path = cache_dir / l10n_path("de").name
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["entries"][TAXES_ID]["name"] = "tampered"
    path.write_text(canonical_json(payload), encoding="utf-8")

    # Act / Assert
    with pytest.raises(EcertisCacheError, match="has been hand-edited"):
        load_localisation("de")


def test_a_correctly_hashed_but_wrongly_shaped_overlay_is_refused(cache_dir: Path) -> None:
    # Arrange
    path = cache_dir / l10n_path("de").name
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["entries"] = {"x": {"name": 1}}
    payload.pop("content_sha256")
    payload["content_sha256"] = content_hash(payload)
    path.write_text(canonical_json(payload), encoding="utf-8")

    # Act / Assert
    with pytest.raises(EcertisCacheError, match="does not match LocalisationCache"):
        load_localisation("de")


@pytest.mark.parametrize(
    ("given", "expected"), [("de", "l10n_de.json"), ("DE", "l10n_de.json")]
)
def test_l10n_path_lowercases_the_language(given: str, expected: str) -> None:
    # Act / Assert
    assert l10n_path(given).name == expected
    assert l10n_path(given).parent.parts[-2:] == ("data", "ecertis")


# --------------------------------------------------- the S1.1.1 files stay byte-identical


def test_the_overlay_did_not_touch_the_s1_1_1_caches() -> None:
    """`criteria.json` feeds the generated Literal and every file carries a hash, so the
    overlay is additive by construction: no `language` key anywhere in the three."""
    # Arrange
    paths = (criteria_path(), *(evidence_path(code) for code in COUNTRIES))

    # Act
    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in paths]

    # Assert
    assert all("language" not in payload for payload in payloads)
    assert all(payload["schema_version"] == 1 for payload in payloads)
