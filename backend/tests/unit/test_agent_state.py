"""S3.2.1 — the graph state extraction reads and writes.

Two things are worth testing about a `TypedDict` used as LangGraph state, and neither is the
annotation. The first is that the **reducer is wired**: `Annotated[list[X], operator.add]`
looks like documentation, but LangGraph reads that metadata to decide whether a second
contributor to the channel appends or overwrites, and getting it wrong silently discards one
node's work. So the reducers are asserted by compiling a real two-node graph and looking at
what survives. The second is that a node's partial update names channels the state actually
has: LangGraph drops an unknown key without complaining, so a typo in a return value is a
node that appears to run and writes nothing.

Everything here is offline and hand-built. There is no model and no document.
"""

from __future__ import annotations

import asyncio
import operator
import typing
from typing import Annotated, get_args, get_origin

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from crossbid.agent.state import (
    DEFAULT_BIDDER_LANGUAGE,
    BidState,
    DocumentSection,
    ExtractionProblem,
    ExtractionProblemReason,
    ExtractionUpdate,
    TenderDocument,
    bidder_language_of,
    sections_of,
)
from crossbid.ingestion.parser import ParsedDocument, ParsedPage
from crossbid.models.requirement import (
    Checkability,
    Requirement,
    RequirementCategory,
    RequirementKind,
    RequirementStage,
)

GERMAN_CLAUSE = "Der Umsatz muss mindestens 3.000.000,00 EUR pro Jahr betragen."


def page(number: int, text: str = "text") -> ParsedPage:
    return ParsedPage(page_number=number, text=text)


def parsed(*texts: str, document_id: str = "doc-1") -> ParsedDocument:
    """A document whose page N holds `texts[N - 1]`. An empty string is an unread page."""
    return ParsedDocument(
        document_id=document_id,
        parser_name="hand-built",
        pages=tuple(page(index, text) for index, text in enumerate(texts, start=1)),
    )


def tender_document(*texts: str, name: str = "Bewerbungsbedingungen.pdf") -> TenderDocument:
    return TenderDocument(parsed=parsed(*texts), name=name, language="de")


def requirement(identifier: str, *, page_number: int = 1) -> Requirement:
    return Requirement(
        id=identifier,
        bid_id="bid-1",
        category=RequirementCategory.ECONOMIC_FINANCIAL,
        kind=RequirementKind.MANDATORY,
        stage=RequirementStage.BID_ELIGIBILITY,
        checkable=Checkability.COMPANY_PROPERTY,
        source_text=GERMAN_CLAUSE,
        source_lang="de",
        document_name="Bewerbungsbedingungen.pdf",
        page=page_number,
    )


def problem(reason: ExtractionProblemReason) -> ExtractionProblem:
    return ExtractionProblem(
        reason=reason, document_name="Bewerbungsbedingungen.pdf", pages=(1, 2)
    )


# ------------------------------------------------------------------- the state channels


def test_a_second_contributor_appends_to_the_requirement_channel() -> None:
    """`operator.add`, asserted through LangGraph rather than through the annotation.

    S3.2.2 puts the notice's own stated criteria into `requirements` before this node runs,
    so the channel has two writers and neither may overwrite the other.
    """

    # Arrange
    async def notice_node(state: BidState, config: RunnableConfig) -> ExtractionUpdate:
        return {"requirements": [requirement("from-notice")]}

    async def extract_node(state: BidState, config: RunnableConfig) -> ExtractionUpdate:
        return {
            "requirements": [requirement("from-documents")],
            "extraction_problems": [problem(ExtractionProblemReason.NO_VERBATIM_QUOTE)],
        }

    builder: StateGraph = StateGraph(BidState)
    builder.add_node("notice", notice_node)
    builder.add_node("extract", extract_node)
    builder.add_edge(START, "notice")
    builder.add_edge("notice", "extract")
    builder.add_edge("extract", END)

    # Act
    final = asyncio.run(builder.compile().ainvoke({"bid_id": "bid-1", "documents": []}))

    # Assert
    assert [row.id for row in final["requirements"]] == ["from-notice", "from-documents"]
    assert len(final["extraction_problems"]) == 1


