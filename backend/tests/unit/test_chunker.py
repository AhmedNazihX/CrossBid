"""S2.1.3 — chunk arithmetic, page attribution, and the tokeniser.

Almost every test here runs on `CharacterEncoder`, a one-token-per-character stand-in, so
the windowing can be reasoned about by eye: with `chunk_tokens=10` a chunk is ten letters.
The real tokeniser is exercised separately at the bottom — and only there, because
`tiktoken.get_encoding` fetches its BPE table over the network on first use and every test
in this suite has to pass offline.

The edge cases are deliberately constructed rather than taken from the fixtures. ADR-0007
recorded three merge and ordering bugs that survived a live rebuild of real eCertis data and
only appeared under hand-built input; a real tender pack has no empty page, no single-token
page and no 900-character word, so the chunker's boundary behaviour would be untested
against it.
"""

from __future__ import annotations

import string
from collections.abc import Iterator, Sequence
from itertools import pairwise
from pathlib import Path

import pytest
import tiktoken
from pydantic import ValidationError

from crossbid.ingestion.chunker import (
    DEFAULT_CHUNK_TOKENS,
    DEFAULT_OVERLAP_TOKENS,
    ENCODING_NAME,
    Chunk,
    Chunker,
    TokenEncoder,
    default_token_encoder,
)
from crossbid.ingestion.parser import ParsedDocument, ParsedPage
from crossbid.ingestion.pymupdf_parser import PyMuPDFParser

DE_PDF = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "tenders"
    / "de"
    / "documents"
    / "Leistungsbeschreibung_VV2_V1.pdf"
)
ALPHABET = string.ascii_lowercase  # 26 "tokens" under CharacterEncoder
GERMAN_SENTENCE = "Der Umsatz muss mindestens 3.000.000,00 EUR pro Jahr betragen"


class CharacterEncoder:
    """One token per character. Reversible, stateless, and countable by eye.

    It satisfies `TokenEncoder` structurally, which is also the point: the chunker never
    imports tiktoken directly, so it can be tested without touching the network.
    """

    def encode(self, text: str) -> list[int]:
        return [ord(character) for character in text]

    def decode(self, tokens: Sequence[int]) -> str:
        return "".join(chr(token) for token in tokens)


def _document(*texts: str, document_id: str = "doc-1") -> ParsedDocument:
    """A parsed document whose page N holds `texts[N - 1]`.

    Deliberately duplicated from `test_parser.py` rather than shared through `conftest.py`:
    the two modules are independent, and one shared builder is not worth coupling them.
    """
    return ParsedDocument(
        document_id=document_id,
        parser_name="test",
        pages=tuple(
            ParsedPage(page_number=number, text=text)
            for number, text in enumerate(texts, start=1)
        ),
    )


def _chunker(*, chunk_tokens: int, overlap_tokens: int) -> Chunker:
    return Chunker(
        chunk_tokens=chunk_tokens,
        overlap_tokens=overlap_tokens,
        encoder=CharacterEncoder(),
    )


def _real_encoder_or_skip() -> TokenEncoder:
    """The production tokeniser, or a skip if its table cannot be fetched offline."""
    try:
        return default_token_encoder()
    except Exception as error:  # pragma: no cover - only on a machine with no BPE cache
        pytest.skip(f"tiktoken BPE table unavailable offline: {error}")


@pytest.fixture(autouse=True)
def _reset_encoder_cache() -> Iterator[None]:
    """`default_token_encoder` is memoised, so a stubbed one must not leak between tests."""
    default_token_encoder.cache_clear()
    yield
    default_token_encoder.cache_clear()


# --------------------------------------------------------------------------- the defaults


def test_the_defaults_are_eight_hundred_tokens_with_one_hundred_overlap() -> None:
    """S2.1.3 states the numbers; they are constructor defaults, not settings lookups."""
    # Act
    chunker = Chunker()

    # Assert
    assert (DEFAULT_CHUNK_TOKENS, DEFAULT_OVERLAP_TOKENS) == (800, 100)
    assert chunker.chunk_tokens == 800
    assert chunker.overlap_tokens == 100


