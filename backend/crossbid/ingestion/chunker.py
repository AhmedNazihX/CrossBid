"""S2.1.3 — a parsed document becomes ~800-token chunks that each name a page.

**Tokens, not characters.** The window is measured with `tiktoken`, and the encoding is
pinned to `cl100k_base` rather than resolved from a model name. Two reasons. First, the
chunk size exists to bound what gets embedded, and the embedding model is the only consumer
with a hard limit — `openai/text-embedding-3-small` (ADR-0004) has an 8191-token input and
tokenises with exactly `cl100k_base`, so counting this way makes the count *true* where
exceeding it is an API error. Second, the chat models are OpenRouter slugs
(`openai/gpt-5.6-terra`) and tiktoken cannot map them at all: `encoding_for_model` raises.
Against those models `cl100k_base` over-counts German — 21 tokens where `o200k_base` needs
17 — which is the safe direction for a prompt budget.

**Page attribution.** A chunk carries `pages`, every page its text came from, and `page`,
the *first* of them, which is the one a citation points at. First rather than
majority-share because the reviewer opens that page to start reading the retrieved passage
and reads forward; a majority page can sit past the beginning of the evidence. `pages` is
what a UI needs to render "p. 12-14", and it stays honest when the pages are not adjacent:
if only the middle page of three was unreadable, a chunk cites `(1, 3)`.

**Overlap.** Windows advance by `chunk_tokens - overlap_tokens`. The final window always
carries at least one token no earlier chunk had, so no chunk is a pure repeat of its
predecessor's tail; it may still be shorter than the target, which is the honest arithmetic
of a fixed window over a document that does not divide evenly.

Size and overlap are constructor parameters. They are not read from settings here: this
module has no dependencies inside `crossbid` beyond `parser`, and the caller that owns
configuration passes them in.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from functools import lru_cache
from itertools import groupby
from operator import itemgetter
from typing import Annotated, Protocol, Self

import tiktoken
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    computed_field,
    model_validator,
)

from crossbid.ingestion.parser import ParsedDocument

DEFAULT_CHUNK_TOKENS = 800
DEFAULT_OVERLAP_TOKENS = 100
MIN_CHUNK_TOKENS = 1

ENCODING_NAME = "cl100k_base"
"""The encoding of `openai/text-embedding-3-small`; see the module docstring."""

PAGE_SEPARATOR = "\n\n"
"""Written between two pages' text inside one chunk, so the chunk reads as prose."""

NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]


class TokenEncoder(Protocol):
    """The slice of `tiktoken.Encoding` the chunker uses.

    A protocol rather than the concrete type so that tests can supply a deterministic
    encoder and never reach the network for a BPE table.
    """

    def encode(self, text: str) -> list[int]: ...

    def decode(self, tokens: Sequence[int]) -> str: ...


@lru_cache(maxsize=1)
def default_token_encoder() -> TokenEncoder:
    """The production tokeniser, loaded once (the table costs a couple of seconds)."""
    return tiktoken.get_encoding(ENCODING_NAME)


class Chunk(BaseModel):
    """One embeddable passage, and the page a reviewer opens to read it."""

    model_config = ConfigDict(frozen=True)

    document_id: NonEmptyStr = Field(description="The `ParsedDocument` this came from")
    index: int = Field(ge=0, description="Position within the document, 0-based")
    pages: tuple[int, ...] = Field(min_length=1, description="Every page the text spans")
    text: str = Field(description="Page texts joined by a blank line")
    token_count: int = Field(ge=1, description="Tokens taken from the document")

    @model_validator(mode="after")
    def _pages_ascend(self) -> Self:
        if list(self.pages) != sorted(set(self.pages)):
            raise ValueError(f"pages must be ascending and distinct, got {self.pages}")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def page(self) -> int:
        """The citable page: where the chunk starts. Derived, so it cannot disagree."""
        return self.pages[0]


class Chunker:
    """Turns a `ParsedDocument` into page-tagged chunks. Holds no per-document state."""

    def __init__(
        self,
        *,
        chunk_tokens: int = DEFAULT_CHUNK_TOKENS,
        overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
        encoder: TokenEncoder | None = None,
    ) -> None:
        if chunk_tokens < MIN_CHUNK_TOKENS:
            raise ValueError(f"chunk_tokens must be at least {MIN_CHUNK_TOKENS}")
        if not 0 <= overlap_tokens < chunk_tokens:
            raise ValueError(
                f"overlap_tokens must be in [0, {chunk_tokens}), got {overlap_tokens}"
            )
        self._chunk_tokens = chunk_tokens
        self._overlap_tokens = overlap_tokens
        # Resolved on first use, not here: constructing a Chunker must not load a BPE table.
        self._encoder = encoder

    @property
    def chunk_tokens(self) -> int:
        return self._chunk_tokens

    @property
    def overlap_tokens(self) -> int:
        return self._overlap_tokens

    @property
    def encoder(self) -> TokenEncoder:
        return self._encoder if self._encoder is not None else default_token_encoder()

    def chunk(self, document: ParsedDocument) -> tuple[Chunk, ...]:
        """Chunks in document order. Unreadable pages contribute nothing."""
        encoder = self.encoder
        tokens, page_of_token = _token_stream(document, encoder)
        stride = self._chunk_tokens - self._overlap_tokens
        return tuple(
            _build_chunk(
                document_id=document.document_id,
                index=index,
                tokens=tokens[start:end],
                page_of_token=page_of_token[start:end],
                encoder=encoder,
            )
            for index, (start, end) in enumerate(
                _windows(len(tokens), self._chunk_tokens, stride)
            )
        )


def _token_stream(
    document: ParsedDocument, encoder: TokenEncoder
) -> tuple[list[int], list[int]]:
    """The document's readable pages as one token run, plus each token's page number."""
    per_page = [
        (page.page_number, encoder.encode(page.text)) for page in document.readable_pages
    ]
    tokens = [token for _, page_tokens in per_page for token in page_tokens]
    page_of_token = [number for number, page_tokens in per_page for _ in page_tokens]
    return tokens, page_of_token


def _windows(total: int, size: int, stride: int) -> Iterator[tuple[int, int]]:
    """Half-open `[start, end)` windows over `total` tokens.

    Stops as soon as a window reaches the end, so the tail is never a chunk made entirely
    of tokens the previous chunk already carried.
    """
    start = 0
    while start < total:
        end = min(start + size, total)
        yield start, end
        if end == total:
            return
        start += stride


def _build_chunk(
    *,
    document_id: str,
    index: int,
    tokens: list[int],
    page_of_token: list[int],
    encoder: TokenEncoder,
) -> Chunk:
    runs = _page_runs(tokens, page_of_token)
    return Chunk(
        document_id=document_id,
        index=index,
        pages=tuple(number for number, _ in runs),
        # Decoded run by run rather than in one call: each run is a slice of a single
        # page's own encoding, which is what keeps the text faithful to that page.
        text=PAGE_SEPARATOR.join(encoder.decode(run) for _, run in runs),
        token_count=len(tokens),
    )


def _page_runs(tokens: list[int], page_of_token: list[int]) -> list[tuple[int, list[int]]]:
    """The chunk's tokens grouped into consecutive same-page runs, in order."""
    tagged = zip(page_of_token, tokens, strict=True)
    return [
        (page_number, [token for _, token in group])
        for page_number, group in groupby(tagged, key=itemgetter(0))
    ]
