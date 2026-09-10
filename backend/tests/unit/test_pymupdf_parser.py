"""S2.1.1 — the default parser, against real tender PDFs and two hand-built ones.

The real fixtures answer "does it read a tender pack faithfully"; ADR-0003 already measured
that all 191 DE pages have a text layer, so they cannot answer "what happens to a page that
has none". `tests/fixtures/ingestion/` exists for exactly that: two PDFs built with pymupdf
whose pages carry a rectangle and a raster image and not one glyph of text.

The monkeypatched tests cover the two ways this parser can be wrong in a way real data will
never show — a markdown conversion that silently returns nothing for a page that does have
text, and a backend that returns a different number of pages than the document has. Both
would misattribute or lose a page, which is the one thing S2.1.1 forbids.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pymupdf
import pytest

from crossbid.ingestion.parser import ParsedDocument, Parser, ParserError
from crossbid.ingestion.pymupdf_parser import PyMuPDFParser

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
INGESTION = FIXTURES / "ingestion"

# 50 pages, so it answers the story's "given a 40-page PDF" criterion; EN rather than DE
# only because no single document in the DE pack reaches 40 pages (the pack is 191 across
# 28 files). Parsed once per module: pymupdf4llm takes ~4s on it.
FORTY_PLUS_PAGE_PDF = FIXTURES / "tenders" / "en" / "documents" / "Tender_Specifications_V1.pdf"
GERMAN_PDF = FIXTURES / "tenders" / "de" / "documents" / "Kriterienkatalog_Eignung_VV2_V1.pdf"
IMAGE_ONLY_PDF = INGESTION / "image_only_page.pdf"
TEXT_IMAGE_TEXT_PDF = INGESTION / "text_image_text.pdf"


@pytest.fixture(scope="module")
def parser() -> PyMuPDFParser:
    return PyMuPDFParser()


@pytest.fixture(scope="module")
def long_document(parser: PyMuPDFParser) -> ParsedDocument:
    return parser.parse(FORTY_PLUS_PAGE_PDF, document_id="en-tender-specs")


@pytest.fixture
def text_pdf(tmp_path: Path) -> Iterator[Path]:
    """A two-page PDF with text on both pages, written fresh so no test shares it."""
    path = tmp_path / "two_text_pages.pdf"
    document = pymupdf.open()
    for number in (1, 2):
        page = document.new_page()
        page.insert_text((72, 72), f"Page {number} of the fixture", fontsize=12)
    document.save(path)
    document.close()
    yield path


# ------------------------------------------------------------------------ the happy path


def test_the_default_parser_satisfies_the_protocol(parser: PyMuPDFParser) -> None:
    # Act / Assert
    assert isinstance(parser, Parser)
    assert parser.name == "pymupdf"


def test_a_forty_page_pdf_yields_one_entry_per_page(long_document: ParsedDocument) -> None:
    """First S2.1.1 criterion: every page is present and numbered as a viewer shows it."""
    # Assert
    assert long_document.page_count == 50
    assert [page.page_number for page in long_document.pages] == list(range(1, 51))
    assert long_document.unread_pages == ()
    assert all(page.has_text for page in long_document.pages)


def test_the_document_records_its_id_and_parser(long_document: ParsedDocument) -> None:
    """Chunks cite `document_id`; `parser_name` is what S2.1.2's comparison hangs on."""
    # Assert
    assert long_document.document_id == "en-tender-specs"
    assert long_document.parser_name == "pymupdf"


def test_page_text_is_the_text_of_that_page_and_not_the_whole_document(
    long_document: ParsedDocument,
) -> None:
    """The point of page fidelity: page 1's text must not contain page 2's."""
    # Arrange
    first, second = long_document.pages[0].text, long_document.pages[1].text

    # Assert
    assert first and second
    assert second not in first
    assert len(first) < 10_000  # a single page, not a concatenation of fifty


def test_german_text_survives_parsing(parser: PyMuPDFParser) -> None:
    """Requirements are quoted verbatim in the source language, umlauts included."""
    # Act
    document = parser.parse(GERMAN_PDF, document_id="de-kriterienkatalog")

    # Assert
    assert document.page_count == 3
    assert document.unread_pages == ()
    assert "Kriterienkatalog" in document.pages[0].text
    assert "Eignung" in document.pages[0].text
    assert any("ü" in page.text or "ä" in page.text for page in document.pages)


