"""S2.5.1 — reading a buyer's published ESPD request (DUME), against the committed fixture.

The claim this file pins is the one the whole story rests on: **the French fixture's
`DUME_acheteur.xml` declares 30 `ccv:Criterion` elements and every one of them is a member
of the generated `EcertisCriterionId`**, so a tender that publishes a DUME needs no model to
map its criteria — which is what `CLAUDE.md` says and what nothing had yet implemented.

Everything else here is about what happens when a file is *not* that: an id the register
never heard of, a criterion repeated per lot, a root element that is XML but not an ESPD
request, and the hostile payloads `ingestion/safe_xml.py` refuses. Offline, no model.
"""

from __future__ import annotations

import logging

import pytest

from crossbid.ingestion.espd import EspdParseError, parse_espd_request
from crossbid.models.ecertis_criteria import CRITERION_IDS
from tests.conftest import espd_request_bytes, espd_request_xml

TURNOVER_ID = "499efc97-2ac1-4af2-9e84-323c2ca67747"
TURNOVER_TYPE = "CRITERION.SELECTION.ECONOMIC_FINANCIAL_STANDING.TURNOVER.GENERAL_YEARLY"
MANPOWER_ID = "1f49b3f0-d50f-43f6-8b30-4bafab108b9b"
CORRUPTION_ID = "c27b7c4e-c837-4529-b867-ed55ce639db5"
REFERENCES_ID = "5e506c16-26ab-4e32-bb78-b27f87dc0565"
"""`CRITERION.SELECTION...REFERENCES.SERVICES_DELIVERY_PERFORMANCE`: the one criterion in
the fixture whose `cbc:Description` is a single space, which is why the name matters."""

UNKNOWN_ID = "ffffffff-ffff-4fff-8fff-ffffffffffff"

BILLION_LAUGHS = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;">]>
<lolz>&lol2;</lolz>"""


def criterion(
    identifier: str = TURNOVER_ID,
    type_code: str = TURNOVER_TYPE,
    name: str = "Chiffre d'affaires annuel general",
    description: str = "Chiffre(s) d'affaires annuel general",
) -> tuple[str, str, str, str]:
    return identifier, type_code, name, description


# ------------------------------------------------------------------- the committed fixture


def test_the_french_fixture_declares_thirty_criteria_the_register_knows() -> None:
    """The finding the story exists for: 30 of 30 map with no inference at all."""
    # Act
    request = parse_espd_request(espd_request_bytes())

    # Assert
    assert len(request.criteria) == 30
    assert request.dropped_criterion_count == 0
    assert {c.id for c in request.criteria} <= set(CRITERION_IDS)


def test_a_fixture_criterion_carries_its_type_code_and_the_buyers_own_words() -> None:
    """The buyer's French wording is what a citation shows; the type code is what classifies."""
    # Act
    request = parse_espd_request(espd_request_bytes())
    found = {c.id: c for c in request.criteria}

    # Assert
    turnover = found[TURNOVER_ID]
    assert turnover.type_code == TURNOVER_TYPE
    # The buyer's own typography, curly apostrophe and all: this is a quote, not prose.
    assert turnover.name == "Chiffre d’affaires annuel général"  # noqa: RUF001
    assert turnover.description == "Chiffre(s) d’affaires annuel général"  # noqa: RUF001
    assert found[MANPOWER_ID].type_code.startswith("CRITERION.SELECTION.TECHNICAL")
    assert found[CORRUPTION_ID].type_code == "CRITERION.EXCLUSION.CONVICTIONS.CORRUPTION"


def test_a_blank_description_is_reported_as_blank_rather_than_filled_in() -> None:
    """The reader is faithful to the file; choosing what to show is the mapper's decision."""
    # Act
    request = parse_espd_request(espd_request_bytes())
    references = next(c for c in request.criteria if c.id == REFERENCES_ID)

    # Assert
    assert references.description.strip() == ""
    assert references.name.startswith("Décrivez des principaux services")


def test_the_fixture_declares_no_language() -> None:
    """ESPD 1.0.2 leaves `languageID` off; the caller supplies the tender's own language."""
    assert parse_espd_request(espd_request_bytes()).language is None


# ------------------------------------------------------------------ what is dropped, loudly


