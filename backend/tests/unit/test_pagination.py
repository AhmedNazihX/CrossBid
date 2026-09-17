"""M13 — the keyset cursor both list routes page with.

Offline and pure: nothing here touches a connection. What is asserted is the one property a
cursor has to have and an offset does not — that a page boundary survives rows being inserted
at the head of the list, which on `documents` happens every time a bidder uploads a file, and
on `bids` every time one is started. An `offset 50` re-read after one insert repeats a row and
hides another; a keyset cursor names the last row it saw and cannot.

The encoding is opaque on purpose. A caller who decodes it and builds their own is writing
against an internal ordering, so `decode` refuses anything it did not produce rather than
guessing, and a refusal is the router's 422 rather than a page of someone else's rows.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from crossbid.readmodel.pagination import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    CursorError,
    Page,
    PageCursor,
    decode_cursor,
    encode_cursor,
    resolve_limit,
)

AN_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
A_TIME = datetime(2026, 9, 17, 10, 30, 15, 123456, tzinfo=UTC)


class TestTheCursorRoundTrip:
    def test_decoding_what_was_encoded_gives_the_same_place_back(self) -> None:
        # Arrange / Act
        restored = decode_cursor(encode_cursor(PageCursor(created_at=A_TIME, row_id=AN_ID)))

        # Assert
        assert restored == PageCursor(created_at=A_TIME, row_id=AN_ID)

    def test_microseconds_survive_the_round_trip(self) -> None:
        """Two documents uploaded in the same second are ordered by the microsecond, so a
        cursor that dropped it would re-serve or skip the row it was pointing at."""
        # Arrange
        first = PageCursor(created_at=A_TIME, row_id=AN_ID)
        second = PageCursor(created_at=A_TIME + timedelta(microseconds=1), row_id=AN_ID)

        # Act / Assert
        assert encode_cursor(first) != encode_cursor(second)
        assert decode_cursor(encode_cursor(second)).created_at == second.created_at

    def test_the_encoding_is_opaque(self) -> None:
        """Not a security property — it is a contract one. A cursor that reads as a timestamp
        invites a caller to build one, and then the ordering is public API."""
        # Act
        encoded = encode_cursor(PageCursor(created_at=A_TIME, row_id=AN_ID))

        # Assert
        assert "2026" not in encoded
        assert str(AN_ID) not in encoded


class TestARefusedCursor:
    @pytest.mark.parametrize(
        ("value", "why"),
        [
            ("", "empty"),
            ("not-base64-!!", "not base64"),
            ("Zm9vYmFy", "base64 of something else"),
            ("MjAyNi0wOS0xN1QxMDozMDoxNVpebm90LWEtdXVpZA==", "a good time, a bad id"),
        ],
    )
    def test_anything_this_module_did_not_produce_is_refused(
        self, value: str, why: str
    ) -> None:
        # Act / Assert
        with pytest.raises(CursorError):
            decode_cursor(value)

    def test_the_refusal_does_not_quote_the_cursor_back(self) -> None:
        """It reaches the browser as a 422 detail, and echoing caller-controlled bytes into a
        message a screen renders is how the harmless ones start."""
        # Act
        with pytest.raises(CursorError) as raised:
            decode_cursor("<script>alert(1)</script>")

        # Assert
        assert "script" not in str(raised.value)


class TestTheLimit:
    def test_no_limit_asked_for_gives_the_default(self) -> None:
        assert resolve_limit(None) == DEFAULT_PAGE_SIZE

    def test_a_limit_over_the_ceiling_is_refused_rather_than_quietly_clamped(self) -> None:
        """Clamping would answer 50 rows to a request for 5 000 and say nothing, which is the
        silent truncation this whole finding is about."""
        # Act / Assert
        with pytest.raises(ValueError):
            resolve_limit(MAX_PAGE_SIZE + 1)

    @pytest.mark.parametrize("value", [0, -1])
    def test_a_limit_of_zero_or_less_is_refused(self, value: int) -> None:
        with pytest.raises(ValueError):
            resolve_limit(value)

    def test_a_limit_inside_the_range_is_honoured(self) -> None:
        assert resolve_limit(7) == 7


class TestThePage:
    def test_a_full_page_carries_a_cursor_to_the_next_one(self) -> None:
        # Arrange: the read model asks for one more row than it wants, to learn there is more.
        rows = [
            {"created_at": A_TIME - timedelta(minutes=n), "id": uuid.uuid4()} for n in range(4)
        ]

        # Act
        page = Page.of(rows, limit=3, key=lambda row: (row["created_at"], row["id"]))

        # Assert
        assert len(page.items) == 3
        assert page.next_cursor is not None
        assert decode_cursor(page.next_cursor) == PageCursor(
            created_at=rows[2]["created_at"], row_id=rows[2]["id"]
        )

    def test_the_overflow_row_is_not_served(self) -> None:
        """The limit+1 row exists only to answer "is there more"; serving it would make every
        page one row longer than the caller asked for."""
        # Arrange
        rows = [
            {"created_at": A_TIME - timedelta(minutes=n), "id": uuid.uuid4()} for n in range(4)
        ]

        # Act
        page = Page.of(rows, limit=3, key=lambda row: (row["created_at"], row["id"]))

        # Assert
        assert rows[3] not in page.items

    def test_a_short_page_is_the_last_page(self) -> None:
        # Arrange
        rows = [{"created_at": A_TIME, "id": AN_ID}]

        # Act
        page = Page.of(rows, limit=3, key=lambda row: (row["created_at"], row["id"]))

        # Assert
        assert page.next_cursor is None
        assert len(page.items) == 1

    def test_an_exactly_full_page_with_nothing_after_it_still_ends(self) -> None:
        """The boundary the naive version gets wrong: `len(rows) == limit` means the limit+1
        row was *not* returned, so this is the end, not a full page with more behind it."""
        # Arrange
        rows = [
            {"created_at": A_TIME - timedelta(minutes=n), "id": uuid.uuid4()} for n in range(3)
        ]

        # Act
        page = Page.of(rows, limit=3, key=lambda row: (row["created_at"], row["id"]))

        # Assert
        assert page.next_cursor is None
        assert len(page.items) == 3

    def test_no_rows_at_all_is_an_empty_last_page(self) -> None:
        # Act
        page = Page.of([], limit=3, key=lambda row: (row["created_at"], row["id"]))

        # Assert
        assert page.items == ()
        assert page.next_cursor is None
