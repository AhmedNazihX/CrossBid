"""S1.1.3 — the generated criterion enum.

Acceptance criterion, verbatim: *Given the generator, then the `Literal` type matches the
cache and the extraction schema rejects unknown ids.*

The byte-identity test is the load-bearing one. Everything else here would still pass if
someone edited `crossbid/models/ecertis_criteria.py` by hand and forgot to rebuild the
cache, or rebuilt the cache and forgot to regenerate the enum; re-rendering from the
committed `criteria.json` and comparing bytes is what actually catches a stale generated
file in CI.
"""

from __future__ import annotations

from types import MappingProxyType, ModuleType

import pytest
from pydantic import BaseModel, ValidationError, create_model

from crossbid.models.ecertis_criteria import (
    CRITERION_IDS,
    CRITERION_NAMES,
    EcertisCriterionId,
)
from crossbid.reference.ecertis_client import load_criteria

UNKNOWN_ID = "iso-27001"
"""eCertis does not map arbitrary standards, so this is exactly what an LLM would invent."""


@pytest.fixture(scope="module")
def extraction_probe() -> type[BaseModel]:
    """Stand-in for `Requirement.ecertis_criterion_id` (S0.4.1), carrying the real type.

    Built with `create_model` rather than a `class` body because `from __future__ import
    annotations` would stringify the annotation and pydantic cannot resolve a local name.
    """
    return create_model("ExtractionProbe", ecertis_criterion_id=(EcertisCriterionId, ...))


def test_literal_matches_the_committed_cache() -> None:
    # Arrange
    cached_ids = {criterion.id for criterion in load_criteria().criteria}

    # Act / Assert
    assert set(CRITERION_IDS) == cached_ids
    assert len(CRITERION_IDS) == len(cached_ids), "the Literal has a duplicate id"


def test_criterion_names_match_the_committed_cache() -> None:
    # Arrange
    expected = {criterion.id: criterion.name for criterion in load_criteria().criteria}

    # Act / Assert
    assert dict(CRITERION_NAMES) == expected


def test_criterion_ids_are_sorted_and_agree_with_the_name_mapping() -> None:
    # Act / Assert
    assert tuple(sorted(CRITERION_IDS)) == CRITERION_IDS
    assert tuple(CRITERION_NAMES) == CRITERION_IDS


def test_criterion_names_is_not_mutable() -> None:
    """`models/` is the contract layer; a caller must not be able to edit the lookup."""
    # Assert
    assert isinstance(CRITERION_NAMES, MappingProxyType)
    with pytest.raises(TypeError):
        CRITERION_NAMES["new-id"] = "injected"  # type: ignore[index]


def test_extraction_schema_accepts_a_real_criterion_id(
    extraction_probe: type[BaseModel],
) -> None:
    # Arrange
    known = CRITERION_IDS[0]

    # Act
    parsed = extraction_probe(ecertis_criterion_id=known)

    # Assert
    assert parsed.model_dump() == {"ecertis_criterion_id": known}


@pytest.mark.parametrize(
    "rejected",
    [
        UNKNOWN_ID,
        "",
        "b61bbeb7-690e-4a40-bc68-d6d4ecfaa3d5",  # a real id with its last character bumped
        "a9e2613e-0891-4ae8-8fe4-db45eee58997",  # a *national* sub-criterion id, not EU-level
    ],
)
def test_extraction_schema_rejects_unknown_ids(
    extraction_probe: type[BaseModel], rejected: str
) -> None:
    # Act / Assert
    with pytest.raises(ValidationError) as caught:
        extraction_probe(ecertis_criterion_id=rejected)
    assert caught.value.errors()[0]["type"] == "literal_error"


def test_national_sub_criterion_ids_are_not_in_the_literal() -> None:
    """The whole point of finding #1: national ids are a different id space.

    `criteria?nationalEntity=de` returns country-scoped UUIDs for the same 56 criteria.
    If any of them leaked into the enum, a criterion extracted from a French tender could
    not be looked up against German evidence.
    """
    # Arrange
    from crossbid.reference.ecertis_client import load_evidence

    national_ids = {sub.id for row in load_evidence("de").criteria for sub in row.sub_criteria}

    # Assert
    assert national_ids, "the DE evidence cache has no sub-criteria at all"
    assert national_ids.isdisjoint(set(CRITERION_IDS))


def test_regenerating_the_enum_reproduces_the_committed_file_byte_for_byte(
    ecertis_generator: ModuleType,
) -> None:
    """Fails when the generated file is stale — the reason this test exists.

    Compared as bytes, not as an AST or a parsed value, because `ruff format --check` runs
    over the generated file too: a layout drift is a CI failure just as much as a missing
    criterion is.
    """
    # Arrange
    cache = load_criteria()

    # Act
    rendered = ecertis_generator._render_enum(cache.criteria, cache.source_date)
    committed = ecertis_generator.GENERATED_ENUM_PATH.read_text(encoding="utf-8")

    # Assert
    assert rendered == committed, (
        "crossbid/models/ecertis_criteria.py is out of date with "
        "crossbid/reference/data/ecertis/criteria.json. "
        "Run `uv run python scripts/build_ecertis_cache.py`."
    )


def test_generated_file_is_marked_as_generated(ecertis_generator: ModuleType) -> None:
    """A future maintainer has to be told not to edit it, in the file itself."""
    # Arrange
    committed = ecertis_generator.GENERATED_ENUM_PATH.read_text(encoding="utf-8")

    # Assert
    assert "GENERATED FILE" in committed
    assert "do not hand-edit" in committed
    assert ecertis_generator.GENERATOR_NAME in committed
    assert committed.endswith("\n")


def test_generated_enum_imports_nothing_from_crossbid(ecertis_generator: ModuleType) -> None:
    """`models/` is the bottom of the dependency order and must stay there."""
    # Arrange
    committed = ecertis_generator.GENERATED_ENUM_PATH.read_text(encoding="utf-8")

    # Assert
    import_lines = [
        line for line in committed.splitlines() if line.startswith(("import ", "from "))
    ]
    assert import_lines, "the generated file has no imports at all"
    assert "crossbid" not in "\n".join(import_lines)
