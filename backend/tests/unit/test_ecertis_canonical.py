"""S1.1.1 — "a second run changes nothing", broken into the invariants that make it true.

Two runs produce identical bytes only if (a) the encoding is a pure function of the
content, ignoring dict insertion order, and (b) `source_date` is derived from the content
rather than read off the clock. Those are the two things asserted here, plus the guard
that stops a hand-edited cache from being loaded as if it were generated.

The last group is the other half of "refusing to write": eCertis answers `200` with an empty
body often enough that a fetch which lost half the register looks exactly like a register
that shrank, so the generator compares against what is committed before it overwrites it.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from crossbid.reference.ecertis_client import canonical_json, content_hash
from crossbid.reference.ecertis_schema import (
    CACHE_SCHEMA_VERSION,
    ECERTIS_SPEC_VERSION,
    CriteriaCache,
)

SOURCE = "https://ec.europa.eu/growth/tools-databases/ecertisrest/"
EARLIER_DATE = "2026-01-31"
LATER_DATE = "2026-09-10"


def _body(name: str = "Payment of taxes") -> dict[str, Any]:
    """The smallest payload `CriteriaCache` accepts, minus the provenance fields."""
    return {
        "source": SOURCE,
        "ecertis_spec_version": ECERTIS_SPEC_VERSION,
        "schema_version": CACHE_SCHEMA_VERSION,
        "criteria": [
            {
                "id": "b61bbeb7-690e-4a40-bc68-d6d4ecfaa3d4",
                "name": name,
                "description": "Has the economic operator breached its obligations...",
                "type_name": "Exclusion Ground / Grounds related to the payment of taxes",
                "version": "3",
            }
        ],
    }


# ------------------------------------------------------------------------ canonical form


def test_canonical_json_ignores_dict_insertion_order() -> None:
    # Arrange
    forward = {"alpha": 1, "beta": {"x": 1, "y": 2}}
    backward = {"beta": {"y": 2, "x": 1}, "alpha": 1}

    # Act / Assert
    assert canonical_json(forward) == canonical_json(backward)


def test_canonical_json_ends_in_exactly_one_newline() -> None:
    # Act
    encoded = canonical_json({"a": 1})

    # Assert
    assert encoded.endswith("\n")
    assert not encoded.endswith("\n\n")


def test_canonical_json_keeps_non_ascii_readable() -> None:
    """`ensure_ascii=False`: the cache is full of German, and \\u00fc escapes are unreadable."""
    # Act
    encoded = canonical_json({"name": "Freistellungsbescheinigung für Grün"})

    # Assert
    assert "für Grün" in encoded
    assert "\\u" not in encoded


def test_canonical_json_uses_a_fixed_indent() -> None:
    # Act
    encoded = canonical_json({"outer": {"inner": 1}})

    # Assert
    assert '\n  "outer"' in encoded
    assert '\n    "inner"' in encoded


def test_canonical_json_round_trips() -> None:
    # Arrange
    payload = _body()

    # Act / Assert
    assert json.loads(canonical_json(payload)) == payload


# -------------------------------------------------------------------------- content hash


def test_content_hash_ignores_insertion_order() -> None:
    # Arrange
    body = _body()
    reordered = {key: body[key] for key in reversed(list(body))}

    # Act / Assert
    assert content_hash(body) == content_hash(reordered)


@pytest.mark.parametrize("provenance", ["source_date", "content_sha256"])
def test_content_hash_excludes_the_provenance_fields(provenance: str) -> None:
    """`source_date` is derived from the hash, so it must not feed back into it."""
    # Arrange
    body = _body()

    # Act / Assert
    assert content_hash(body) == content_hash({**body, provenance: "anything at all"})


def test_content_hash_changes_when_the_data_changes() -> None:
    # Act / Assert
    assert content_hash(_body()) != content_hash(_body(name="Payment of taxes (amended)"))


def test_content_hash_is_a_sha256_hexdigest() -> None:
    # Act
    digest = content_hash(_body())

    # Assert
    assert len(digest) == 64
    assert set(digest) <= set("0123456789abcdef")


# ------------------------------------------------------------------- source_date carry-over


def test_write_cache_stamps_today_on_a_first_write(
    ecertis_generator: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.setattr(ecertis_generator, "_today", lambda: LATER_DATE)
    path = tmp_path / "criteria.json"

    # Act
    outcome = ecertis_generator._write_cache(path, _body(), CriteriaCache)

    # Assert
    assert outcome.changed is True
    assert outcome.source_date == LATER_DATE
    assert json.loads(path.read_text(encoding="utf-8"))["source_date"] == LATER_DATE


def test_write_cache_carries_source_date_over_when_the_content_is_unchanged(
    ecertis_generator: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The acceptance criterion: a second run must not move `source_date`."""
    # Arrange
    path = tmp_path / "criteria.json"
    monkeypatch.setattr(ecertis_generator, "_today", lambda: EARLIER_DATE)
    first = ecertis_generator._write_cache(path, _body(), CriteriaCache)
    before = path.read_bytes()

    # Act — same data, but the calendar has moved on
    monkeypatch.setattr(ecertis_generator, "_today", lambda: LATER_DATE)
    second = ecertis_generator._write_cache(path, _body(), CriteriaCache)

    # Assert
    assert first.source_date == second.source_date == EARLIER_DATE
    assert second.changed is False
    assert path.read_bytes() == before


