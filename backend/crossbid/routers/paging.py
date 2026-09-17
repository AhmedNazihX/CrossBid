"""M13 — the `limit` and `cursor` query parameters, in one place for both list routes.

`GET /documents` and `GET /bids` page identically, so they read the pair identically: the
descriptions OpenAPI publishes, the refusals a caller gets, and the translation from two
strings on a URL into the read model's arguments all live here rather than twice.

**Why a 422 and not a clamp.** `readmodel/pagination.py` explains the reasoning; this module
is where it becomes an HTTP answer. A caller who asks for 5 000 rows has misread the contract
and is told so, instead of receiving 50 rows that look like the whole list — which is the
silent truncation the finding is about.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from fastapi import HTTPException, status

from crossbid.readmodel.pagination import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    CursorError,
    PageCursor,
    decode_cursor,
    resolve_limit,
)

PAGE_LIMIT_DESCRIPTION: Final = (
    f"Rows on this page, 1 to {MAX_PAGE_SIZE}. Omitted, {DEFAULT_PAGE_SIZE}."
)

PAGE_CURSOR_DESCRIPTION: Final = (
    "The `next_cursor` of the previous page. Omitted, the first page. Opaque: its shape is "
    "not part of the contract and a cursor from anywhere else is refused."
)


@dataclass(frozen=True, slots=True)
class PageRequest:
    """What the two query parameters mean once they are known to be usable."""

    limit: int
    after: PageCursor | None


def page_request(*, limit: int | None, cursor: str | None) -> PageRequest:
    """The read model's arguments, or the 422 that names what is wrong.

    A typed pair rather than a `**kwargs` dict: the dict version type-checks as `object` at
    every call site, which is how a read model's signature could change underneath a router
    with nothing to say so.
    """
    try:
        resolved = resolve_limit(limit)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    return PageRequest(limit=resolved, after=_after(cursor))


def _after(cursor: str | None) -> PageCursor | None:
    if cursor is None:
        return None
    try:
        return decode_cursor(cursor)
    except CursorError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