@pytest.mark.parametrize(
    ("chunk_tokens", "overlap_tokens"),
    [(10, 10), (10, 11), (0, 0), (-1, 0), (10, -1)],
)
def test_impossible_sizes_are_rejected_at_construction(
    chunk_tokens: int, overlap_tokens: int
) -> None:
    """An overlap at or above the size never advances: it would chunk forever."""
    # Act / Assert
    with pytest.raises(ValueError, match=r"overlap|chunk_tokens"):
        Chunker(chunk_tokens=chunk_tokens, overlap_tokens=overlap_tokens)


def test_an_overlap_of_zero_is_allowed() -> None:
    # Act / Assert
    assert Chunker(chunk_tokens=10, overlap_tokens=0).overlap_tokens == 0


# ------------------------------------------------------------------ windowing arithmetic


def test_a_document_shorter_than_one_chunk_yields_a_single_chunk() -> None:
    # Act
    chunks = _chunker(chunk_tokens=10, overlap_tokens=2).chunk(_document("abc"))

    # Assert
    assert len(chunks) == 1
    assert chunks[0].text == "abc"
    assert chunks[0].token_count == 3


def test_chunks_advance_by_size_minus_overlap_and_carry_their_position() -> None:
    # Act
    chunks = _chunker(chunk_tokens=10, overlap_tokens=2).chunk(_document(ALPHABET))

    # Assert
    assert [chunk.text for chunk in chunks] == [
        "abcdefghij",
        "ijklmnopqr",
        "qrstuvwxyz",
    ]
    assert [chunk.index for chunk in chunks] == [0, 1, 2]
    assert {chunk.document_id for chunk in chunks} == {"doc-1"}


def test_consecutive_chunks_share_exactly_the_overlap() -> None:
    # Arrange
    overlap = 3

    # Act
    chunks = _chunker(chunk_tokens=8, overlap_tokens=overlap).chunk(_document(ALPHABET))

    # Assert
    for earlier, later in pairwise(chunks):
        assert earlier.text[-overlap:] == later.text[:overlap]


def test_an_overlap_of_zero_partitions_the_document() -> None:
    """Nothing is repeated and nothing is lost."""
    # Act
    chunks = _chunker(chunk_tokens=10, overlap_tokens=0).chunk(_document(ALPHABET))

    # Assert
    assert [chunk.text for chunk in chunks] == ["abcdefghij", "klmnopqrst", "uvwxyz"]
    assert "".join(chunk.text for chunk in chunks) == ALPHABET


def test_a_document_of_exactly_one_chunk_size_gets_no_overlap_only_tail() -> None:
    """The exact-boundary case: 10 tokens at size 10 is one chunk, never two."""
    # Act
    chunks = _chunker(chunk_tokens=10, overlap_tokens=4).chunk(_document(ALPHABET[:10]))

    # Assert
    assert len(chunks) == 1
    assert chunks[0].token_count == 10


def test_one_token_past_the_boundary_produces_a_second_chunk_with_one_new_token() -> None:
    """The honest consequence of an overlap: the tail chunk is mostly a repeat."""
    # Act
    chunks = _chunker(chunk_tokens=10, overlap_tokens=4).chunk(_document(ALPHABET[:11]))

    # Assert
    assert len(chunks) == 2
    assert chunks[1].text == "ghijk"
    assert chunks[1].token_count == 5


def test_the_last_chunk_always_carries_at_least_one_unseen_token() -> None:
    """No chunk may be a pure duplicate of its predecessor's tail."""
    # Arrange
    chunker = _chunker(chunk_tokens=8, overlap_tokens=5)

    # Act
    for length in range(1, len(ALPHABET) + 1):
        chunks = chunker.chunk(_document(ALPHABET[:length]))

        # Assert
        assert chunks[-1].text.endswith(ALPHABET[length - 1])


