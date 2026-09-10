"""S2.1.1 — the parser contract, independent of any PDF library.

Two things are asserted here and nowhere else.

First, `ParsedDocument` cannot be built in a shape that loses a page: page numbers must be
the complete run 1..N, in order. A gap or a duplicate is exactly the silent drop the story
forbids, so it is a construction error rather than something a caller has to notice.

Second, `unread_pages` is *derived* from the pages, never supplied. Two implementations of
the protocol (pymupdf today, Docling in S2.1.2) therefore cannot disagree about which pages
were readable, because neither of them gets to say.

The fake parser at the bottom stands in for that second implementation: it satisfies
`Parser` without importing pymupdf, without subclassing anything, and without being
registered anywhere.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from crossbid.ingestion.parser import (
    DocumentSource,
    ParsedDocument,
    ParsedPage,
    Parser,
    ParserError,
    has_extractable_text,
)

# A page that carries only these characters is "not read": OCR was cut from scope, so an
# image-only page has no honest terminal state other than "we could not read it".
BLANK_TEXTS = ("", " ", "\n\n", "\t", "\u00a0", " \n \t\u2009")


def _document(*texts: str, document_id: str = "doc-1") -> ParsedDocument:
    """A parsed document whose page N holds `texts[N - 1]`."""
    return ParsedDocument(
        document_id=document_id,
        parser_name="fake",
        pages=tuple(
            ParsedPage(page_number=number, text=text)
            for number, text in enumerate(texts, start=1)
        ),
    )


# ------------------------------------------------------------------ has_extractable_text


@pytest.mark.parametrize("text", BLANK_TEXTS)
def test_whitespace_only_text_is_not_extractable(text: str) -> None:
    # Act / Assert
    assert has_extractable_text(text) is False


@pytest.mark.parametrize("text", ["a", "0", " x ", "**Kriterienkatalog Eignung**"])
def test_any_non_whitespace_character_counts_as_extractable(text: str) -> None:
    # Act / Assert
    assert has_extractable_text(text) is True


# --------------------------------------------------------------------------- ParsedPage


def test_page_reports_whether_it_has_text() -> None:
    # Arrange / Act
    readable = ParsedPage(page_number=1, text="Seite 1")
    unreadable = ParsedPage(page_number=2, text="\n\n")

    # Assert
    assert readable.has_text is True
    assert unreadable.has_text is False


def test_page_numbers_are_one_based() -> None:
    # Act / Assert
    with pytest.raises(ValidationError):
        ParsedPage(page_number=0, text="text")


def test_page_is_immutable() -> None:
    # Arrange
    page = ParsedPage(page_number=1, text="text")

    # Act / Assert
    with pytest.raises(ValidationError):
        page.text = "something else"  # type: ignore[misc]


# ----------------------------------------------------------------------- ParsedDocument


def test_document_has_one_entry_per_page() -> None:
    """The first S2.1.1 criterion, at model level: no page is missing from `pages`."""
    # Act
    document = _document("one", "two", "three")

    # Assert
    assert document.page_count == 3
    assert [page.page_number for page in document.pages] == [1, 2, 3]


def test_unread_pages_lists_pages_without_text_and_keeps_them_in_pages() -> None:
    """The second S2.1.1 criterion: listed as "not read", not silently dropped."""
    # Act
    document = _document("Seite 1", "\n\n", "Seite 3")

    # Assert
    assert document.unread_pages == (2,)
    assert document.page_count == 3
    assert document.pages[1].text == "\n\n"


def test_unread_pages_is_empty_for_a_fully_readable_document() -> None:
    # Act / Assert
    assert _document("a", "b").unread_pages == ()


def test_every_page_can_be_unread() -> None:
    # Act
    document = _document("", "\u00a0")

    # Assert
    assert document.unread_pages == (1, 2)
    assert document.readable_pages == ()


def test_readable_pages_skips_the_unread_ones_in_page_order() -> None:
    # Act
    readable = _document("Seite 1", " ", "Seite 3").readable_pages

    # Assert
    assert [page.page_number for page in readable] == [1, 3]


def test_unread_pages_cannot_be_supplied_by_the_parser() -> None:
    """Derived, so two implementations of the protocol cannot disagree about it."""
    # Act
    document = ParsedDocument(
        document_id="doc-1",
        parser_name="fake",
        pages=(ParsedPage(page_number=1, text=""),),
        unread_pages=(),  # type: ignore[call-arg]
    )

    # Assert
    assert document.unread_pages == (1,)


def test_a_gap_in_the_page_numbers_is_rejected() -> None:
    """A missing number would mean a dropped page, which is the bug S2.1.1 exists to stop."""
    # Arrange
    pages = (ParsedPage(page_number=1, text="a"), ParsedPage(page_number=3, text="c"))

    # Act / Assert
    with pytest.raises(ValidationError, match=r"1\.\.2"):
        ParsedDocument(document_id="doc-1", parser_name="fake", pages=pages)


def test_duplicate_page_numbers_are_rejected() -> None:
    # Arrange
    pages = (ParsedPage(page_number=1, text="a"), ParsedPage(page_number=1, text="b"))

    # Act / Assert
    with pytest.raises(ValidationError, match=r"1\.\.2"):
        ParsedDocument(document_id="doc-1", parser_name="fake", pages=pages)


def test_pages_out_of_order_are_rejected() -> None:
    # Arrange
    pages = (ParsedPage(page_number=2, text="b"), ParsedPage(page_number=1, text="a"))

    # Act / Assert
    with pytest.raises(ValidationError, match=r"1\.\.2"):
        ParsedDocument(document_id="doc-1", parser_name="fake", pages=pages)


def test_a_document_with_no_pages_is_allowed() -> None:
    """A zero-page PDF is a real thing; it must not raise, it must yield nothing."""
    # Act
    document = _document()

    # Assert
    assert document.page_count == 0
    assert document.unread_pages == ()


def test_blank_document_id_is_rejected() -> None:
    # Act / Assert
    with pytest.raises(ValidationError):
        _document("a", document_id="")


def test_document_serialises_its_derived_fields() -> None:
    """`unread_pages` and `page_count` reach the API contract, so they must serialise."""
    # Act
    dumped = _document("Seite 1", "").model_dump()

    # Assert
    assert dumped["unread_pages"] == (2,)
    assert dumped["page_count"] == 2
    assert dumped["document_id"] == "doc-1"


# ------------------------------------------------------------------------------- Parser


class FakeParser:
    """Stands in for `docling_parser.DoclingParser` (S2.1.2, Could, not built).

    It satisfies `Parser` structurally: no base class, no import of the default parser, no
    registry entry. That is the whole reason the seam is a `typing.Protocol`.
    """

    name = "fake"

    def parse(self, source: DocumentSource, *, document_id: str) -> ParsedDocument:
        text = source.name if isinstance(source, Path) else source.decode("utf-8")
        return ParsedDocument(
            document_id=document_id,
            parser_name=self.name,
            pages=(ParsedPage(page_number=1, text=text),),
        )


def test_a_second_implementation_satisfies_the_protocol_without_inheriting() -> None:
    # Arrange
    parser: Parser = FakeParser()

    # Act
    document = parser.parse(b"Seite 1", document_id="doc-1")

    # Assert
    assert isinstance(parser, Parser)
    assert document.parser_name == "fake"
    assert document.pages[0].text == "Seite 1"


def test_the_protocol_accepts_both_a_path_and_bytes() -> None:
    """Uploads arrive as bytes (S2.2.3) and fixtures as paths; neither needs a temp file."""
    # Arrange
    parser: Parser = FakeParser()

    # Act
    from_path = parser.parse(Path("upload.pdf"), document_id="doc-1")
    from_bytes = parser.parse(b"upload.pdf", document_id="doc-1")

    # Assert
    assert from_path.pages[0].text == from_bytes.pages[0].text == "upload.pdf"


def test_parser_error_is_an_exception_carrying_a_message() -> None:
    """Backends raise their own error types; callers catch this one."""
    # Act / Assert
    with pytest.raises(ParserError, match=r"broken\.pdf"):
        raise ParserError("broken.pdf could not be opened")
