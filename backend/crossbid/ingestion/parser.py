"""S2.1.1 — the parsing contract: one entry per page, and no page ever dropped.

Every cell of the requirements matrix has to point at a page the reviewer can open, so a
parser's job is not "give me the text of this PDF" but "give me the text of page N, for
every N". That is why `ParsedDocument` is a complete run of pages rather than a string, and
why a page whose text could not be extracted is *listed* rather than skipped.

Two properties are enforced here so that no implementation can get them wrong:

- `pages` must be numbered 1..N in order. A gap or a duplicate is a construction error,
  because it would mean a page went missing without anyone noticing.
- `unread_pages` is derived from the pages, not supplied. OCR is out of scope, so "not
  read" is the honest terminal state for an image-only page; making it a computed view of
  `pages` means the list and the pages can never disagree.

`Parser` is a `typing.Protocol` rather than an abstract base class. S2.1.2 (Could) adds a
Docling implementation, and structural typing means it needs no import from here, no base
class and no registry: a class with a `name` and a matching `parse` *is* a `Parser`. The
signature is deliberately free of backend types — `Path | bytes` in, `ParsedDocument` out,
`ParserError` on failure — so Docling's converter and pymupdf's document object both fit
behind it and callers never catch a library-specific exception.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Protocol, Self, runtime_checkable

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    computed_field,
    model_validator,
)

NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]

DocumentSource = Path | bytes
"""A file on disk (fixtures, seeds) or the raw bytes of an upload (S2.2.3)."""


class ParserError(Exception):
    """A document could not be read. Raised in place of any backend-specific exception."""


def has_extractable_text(text: str) -> bool:
    """Whether a page yielded text at all.

    Anything with no non-whitespace character counts as unread. `str.strip()` covers the
    non-breaking spaces and thin spaces that PDF producers sprinkle into otherwise empty
    pages, which a `!= ""` check would take for content.
    """
    return bool(text.strip())


class ParsedPage(BaseModel):
    """One page, exactly as the parser read it."""

    model_config = ConfigDict(frozen=True)

    page_number: int = Field(ge=1, description="1-based, the number a PDF viewer shows")
    text: str = Field(description="Extracted text; empty when the page could not be read")

    @property
    def has_text(self) -> bool:
        return has_extractable_text(self.text)


class ParsedDocument(BaseModel):
    """A document as a complete, ordered run of pages.

    `unread_pages` and `page_count` are computed, so they are part of the serialised shape
    the frontend sees but cannot be set by a caller.
    """

    model_config = ConfigDict(frozen=True)

    document_id: NonEmptyStr = Field(description="Caller's id; carried onto every chunk")
    parser_name: NonEmptyStr = Field(description="Which implementation produced this")
    pages: tuple[ParsedPage, ...] = Field(description="Page 1..N, in order, none omitted")

    @model_validator(mode="after")
    def _pages_are_the_complete_run(self) -> Self:
        expected = list(range(1, len(self.pages) + 1))
        actual = [page.page_number for page in self.pages]
        if actual != expected:
            raise ValueError(
                f"pages must be numbered 1..{len(self.pages)} in order, got {actual}"
            )
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def unread_pages(self) -> tuple[int, ...]:
        """Pages with no extractable text. Never dropped, only listed."""
        return tuple(page.page_number for page in self.pages if not page.has_text)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def readable_pages(self) -> tuple[ParsedPage, ...]:
        """The pages worth chunking, in page order."""
        return tuple(page for page in self.pages if page.has_text)


@runtime_checkable
class Parser(Protocol):
    """What ingestion needs from a document reader; see the module docstring."""

    @property
    def name(self) -> str:
        """Short identifier recorded on every `ParsedDocument` this parser produces."""
        ...

    def parse(self, source: DocumentSource, *, document_id: str) -> ParsedDocument:
        """Read `source` page by page. Raises `ParserError` if it cannot be opened."""
        ...