def test_the_problem_channel_starts_empty_and_accumulates() -> None:
    """A run with nothing to report must still leave a readable channel, not a `KeyError`."""

    # Arrange
    async def silent_node(state: BidState, config: RunnableConfig) -> ExtractionUpdate:
        return {"requirements": []}

    builder: StateGraph = StateGraph(BidState)
    builder.add_node("silent", silent_node)
    builder.add_edge(START, "silent")
    builder.add_edge("silent", END)

    # Act
    final = asyncio.run(builder.compile().ainvoke({"bid_id": "bid-1", "documents": []}))

    # Assert
    assert final["requirements"] == []
    assert final["extraction_problems"] == []


@pytest.mark.parametrize("channel", ["requirements", "extraction_problems"])
def test_accumulating_channels_carry_an_add_reducer(channel: str) -> None:
    """The annotation itself, so a refactor cannot drop the reducer and keep the type."""
    # Act
    annotation = typing.get_type_hints(BidState, include_extras=True)[channel]

    # Assert
    assert get_origin(annotation) is Annotated
    assert operator.add in get_args(annotation)


def test_an_extraction_update_only_names_channels_the_state_has() -> None:
    """LangGraph discards an unknown key in a partial update without raising."""
    # Act
    update_keys = set(typing.get_type_hints(ExtractionUpdate).keys())
    state_keys = set(typing.get_type_hints(BidState).keys())

    # Assert
    assert update_keys, "the update must name at least one channel"
    assert update_keys <= state_keys, update_keys - state_keys


def test_the_state_documents_where_the_later_stories_extend_it() -> None:
    """The docstring is the only place the reader learns what is deliberately absent."""
    # Assert
    assert BidState.__doc__ is not None
    assert "S3.1.1" in BidState.__doc__
    assert "S3.3.1" in BidState.__doc__
    assert "F3.4" in BidState.__doc__


# --------------------------------------------------------------------- tender documents


def test_a_tender_document_carries_the_name_and_language_a_citation_needs() -> None:
    """`ParsedDocument` has neither: its id is the caller's, and it knows no language."""
    # Act
    document = tender_document("Seite eins")

    # Assert
    assert document.name == "Bewerbungsbedingungen.pdf"
    assert document.language == "de"
    assert document.parsed.page_count == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [("name", ""), ("name", "   "), ("language", "d"), ("language", "deutsch")],
)
def test_a_tender_document_refuses_metadata_a_requirement_could_not_hold(
    field: str, value: str
) -> None:
    """`Requirement.source_lang` is 2-5 characters and its `document_name` is a citation:
    a document that cannot fill them in would fail one row at a time, deep in extraction."""
    # Arrange
    fields = {"parsed": parsed("Seite eins"), "name": "ok.pdf", "language": "de", field: value}

    # Act / Assert
    with pytest.raises(ValidationError):
        TenderDocument(**fields)


def test_a_documents_metadata_is_stripped_so_a_citation_never_carries_whitespace() -> None:
    """`Requirement.source_lang` is documented as BCP 47, and " de" is not a language tag."""
    # Act
    document = TenderDocument(parsed=parsed("Seite eins"), name="  ok.pdf  ", language=" de ")

    # Assert
    assert document.name == "ok.pdf"
    assert document.language == "de"


def test_a_tender_document_is_frozen() -> None:
    # Arrange
    document = tender_document("Seite eins")

    # Act / Assert
    with pytest.raises(ValidationError):
        document.name = "other.pdf"  # type: ignore[misc]


# --------------------------------------------------------------------------- sectioning


def test_sections_group_readable_pages_into_runs_of_the_requested_size() -> None:
    # Arrange
    document = tender_document(*[f"Seite {number}" for number in range(1, 8)])

    # Act
    sections = sections_of(document, section_pages=3)

    # Assert
    assert [section.page_numbers for section in sections] == [(1, 2, 3), (4, 5, 6), (7,)]


def test_sections_skip_pages_with_no_text_layer_without_emitting_an_empty_section() -> None:
    """A page with no text layer is listed by the parser and contributes nothing here.

    CLAUDE.md records the trap: `pymupdf4llm` returns `"\\n\\n\\n\\n"` for an image-only
    page, so an emptiness test written as `text != ""` would section whitespace and send it
    to the model. `has_extractable_text` is the one definition of "not read".
    """
    # Arrange — pages 2 and 3 have no text layer, page 4 has whitespace only
    document = tender_document("Seite eins", "", "\n\n\n\n", "   \t ", "Seite fuenf")

    # Act
    sections = sections_of(document, section_pages=2)

    # Assert
    assert [section.page_numbers for section in sections] == [(1, 5)]
    assert all(page.has_text for section in sections for page in section.pages)