def test_a_single_word_longer_than_a_chunk_is_split_rather_than_dropped() -> None:
    """A token stream has no word boundaries to respect, and must not need one."""
    # Arrange
    word = "Rahmenvereinbarungsverwaltungsvorschrift" * 3  # 123 characters, no spaces

    # Act
    chunks = _chunker(chunk_tokens=50, overlap_tokens=10).chunk(_document(word))

    # Assert
    assert len(chunks) == 3
    assert {chunk.pages for chunk in chunks} == {(1,)}
    assert chunks[0].text == word[:50]


# ------------------------------------------------------------------- page attribution


def test_a_chunk_inside_a_single_page_cites_only_that_page() -> None:
    # Act
    chunks = _chunker(chunk_tokens=3, overlap_tokens=0).chunk(_document("abc", "defg"))

    # Assert
    assert [chunk.pages for chunk in chunks] == [(1,), (2,), (2,)]
    assert [chunk.page for chunk in chunks] == [1, 2, 2]


def test_a_chunk_crossing_a_page_boundary_records_every_page_it_touches() -> None:
    """The S2.1.3 criterion, and the reason `page` is the *first* page it touches."""
    # Act
    chunks = _chunker(chunk_tokens=6, overlap_tokens=0).chunk(_document("abcd", "efgh", "ijkl"))

    # Assert
    assert [chunk.pages for chunk in chunks] == [(1, 2), (2, 3)]
    assert [chunk.page for chunk in chunks] == [1, 2]


def test_pages_are_joined_by_a_blank_line_so_the_text_reads_continuously() -> None:
    # Act
    chunks = _chunker(chunk_tokens=10, overlap_tokens=0).chunk(_document("abc", "def"))

    # Assert
    assert chunks[0].text == "abc\n\ndef"


def test_a_chunk_can_cite_two_pages_that_are_not_adjacent() -> None:
    """Only the middle page is unreadable, so pages 1 and 3 end up in one chunk."""
    # Act
    chunks = _chunker(chunk_tokens=10, overlap_tokens=0).chunk(_document("abc", "", "def"))

    # Assert
    assert chunks[0].pages == (1, 3)
    assert chunks[0].page == 1
    assert chunks[0].text == "abc\n\ndef"


def test_an_unreadable_page_contributes_no_tokens_and_no_citation() -> None:
    # Act
    chunks = _chunker(chunk_tokens=4, overlap_tokens=0).chunk(_document("   ", "abcdefg"))

    # Assert
    assert [chunk.pages for chunk in chunks] == [(2,), (2,)]
    assert [chunk.text for chunk in chunks] == ["abcd", "efg"]


def test_a_single_token_page_still_gets_its_own_citation() -> None:
    # Act
    chunks = _chunker(chunk_tokens=2, overlap_tokens=0).chunk(_document("ab", "c"))

    # Assert
    assert [chunk.pages for chunk in chunks] == [(1,), (2,)]


def test_a_document_with_no_readable_page_yields_no_chunks() -> None:
    """An image-only PDF: nothing to embed, and no empty chunk pretending otherwise."""
    # Act
    chunks = _chunker(chunk_tokens=10, overlap_tokens=2).chunk(_document("", "  ", "\n"))

    # Assert
    assert chunks == ()


def test_a_document_with_no_pages_yields_no_chunks() -> None:
    # Act / Assert
    assert _chunker(chunk_tokens=10, overlap_tokens=2).chunk(_document()) == ()


# ------------------------------------------------------------------------- the Chunk model


def test_a_chunk_is_immutable() -> None:
    # Arrange
    chunk = _chunker(chunk_tokens=10, overlap_tokens=0).chunk(_document("abc"))[0]

    # Act / Assert
    with pytest.raises(ValidationError):
        chunk.text = "something else"  # type: ignore[misc]