def test_write_cache_advances_source_date_when_upstream_changed(
    ecertis_generator: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    path = tmp_path / "criteria.json"
    monkeypatch.setattr(ecertis_generator, "_today", lambda: EARLIER_DATE)
    ecertis_generator._write_cache(path, _body(), CriteriaCache)

    # Act
    monkeypatch.setattr(ecertis_generator, "_today", lambda: LATER_DATE)
    outcome = ecertis_generator._write_cache(
        path, _body(name="Payment of taxes (amended)"), CriteriaCache
    )

    # Assert
    assert outcome.changed is True
    assert outcome.source_date == LATER_DATE


def test_write_cache_stamps_today_when_the_old_file_had_no_source_date(
    ecertis_generator: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`source_date` is outside the hash, so a hash match cannot prove it was present."""
    # Arrange
    path = tmp_path / "criteria.json"
    path.write_text(canonical_json(_body()), encoding="utf-8")  # no source_date at all
    monkeypatch.setattr(ecertis_generator, "_today", lambda: LATER_DATE)

    # Act
    outcome = ecertis_generator._write_cache(path, _body(), CriteriaCache)

    # Assert
    assert outcome.source_date == LATER_DATE


def test_write_cache_ignores_an_unreadable_previous_file(
    ecertis_generator: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    path = tmp_path / "criteria.json"
    path.write_text("{ this is not json", encoding="utf-8")
    monkeypatch.setattr(ecertis_generator, "_today", lambda: LATER_DATE)

    # Act
    outcome = ecertis_generator._write_cache(path, _body(), CriteriaCache)

    # Assert
    assert outcome.changed is True
    assert outcome.source_date == LATER_DATE


def test_write_cache_refuses_a_payload_that_does_not_match_the_model(
    ecertis_generator: ModuleType, tmp_path: Path
) -> None:
    # Arrange
    path = tmp_path / "criteria.json"
    broken = {**_body(), "criteria": [{"id": "", "name": "", "description": 1}]}

    # Act / Assert
    with pytest.raises(SystemExit, match="refusing to write"):
        ecertis_generator._write_cache(path, broken, CriteriaCache)
    assert not path.exists()


def test_write_cache_output_is_the_canonical_encoding(
    ecertis_generator: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Whatever the writer does, it must agree with what the loader will hash."""
    # Arrange
    path = tmp_path / "criteria.json"
    monkeypatch.setattr(ecertis_generator, "_today", lambda: LATER_DATE)

    # Act
    ecertis_generator._write_cache(path, _body(), CriteriaCache)
    written = path.read_text(encoding="utf-8")

    # Assert
    assert written == canonical_json(json.loads(written))
    assert json.loads(written)["content_sha256"] == content_hash(_body())


# ------------------------------------------------------------------- the shrink guards


def _overlay(path: Path, entries: Any) -> Path:
    """A committed `l10n_*.json` as the generator would find it on disk."""
    path.write_text(json.dumps({"entries": entries}), encoding="utf-8")
    return path


def test_shrunk_localisation_counts_the_ids_this_fetch_did_not_produce(
    ecertis_generator: ModuleType, tmp_path: Path
) -> None:
    """The number `_build` refuses on: ids the bidder-language overlay would lose."""
    # Arrange
    path = _overlay(tmp_path / "l10n_de.json", {"kept": {}, "lost": {}, "also-lost": {}})

    # Act
    lost = ecertis_generator._shrunk_localisation(path, {"kept": object(), "new": object()})

    # Assert
    assert lost == 2


def test_shrunk_localisation_reports_no_loss_when_nothing_is_committed_yet(
    ecertis_generator: ModuleType, tmp_path: Path
) -> None:
    """A first run has nothing to lose, so the guard must not block the initial build."""
    # Act / Assert
    assert ecertis_generator._shrunk_localisation(tmp_path / "absent.json", {}) == 0


@pytest.mark.parametrize(
    "entries", [["not", "a", "map"], "not a map", None], ids=["list", "string", "null"]
)
def test_shrunk_localisation_refuses_an_overlay_it_cannot_read(
    ecertis_generator: ModuleType, tmp_path: Path, entries: Any
) -> None:
    """An unreadable overlay is not an empty one, and "0 lost" is what licenses the write.

    Answering 0 here would let a fetch that came back half-empty overwrite `l10n_de.json`
    unchallenged — the exact loss the guard exists to prevent, waved through by the guard
    itself. The English pass has no such escape hatch, so this one has none either.
    """
    # Arrange
    path = _overlay(tmp_path / "l10n_de.json", entries)

    # Act / Assert
    with pytest.raises(SystemExit, match="could not be read"):
        ecertis_generator._shrunk_localisation(path, {})
