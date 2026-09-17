"""M13 — the keyset cursor the two growing list routes page with.

**Why a cursor and not an offset.** Both lists are ordered newest first and both grow at the
head: a bidder uploads a file, a bid is started. Under `offset 50` an insert between two
requests shifts every row down one, so the second page repeats the row that was 50 and never
serves the one that was 51. The page boundary here is the *row* the caller last saw —
`(created_at, id)` — so an insert at the head changes what comes before the boundary and
nothing about where it is.

**Why `(created_at, id)` and not `created_at` alone.** `created_at` is not unique: two
documents of one upload batch can share a microsecond. The id breaks the tie, and both
columns are in the `order by` so the comparison is a single tuple test Postgres can answer
from an index.

**Why the cursor is opaque.** Not secrecy — the caller knows their own rows' timestamps. It is
that a cursor which reads as `2026-09-17T10:30:15Z|<uuid>` invites a caller to construct one,
and from then on the ordering of the read model is public API that cannot be changed. `decode`
refuses anything this module did not produce, and the router turns that into a 422 rather than
serving a page from a place nobody meant.

**Why a refused limit rather than a clamped one.** Clamping answers a request for 5 000 rows
with 50 and says nothing, which is the silent truncation this finding is about wearing a
different hat. The ceiling is part of the contract, so exceeding it is an error the caller can
read.
"""

from __future__ import annotations

import base64
import binascii
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

DEFAULT_PAGE_SIZE: Final = 50
"""What a caller who names no limit gets. A dashboard shows fewer than this above the fold."""

MAX_PAGE_SIZE: Final = 200
"""The most one request may ask for. `MAX_BIDS_LISTED` was this number as a silent cap; it is
the same number as a stated one, and now there is a page after it."""

_SEPARATOR: Final = "\x1e"
"""ASCII record separator: cannot occur in an ISO-8601 timestamp or a UUID, so the split is
unambiguous without escaping."""


class CursorError(ValueError):
    """The cursor was not one this module produced. The router answers 422."""


@dataclass(frozen=True, slots=True)
class PageCursor:
    """The last row of the previous page: where the next one starts, exclusive."""

    created_at: datetime
    row_id: uuid.UUID


def encode_cursor(cursor: PageCursor) -> str:
    """The opaque token a response hands back as `next_cursor`."""
    raw = f"{cursor.created_at.isoformat()}{_SEPARATOR}{cursor.row_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(value: str) -> PageCursor:
    """The place `value` names, or `CursorError`.

    The refusal never quotes `value` back: it arrives from the query string and reaches a
    screen as a 422 detail, and a message that echoes caller-controlled bytes is how the
    harmless ones start.
    """
    try:
        padded = value + "=" * (-len(value) % 4)
        raw = base64.urlsafe_b64decode(padded.encode()).decode()
        when, _, row_id = raw.partition(_SEPARATOR)
        if not _:
            raise CursorError(_REFUSAL)
        return PageCursor(created_at=datetime.fromisoformat(when), row_id=uuid.UUID(row_id))
    except CursorError:
        raise
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise CursorError(_REFUSAL) from exc


_REFUSAL: Final = (
    "That is not a cursor this API issued. Ask for the first page without one, and follow "
    "the `next_cursor` each answer carries."
)


def resolve_limit(requested: int | None) -> int:
    """`requested` if the contract allows it, else `DEFAULT_PAGE_SIZE` when none was asked
    for. Raises `ValueError` rather than clamping — see the module docstring."""
    if requested is None:
        return DEFAULT_PAGE_SIZE
    if requested < 1:
        raise ValueError("A page holds at least one row.")
    if requested > MAX_PAGE_SIZE:
        raise ValueError(f"A page holds at most {MAX_PAGE_SIZE} rows.")
    return requested


@dataclass(frozen=True, slots=True)
class Page[T]:
    """One page of rows and, when there are more, where to continue."""

    items: tuple[T, ...]
    next_cursor: str | None

    @classmethod
    def of(
        cls, rows: Sequence[T], *, limit: int, key: Callable[[T], tuple[datetime, uuid.UUID]]
    ) -> Page[T]:
        """A page out of the `limit + 1` rows the query asked for.

        The extra row is how "is there more" is answered without a second `count(*)` over a
        table that is being written to. It is never served: a page is `limit` rows or fewer,
        and `len(rows) == limit` means the extra row was *not* returned, so this is the last
        page — the boundary the obvious version gets wrong by one.
        """
        if len(rows) <= limit:
            return cls(items=tuple(rows), next_cursor=None)
        served = tuple(rows[:limit])
        created_at, row_id = key(served[-1])
        return cls(
            items=served,
            next_cursor=encode_cursor(PageCursor(created_at=created_at, row_id=row_id)),
        )