def test_leading_whitespace_from_the_markdown_conversion_is_trimmed(
    parser: PyMuPDFParser,
) -> None:
    """pymupdf4llm prefixes every page with blank lines; they are not content."""
    # Act
    document = parser.parse(GERMAN_PDF, document_id="de-kriterienkatalog")

    # Assert
    assert document.pages[0].text == document.pages[0].text.strip()


def test_parsing_bytes_and_parsing_a_path_agree(parser: PyMuPDFParser) -> None:
    """Uploads arrive as bytes (S2.2.3); no temp file should be needed."""
    # Act
    from_path = parser.parse(GERMAN_PDF, document_id="de-kriterienkatalog")
    from_bytes = parser.parse(GERMAN_PDF.read_bytes(), document_id="de-kriterienkatalog")

    # Assert
    assert from_bytes == from_path


# -------------------------------------------------------------------- pages with no text


def test_an_image_only_page_is_listed_as_unread_not_dropped(parser: PyMuPDFParser) -> None:
    """Second S2.1.1 criterion. OCR was cut, so "not read" is the terminal state."""
    # Act
    document = parser.parse(IMAGE_ONLY_PDF, document_id="image-only")

    # Assert
    assert document.page_count == 1
    assert document.unread_pages == (1,)
    assert document.pages[0].page_number == 1
    assert document.pages[0].text == ""
    assert document.readable_pages == ()


def test_parsing_continues_past_an_unreadable_page_in_the_middle(
    parser: PyMuPDFParser,
) -> None:
    # Act
    document = parser.parse(TEXT_IMAGE_TEXT_PDF, document_id="text-image-text")

    # Assert
    assert document.page_count == 3
    assert document.unread_pages == (2,)
    assert "Seite 1" in document.pages[0].text
    assert "Seite 3" in document.pages[2].text


# ------------------------------------------------------- what real data never exercises


def test_a_page_the_markdown_conversion_blanks_falls_back_to_its_raw_text(
    parser: PyMuPDFParser, text_pdf: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Losing a page's formatting is acceptable; losing the page is not."""
    # Arrange
    monkeypatch.setattr(
        PyMuPDFParser, "_markdown_per_page", staticmethod(lambda document: ["", ""])
    )

    # Act
    document = parser.parse(text_pdf, document_id="two-text-pages")

    # Assert
    assert document.unread_pages == ()
    assert document.pages[0].text == "Page 1 of the fixture"
    assert document.pages[1].text == "Page 2 of the fixture"


def test_a_page_blank_in_both_layers_is_unread(
    parser: PyMuPDFParser, text_pdf: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange: markdown blank, and no raw text layer either
    monkeypatch.setattr(
        PyMuPDFParser, "_markdown_per_page", staticmethod(lambda document: ["", "  "])
    )
    monkeypatch.setattr(pymupdf.Page, "get_text", lambda self, *args, **kwargs: "\n")

    # Act
    document = parser.parse(text_pdf, document_id="two-text-pages")

    # Assert
    assert document.unread_pages == (1, 2)


def test_a_backend_returning_the_wrong_number_of_pages_is_an_error(
    parser: PyMuPDFParser, text_pdf: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Silently zipping 1 markdown page onto 2 PDF pages would misattribute a citation."""
    # Arrange
    monkeypatch.setattr(
        PyMuPDFParser, "_markdown_per_page", staticmethod(lambda document: ["only one"])
    )

    # Act / Assert
    with pytest.raises(ParserError, match="1 page"):
        parser.parse(text_pdf, document_id="two-text-pages")


# ------------------------------------------------------------------------------- failure


def test_bytes_that_are_not_a_pdf_raise_parser_error(parser: PyMuPDFParser) -> None:
    """The caller catches `ParserError`, never a pymupdf exception type."""
    # Act / Assert
    with pytest.raises(ParserError, match="upload-7"):
        parser.parse(b"this is not a pdf", document_id="upload-7")


def test_a_missing_file_raises_parser_error(parser: PyMuPDFParser, tmp_path: Path) -> None:
    # Act / Assert
    with pytest.raises(ParserError, match="absent"):
        parser.parse(tmp_path / "nope.pdf", document_id="absent")


def test_a_pdf_with_no_pages_parses_to_nothing_rather_than_raising(
    parser: PyMuPDFParser,
) -> None:
    """Hand-assembled because pymupdf refuses to *save* a zero-page document."""
    # Arrange
    empty_pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\n"
        b"trailer<</Root 1 0 R>>\n"
    )

    # Act
    parsed = parser.parse(empty_pdf, document_id="empty")

    # Assert
    assert parsed.page_count == 0
    assert parsed.unread_pages == ()
    assert parsed.readable_pages == ()