def test_a_criterion_the_register_does_not_know_is_dropped_and_counted(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """ADR-0007: an id outside the EU-level register is not a criterion we can look up."""
    # Arrange
    data = espd_request_xml(criterion(), criterion(identifier=UNKNOWN_ID))

    # Act
    with caplog.at_level(logging.WARNING):
        request = parse_espd_request(data)

    # Assert
    assert [c.id for c in request.criteria] == [TURNOVER_ID]
    assert request.dropped_criterion_count == 1
    assert UNKNOWN_ID in caplog.text


def test_a_national_looking_uuid_is_dropped_like_any_other_stranger() -> None:
    """The trap ADR-0007 names: `criteria?nationalEntity=de` ids are UUIDs too, and wrong."""
    # Arrange — a real shape, not a member of the EU-level enum.
    data = espd_request_xml(criterion(identifier="0d3ec09b-1e42-4f43-96e2-9f3cef7f40ab"))

    # Act
    request = parse_espd_request(data)

    # Assert
    assert request.criteria == ()
    assert request.dropped_criterion_count == 1


def test_an_id_is_matched_case_insensitively_and_stored_lower_case() -> None:
    """A DUME may print the UUID in either case; the register's keys are lower case."""
    # Act
    request = parse_espd_request(espd_request_xml(criterion(identifier=TURNOVER_ID.upper())))

    # Assert
    assert [c.id for c in request.criteria] == [TURNOVER_ID]


def test_a_criterion_repeated_per_lot_is_kept_once() -> None:
    """Real DUMEs restate the same criterion for every lot; the matrix wants one row."""
    # Act
    request = parse_espd_request(espd_request_xml(criterion(), criterion(), criterion()))

    # Assert
    assert len(request.criteria) == 1
    assert request.dropped_criterion_count == 0


def test_a_criterion_without_a_type_code_is_dropped() -> None:
    """Without the ESPD type code nothing can classify the row, and guessing is the ban."""
    # Act
    request = parse_espd_request(espd_request_xml(criterion(type_code="  ")))

    # Assert
    assert request.criteria == ()
    assert request.dropped_criterion_count == 1


def test_a_criterion_with_no_wording_at_all_is_dropped() -> None:
    """A requirement whose `source_text` would be empty cites nothing a reviewer can read."""
    # Act
    request = parse_espd_request(espd_request_xml(criterion(name=" ", description=" ")))

    # Assert
    assert request.criteria == ()


def test_a_request_with_no_criteria_parses_to_an_empty_list() -> None:
    """Not an error here: "is this an ESPD request" and "does it say anything" differ."""
    # Act
    request = parse_espd_request(espd_request_xml())

    # Assert
    assert request.criteria == ()
    assert request.dropped_criterion_count == 0


# --------------------------------------------------------------------------- what is refused


def test_a_document_that_is_not_an_espd_request_is_refused() -> None:
    with pytest.raises(EspdParseError, match="ESPD request"):
        parse_espd_request(espd_request_xml(criterion(), root="cac:Tender"))


def test_an_espd_response_is_refused_although_it_carries_criteria() -> None:
    """The bidder's own answer is a different artefact; v1 reads the buyer's request only."""
    with pytest.raises(EspdParseError, match="ESPD request"):
        parse_espd_request(espd_request_xml(criterion(), root="espd:ESPDResponse"))


def test_a_hostile_document_is_refused_by_the_xml_hardening() -> None:
    """Proof the reader goes through `safe_xml` rather than round its side."""
    with pytest.raises(EspdParseError, match="could not be read"):
        parse_espd_request(BILLION_LAUGHS)


def test_bytes_that_are_not_xml_are_refused() -> None:
    with pytest.raises(EspdParseError, match="could not be read"):
        parse_espd_request(b"%PDF-1.7 this is a pdf")


def test_the_language_is_read_from_ubls_language_id_when_a_buyer_sets_one() -> None:
    """Some buyers do declare it, and `Requirement.source_lang` has to be right."""
    # Act
    request = parse_espd_request(espd_request_xml(criterion(), language="FR"))

    # Assert
    assert request.language == "fr"


def test_a_language_tag_that_is_not_one_is_ignored_rather_than_repaired() -> None:
    """A wrong tag would label a French quote as something else for the rest of the run."""
    # Act
    request = parse_espd_request(espd_request_xml(criterion(), language="Francais"))

    # Assert
    assert request.language is None


def test_a_criterion_element_with_no_id_child_is_dropped() -> None:
    """Written out by hand: the shared builder cannot produce a criterion missing a field."""
    # Arrange
    data = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b"<espd-req:ESPDRequest "
        b'xmlns:espd-req="urn:grow:names:specification:ubl:schema:xsd:ESPDRequest-1" '
        b'xmlns:ccv="urn:isa:names:specification:ubl:schema:xsd:'
        b'CCV-CommonAggregateComponents-1" '
        b'xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">'
        b"<ccv:Criterion><cbc:Name>Sans identifiant</cbc:Name></ccv:Criterion>"
        b"</espd-req:ESPDRequest>"
    )

    # Act
    request = parse_espd_request(data)

    # Assert
    assert request.criteria == ()
    assert request.dropped_criterion_count == 1


def test_an_empty_description_element_reads_as_empty_text() -> None:
    """`<cbc:Description/>` has `text is None`, which is not the same as "no such child"."""
    # Act
    request = parse_espd_request(espd_request_xml(criterion(description="")))

    # Assert
    assert request.criteria[0].description == ""
    assert request.criteria[0].name.startswith("Chiffre")
