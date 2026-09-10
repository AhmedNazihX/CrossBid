"""S2.1.1 — the default `Parser`, on pymupdf4llm.

pymupdf4llm is preferred over bare `page.get_text()` because it renders headings, lists and
tables as markdown, and a tender's requirements live in exactly those structures — SP.1's
sections were markdown for the same reason (ADR-0003). It is called with
`page_chunks=True`, which returns one entry per page and so keeps the page boundaries the
citation depends on.

Two defences against losing a page, neither of which real fixture data can exercise
(ADR-0003 measured zero text-free pages across all 365 fixture pages, and ADR-0007's
lesson is that well-behaved data hides exactly this class of bug):

- if the markdown for a page comes back blank, the page's raw text layer is used instead —
  losing a page's formatting is acceptable, losing the page is not;
- if the backend returns a different number of entries than the document has pages, that
  is a `ParserError`, not a silent zip that shifts every citation by one.

Docling (S2.1.2, Could, not built) slots in beside this module behind the same protocol.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pymupdf
import pymupdf4llm

from crossbid.ingestion.parser import (
    DocumentSource,
    ParsedDocument,
    ParsedPage,
    ParserError,
    has_extractable_text,
)

PARSER_NAME = "pymupdf"
PDF_FILETYPE = "pdf"


class PyMuPDFParser:
    """Reads a PDF into one `ParsedPage` per page. Holds no state; safe to share."""

    name = PARSER_NAME

    def parse(self, source: DocumentSource, *, document_id: str) -> ParsedDocument:
        with _open(source, document_id) as document:
            pages = self._pages(document, document_id)
        return ParsedDocument(document_id=document_id, parser_name=self.name, pages=pages)

    def _pages(self, document: pymupdf.Document, document_id: str) -> tuple[ParsedPage, ...]:
        if document.page_count == 0:
            # Nothing to ask the backend, and pymupdf4llm raises IndexError if asked.
            return ()
        markdown = self._markdown_per_page(document)
        _require_one_entry_per_page(len(markdown), document.page_count, document_id)
        return tuple(
            ParsedPage(page_number=index + 1, text=_page_text(document[index], markdown[index]))
            for index in range(document.page_count)
        )

    @staticmethod
    def _markdown_per_page(document: pymupdf.Document) -> list[str]:
        """The only call into pymupdf4llm, kept alone so tests can stand in for it.

        pymupdf4llm ships no type information and its return type varies with the
        arguments; `page_chunks=True` is documented to give one dict per page.
        """
        chunks = cast(
            list[dict[str, Any]],
            pymupdf4llm.to_markdown(document, page_chunks=True, show_progress=False),
        )
        return [str(chunk["text"]) for chunk in chunks]


def _open(source: DocumentSource, document_id: str) -> pymupdf.Document:
    """Open a path or an upload's bytes, or fail with a `ParserError` naming the document."""
    try:
        if isinstance(source, Path):
            return pymupdf.open(source)
        return pymupdf.open(stream=source, filetype=PDF_FILETYPE)
    except Exception as error:
        # pymupdf raises FileNotFoundError, pymupdf.FileDataError, ValueError and
        # RuntimeError for different flavours of "unreadable"; callers want one type.
        raise ParserError(f"{document_id}: could not be opened as a PDF ({error})") from error


def _require_one_entry_per_page(entries: int, page_count: int, document_id: str) -> None:
    if entries != page_count:
        raise ParserError(
            f"{document_id}: parser returned {entries} page entries "
            f"for a {page_count}-page document"
        )


def _page_text(page: pymupdf.Page, markdown: str) -> str:
    """Markdown if it has content, the raw text layer if not, `""` if neither has.

    Returning `""` rather than the blank markdown makes the unread page unambiguous in the
    serialised document; `ParsedDocument.unread_pages` then lists this page.
    """
    if has_extractable_text(markdown):
        return markdown.strip()
    raw = cast(str, page.get_text())  # `str` for the default "text" option
    return raw.strip() if has_extractable_text(raw) else ""