def test_a_document_that_could_not_be_read_at_all_yields_no_sections() -> None:
    # Arrange
    document = tender_document("", "\n\n\n\n")

    # Act / Assert
    assert sections_of(document, section_pages=6) == ()


def test_a_section_names_the_document_and_language_of_its_rows() -> None:
    # Arrange
    document = tender_document("Seite eins", "Seite zwei", name="Kriterienkatalog.pdf")

    # Act
    section = sections_of(document, section_pages=6)[0]

    # Assert
    assert section.document_name == "Kriterienkatalog.pdf"
    assert section.source_lang == "de"
    assert section.label == "Kriterienkatalog.pdf p.1-2"
    assert section.text_of(1) == "Seite eins"


def test_a_single_page_section_labels_one_page_rather_than_a_range() -> None:
    # Arrange
    document = tender_document("Seite eins", name="Anlage.pdf")

    # Act
    section = sections_of(document, section_pages=6)[0]

    # Assert
    assert section.label == "Anlage.pdf p.1"


def test_the_text_of_a_page_outside_the_section_is_not_available() -> None:
    """A row citing a page the section never held cannot be checked against its source."""
    # Arrange
    section = sections_of(tender_document("Seite eins"), section_pages=6)[0]

    # Act / Assert
    assert section.text_of(2) is None


@pytest.mark.parametrize("section_pages", [0, -1])
def test_sectioning_refuses_a_non_positive_section_size(section_pages: int) -> None:
    # Act / Assert
    with pytest.raises(ValueError, match="section_pages"):
        sections_of(tender_document("Seite eins"), section_pages=section_pages)


def test_a_section_refuses_to_hold_no_pages() -> None:
    """Every reader below the section — label, citation, wrapper — relies on there being one."""
    # Act / Assert
    with pytest.raises(ValueError, match="at least one page"):
        DocumentSection(document_name="x.pdf", source_lang="de", pages=())


def test_a_section_is_frozen() -> None:
    # Arrange
    section = sections_of(tender_document("Seite eins"), section_pages=6)[0]

    # Act / Assert
    with pytest.raises(AttributeError):
        section.pages = ()  # type: ignore[misc]


def test_a_hand_built_section_is_available_without_a_document() -> None:
    """The payload type is constructible on its own, which is what a node test needs."""
    # Act
    section = DocumentSection(
        document_name="x.pdf", source_lang="fr", pages=(page(4, "quatre"),)
    )

    # Assert
    assert section.page_numbers == (4,)
    assert section.text_of(4) == "quatre"


# ----------------------------------------------------------------------- bidder language


def test_the_bidder_language_defaults_to_german() -> None:
    """The wedge is a German-speaking bidder reading a French tender (CLAUDE.md)."""
    # Act / Assert
    assert bidder_language_of({"bid_id": "bid-1", "documents": []}) == "de"
    assert DEFAULT_BIDDER_LANGUAGE == "de"


@pytest.mark.parametrize("value", ["fr", " fr ", ""])
def test_the_bidder_language_is_read_from_the_state_when_it_is_set(value: str) -> None:
    # Arrange
    state: BidState = {"bid_id": "bid-1", "documents": [], "bidder_language": value}

    # Act
    language = bidder_language_of(state)

    # Assert
    assert language == (value.strip() or DEFAULT_BIDDER_LANGUAGE)


# --------------------------------------------------------------------------- problems


def test_a_problem_reports_where_it_happened_without_quoting_the_document() -> None:
    """Untrusted input must not escape through a message (ADR-0008), and a dropped row's
    quote is model output derived from an untrusted document."""
    # Act
    reported = problem(ExtractionProblemReason.INVALID_CRITERION_ID)

    # Assert
    assert reported.reason is ExtractionProblemReason.INVALID_CRITERION_ID
    assert reported.pages == (1, 2)
    assert reported.fields == ()
    assert GERMAN_CLAUSE not in reported.model_dump_json()


def test_a_problem_is_frozen() -> None:
    # Arrange
    reported = problem(ExtractionProblemReason.MODEL_ERROR)

    # Act / Assert
    with pytest.raises(ValidationError):
        reported.pages = ()  # type: ignore[misc]
