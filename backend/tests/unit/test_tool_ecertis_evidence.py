"""S1.1.2 — the tool the agent actually calls, and the contract `crossbid.tools` sets.

Two things are worth more than the rest here.

The argument schema is typed on the generated `EcertisCriterionId` Literal, so an invented
id is rejected *before* the function runs — the model gets the 56 legal values in the tool
schema instead of a chance to guess. That is the whole reason S1.1.3 generated the enum, so
it is asserted rather than assumed.

The tool returns a plain dict, not a model and not prose. langchain-core 1.6.2 stringifies
tool output with `json.dumps(..., ensure_ascii=False)` and only falls back to `str()` when
that raises, so a dict reaches the model as JSON with the umlauts intact, while a model
instance would reach it as a Python repr.
"""

from __future__ import annotations

import json

import pytest
from langchain_core.tools import BaseTool
from pydantic import ValidationError

from crossbid.models.matrix import EcertisEvidence
from crossbid.reference import ecertis_client
from crossbid.reference.ecertis_lookup import (
    UNKNOWN_COUNTRY,
    EvidenceStatus,
    lookup_evidence,
)
from crossbid.settings import Settings
from crossbid.tools import ToolContext, ToolManifest
from crossbid.tools.ecertis_evidence import (
    MANIFEST,
    EcertisEvidenceArgs,
    build_tool,
    to_matrix_evidence,
)

TAXES_ID = "b61bbeb7-690e-4a40-bc68-d6d4ecfaa3d4"
COMPANY_ID = "11111111-1111-4111-8111-111111111111"


@pytest.fixture
def context(offline_settings: Settings) -> ToolContext:
    """The eCertis lookup reads no tenant data, so it needs no `db` and no `bid_id`."""
    return ToolContext(settings=offline_settings, company_id=COMPANY_ID)


@pytest.fixture
def tool(context: ToolContext) -> BaseTool:
    return build_tool(context)


# ------------------------------------------------------------------------- the manifest


def test_the_manifest_is_the_name_settings_default_yaml_enables(
    offline_settings: Settings,
) -> None:
    """The registry (S1.4.1) matches on this string; a typo would silently disable the tool."""
    # Assert
    assert isinstance(MANIFEST, ToolManifest)
    assert MANIFEST.name == "ecertis_evidence_lookup"
    assert MANIFEST.name in offline_settings.runtime.enabled_tools
    assert MANIFEST.default_enabled == (
        MANIFEST.name in offline_settings.runtime.enabled_tools
    ), "the flag is a claim about that file; see tests/unit/test_tool_manifests.py"


def test_the_manifest_declares_the_tool_offline() -> None:
    """The cache is committed, so the developer panel may honestly show it as free."""
    # Assert
    assert MANIFEST.external is False


def test_the_description_names_the_countries_the_cache_actually_holds() -> None:
    """It is the model's only clue that asking for Italy will come back empty."""
    # Assert
    assert "DE" in MANIFEST.description
    assert "FR" in MANIFEST.description


# --------------------------------------------------------------------- the argument schema


def test_an_invented_criterion_id_is_rejected_by_the_schema() -> None:
    """The generated Literal, used where it pays: in the model-facing tool schema."""
    # Act / Assert
    with pytest.raises(ValidationError):
        EcertisEvidenceArgs(criterion_id="iso-27001", bidder_country="de")  # type: ignore[arg-type]


def test_a_country_that_is_not_two_letters_is_rejected() -> None:
    # Act / Assert
    with pytest.raises(ValidationError):
        EcertisEvidenceArgs(criterion_id=TAXES_ID, bidder_country="Germany")


def test_the_language_defaults_to_the_one_the_overlay_is_built_for() -> None:
    # Act
    args = EcertisEvidenceArgs(criterion_id=TAXES_ID, bidder_country="de")

    # Assert
    assert args.language == "de"


def test_the_tool_schema_offers_the_model_every_legal_criterion_id(tool: BaseTool) -> None:
    # Act
    schema = EcertisEvidenceArgs.model_json_schema()
    criterion = schema["$defs"]["EcertisCriterionId"] if "$defs" in schema else schema

    # Assert
    assert tool.args_schema is EcertisEvidenceArgs
    assert TAXES_ID in json.dumps(criterion)


# --------------------------------------------------------------------------- the tool


def test_the_tool_carries_the_manifest_name_and_description(tool: BaseTool) -> None:
    # Assert
    assert tool.name == MANIFEST.name
    assert tool.description == MANIFEST.description