def test_the_cited_page_is_derived_from_the_pages_and_cannot_be_set() -> None:
    """Same reasoning as `unread_pages`: one source of truth, no drift."""
    # Act
    chunk = Chunk(document_id="doc-1", index=0, pages=(4, 5), text="x", token_count=1)

    # Assert
    assert chunk.page == 4
    assert chunk.model_dump()["page"] == 4


def test_a_chunk_must_name_at_least_one_page() -> None:
    """A chunk with no citable page would defeat the point of S2.1.1."""
    # Act / Assert
    with pytest.raises(ValidationError):
        Chunk(document_id="doc-1", index=0, pages=(), text="x", token_count=1)


def test_a_chunk_s_pages_must_be_in_ascending_order() -> None:
    """`page` is `pages[0]`, so an unsorted tuple would cite the wrong page."""
    # Act / Assert
    with pytest.raises(ValidationError, match="ascending"):
        Chunk(document_id="doc-1", index=0, pages=(3, 1), text="x", token_count=1)


# ------------------------------------------------------------------------- the tokeniser


def test_the_encoding_is_the_embedding_model_s_own() -> None:
    """cl100k_base is what `text-embedding-3-small` (ADR-0004) tokenises with."""
    # Assert
    assert ENCODING_NAME == "cl100k_base"
    assert tiktoken.encoding_name_for_model("text-embedding-3-small") == ENCODING_NAME


def test_the_default_encoder_is_built_once_from_that_encoding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Checked with a stub so the assertion holds on a machine with no BPE cache."""
    # Arrange
    requested: list[str] = []

    def fake_get_encoding(name: str) -> TokenEncoder:
        requested.append(name)
        return CharacterEncoder()

    monkeypatch.setattr(tiktoken, "get_encoding", fake_get_encoding)

    # Act
    first, second = default_token_encoder(), default_token_encoder()

    # Assert
    assert requested == [ENCODING_NAME]  # memoised: loading the table is not cheap
    assert first is second


def test_a_chunker_given_no_encoder_uses_the_default_one() -> None:
    # Arrange
    encoder = _real_encoder_or_skip()

    # Act
    chunks = Chunker(chunk_tokens=20, overlap_tokens=5).chunk(_document(GERMAN_SENTENCE))

    # Assert
    assert chunks[0].token_count == 20
    assert len(encoder.encode(GERMAN_SENTENCE)) == 21


def test_tokens_are_counted_by_the_tokeniser_and_not_by_characters() -> None:
    """21 tokens for 61 characters: a character count would be out by a factor of three."""
    # Arrange
    _real_encoder_or_skip()

    # Act
    chunks = Chunker(chunk_tokens=800, overlap_tokens=100).chunk(_document(GERMAN_SENTENCE))

    # Assert
    assert len(chunks) == 1
    assert chunks[0].token_count == 21
    assert len(GERMAN_SENTENCE) == 61


# ------------------------------------------------- the real parser, the real tokeniser


def test_the_de_fixture_chunks_to_target_size_with_every_chunk_citing_a_page() -> None:
    """End to end on 21 real German pages: sizes within 10% of 800, pages always citable."""
    # Arrange
    encoder = _real_encoder_or_skip()
    document = PyMuPDFParser().parse(DE_PDF, document_id="de-leistungsbeschreibung")

    # Act
    chunks = Chunker().chunk(document)

    # Assert
    assert document.page_count == 21
    assert len(chunks) > 1
    for chunk in chunks[:-1]:
        assert abs(chunk.token_count - DEFAULT_CHUNK_TOKENS) <= DEFAULT_CHUNK_TOKENS // 10
    for chunk in chunks:
        assert chunk.pages
        assert chunk.page == chunk.pages[0]
        assert set(chunk.pages) <= set(range(1, document.page_count + 1))
        assert len(encoder.encode(chunk.text)) <= DEFAULT_CHUNK_TOKENS * 11 // 10
    assert [chunk.page for chunk in chunks] == sorted(chunk.page for chunk in chunks)