def test_invoking_the_tool_returns_the_german_and_english_answer(tool: BaseTool) -> None:
    """The story, end to end: German document, German issuer, English name beside it."""
    # Act
    result = tool.invoke({"criterion_id": TAXES_ID, "bidder_country": "de"})

    # Assert
    assert result["status"] == EvidenceStatus.FOUND
    assert result["criterion_name"] == "Payment of taxes"
    assert result["criterion_name_localised"].startswith("Entrichtung von Steuern")
    named = {evidence["name"]: evidence for evidence in result["evidences"]}
    assert named["Freistellungsbescheinigung"]["issuers"] == ["competent tax office"]
    assert named["Freistellungsbescheinigung"]["issuers_localised"] == ["zuständiges Finanzamt"]


def test_the_tool_output_is_json_the_way_langchain_stringifies_it(tool: BaseTool) -> None:
    """`json.dumps(ensure_ascii=False)`, so the model reads `zuständiges`, not `\\u00e4`."""
    # Act
    result = tool.invoke({"criterion_id": TAXES_ID, "bidder_country": "de"})

    # Assert
    assert "zuständiges Finanzamt" in json.dumps(result, ensure_ascii=False)


def test_a_country_with_no_entry_is_not_found_rather_than_an_exception(
    tool: BaseTool,
) -> None:
    """The acceptance criterion. A tool that throws costs the ReAct loop a whole turn."""
    # Arrange
    silent = next(
        row.criterion_id
        for row in ecertis_client.load_evidence("fr").criteria
        if not row.sub_criteria
    )

    # Act
    result = tool.invoke({"criterion_id": silent, "bidder_country": "fr"})

    # Assert
    assert result["status"] == EvidenceStatus.NOT_FOUND
    assert result["evidences"] == []


def test_an_uncached_country_is_not_found_rather_than_an_exception(tool: BaseTool) -> None:
    # Act
    result = tool.invoke({"criterion_id": TAXES_ID, "bidder_country": "IT"})

    # Assert
    assert result["status"] == EvidenceStatus.NOT_FOUND
    assert result["country"] == "it"


# ---------------------------------------------------------------- the matrix-row converter


def test_the_answer_converts_to_the_matrix_row_object() -> None:
    """`check_reqs` (S3.3.1) attaches this to a row; the tool owns the conversion."""
    # Arrange
    answer = lookup_evidence(TAXES_ID, "de", "de")

    # Act
    evidence = to_matrix_evidence(TAXES_ID, answer)

    # Assert
    assert isinstance(evidence, EcertisEvidence)
    assert evidence.criterion_id == TAXES_ID
    assert evidence.country == "de"
    assert evidence.found is True
    assert any(
        name.startswith("Freistellungsbescheinigung") for name in evidence.evidence_names
    )
    assert "zuständiges Finanzamt" in evidence.issuers


def test_the_converter_prefers_the_bidder_language_names() -> None:
    """The matrix is read by a German bidder, so the row shows the German paper's name."""
    # Arrange
    answer = lookup_evidence(TAXES_ID, "de", "de")

    # Act
    evidence = to_matrix_evidence(TAXES_ID, answer)

    # Assert
    assert any(
        name.startswith("Bescheinigung in Steuersachen") for name in evidence.evidence_names
    )


def test_a_not_found_answer_converts_to_an_honest_empty_row() -> None:
    """`found=False` is the row's way of saying "eCertis knows no paper for this here"."""
    # Arrange
    answer = lookup_evidence(TAXES_ID, "it", "de")

    # Act
    evidence = to_matrix_evidence(TAXES_ID, answer)

    # Assert
    assert evidence.found is False
    assert evidence.evidence_names == ()
    assert evidence.issuers == ()


@pytest.mark.parametrize("country", ["deu", "", "  ", "../../etc/passwd"])
def test_a_country_that_is_not_a_country_still_converts(country: str) -> None:
    """The direct-call path S3.3.1 was told needs no try/except, given a bad country.

    The tool's argument schema refuses anything but two letters, so the model cannot get here
    — but `check_reqs` calls `lookup_evidence` itself with whatever the requirement row
    carries, and `EcertisEvidence.country` is two letters or nothing. Before the answer's own
    field was constrained, `"deu"` travelled all the way to this conversion and raised a
    `ValidationError` inside the per-requirement ReAct loop.
    """
    # Arrange
    answer = lookup_evidence(TAXES_ID, country)

    # Act
    evidence = to_matrix_evidence(TAXES_ID, answer)

    # Assert
    assert answer.country == UNKNOWN_COUNTRY
    assert evidence.country == UNKNOWN_COUNTRY
    assert evidence.found is False


def test_the_converted_row_is_accepted_by_the_matrix_model() -> None:
    """`EcertisEvidence` is frozen and forbids extras, so this is a real contract check."""
    # Arrange
    answer = lookup_evidence(TAXES_ID, "de", "de")

    # Act
    evidence = to_matrix_evidence(TAXES_ID, answer)

    # Assert
    assert EcertisEvidence.model_validate(evidence.model_dump()) == evidence
