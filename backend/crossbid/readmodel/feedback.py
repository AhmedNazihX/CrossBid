"""S4.6.3 — the `feedback` table: what the bidder thought of one answer, kept as they said it.

`migrations/0001_init.sql` declared the table and this story is its first writer, so there is
no migration here. Two of its columns decide the shape of everything below.

**`matrix_row_id` is nullable.** A rating about a matrix row names it; a rating with none is
about the bid's own answer, which is what a chat answer will be when F3.5 lands. Refusing the
null case would be inventing a constraint the table does not have, and the `exists` branch in
the insert is what keeps the two apart without a second statement.

**There is no unique index on a target, so this is an append-only log.** A second thumb on
the same row is a second row, and `SELECT_LATEST_FEEDBACK` answers with the most recent one
per target. The story asks that corrections are *kept*, and a log keeps them where an upsert
would overwrite the bidder's first answer with their second. Nothing reads the log back into
the agent: feedback-driven learning is cut from the course build (docs/project-plan.md), so
these rows are stored and shown, never trained on.

**The tenant scope, and why the insert is an `insert ... select`.** The API connects as a
`BYPASSRLS` role, so the `company_id` predicate in each statement is the only thing between
two companies (ADR-0009). A plain `insert ... values` would bind the caller's `company_id`
as a value and write it blind — the row would land whatever bid it named. So the insert
selects the bid instead: the `where` proves the bid is the caller's, `company_id` is written
from *that row* rather than from the parameter, and an optional `matrix_row_id` has to belong
to the same bid and the same company or the `select` yields nothing and no row is inserted.
A bidder rating another company's row therefore inserts nothing at all, and the router turns
that into 404 — never 403, which would confirm the id exists (`routers/bids.py`'s reasoning).

Every statement carries `company_id` in its text; `SCOPED_STATEMENTS` lets a test assert it.
The connection protocol is `readmodel.bids.ConnectionSource`.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import IntEnum
from typing import Any, Final, LiteralString

from pydantic import BaseModel, ConfigDict, Field

from crossbid.readmodel.bids import ConnectionSource


class Rating(IntEnum):
    """A thumb, in the values the column already stores: `check (rating in (-1, 1))`.

    An `IntEnum` rather than words, because 0001 fixed the vocabulary of this column before
    the API existed and a `'up' -> 1` mapping layer would be a second place for it to drift.
    `DocumentStatus` lives beside its table for the same reason. A test asserts the two
    values against the check constraint, as `test_migrations.py` does for the text enums.
    """

    UP = 1
    DOWN = -1


class FeedbackRecord(BaseModel):
    """One stored rating, as the bidder's own screen reads it back.

    `company_id` is deliberately absent: it is the scope every statement here filters by,
    and a response that repeated it would tell the browser something it already asserted.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: int = Field(
        description="Identifies this rating; a later rating of the same target "
        "is a new row with a new id"
    )
    bid_id: str
    matrix_row_id: str | None = Field(
        default=None,
        description="The matrix row rated, or null when the rating is about the bid's answer",
    )
    rating: Rating = Field(description="1 for a thumb up, -1 for a thumb down")
    comment: str | None = Field(default=None, description="The bidder's correction, if given")
    created_at: datetime


# ------------------------------------------------------------------------- statements

INSERT_FEEDBACK: Final[LiteralString] = """
insert into feedback (company_id, bid_id, matrix_row_id, rating, comment)
select b.company_id, b.id, %(matrix_row_id)s::uuid, %(rating)s, %(comment)s
from bids b
where b.company_id = %(company_id)s
  and b.id = %(bid_id)s
  and (
      %(matrix_row_id)s::uuid is null
      or exists (
          select 1
          from matrix_rows m
          where m.id = %(matrix_row_id)s::uuid
            and m.company_id = %(company_id)s
            and m.bid_id = b.id
      )
  )
returning id, bid_id, matrix_row_id, rating, comment, created_at
"""
"""The one write. See the module docstring for why it selects the bid rather than binding
the tenant as a value.

The `::uuid` casts are not decoration: psycopg sends a `str` parameter as `unknown`, and
Postgres cannot resolve `%(matrix_row_id)s is null` without being told what the null is."""

SELECT_LATEST_FEEDBACK: Final[LiteralString] = """
select distinct on (matrix_row_id)
       id, bid_id, matrix_row_id, rating, comment, created_at
from feedback
where company_id = %(company_id)s and bid_id = %(bid_id)s
order by matrix_row_id, created_at desc, id desc
"""
"""What the workspace shows beside each row: the bidder's *latest* word on each target.

`distinct on` keeps the first row of each group, which the `order by` makes the newest —
and Postgres groups the nulls together, so the bid-level target answers one row like any
other. The whole log is still in the table for whoever reads it later; a screen that showed
every superseded thumb would be reporting history the bidder has already corrected."""

SCOPED_STATEMENTS: Final[tuple[LiteralString, ...]] = (
    INSERT_FEEDBACK,
    SELECT_LATEST_FEEDBACK,
)

TENANT_PARAMETER: Final = "company_id = %(company_id)s"
"""What the scope looks like in both statements, aliased or not."""


# -------------------------------------------------------------------------- operations


async def record_feedback(
    db: ConnectionSource,
    *,
    company_id: str,
    bid_id: str,
    rating: Rating,
    matrix_row_id: str | None = None,
    comment: str | None = None,
) -> FeedbackRecord | None:
    """Store one rating and answer it back, or `None` when there was nothing to rate.

    `None` covers a bid that is not this company's and a matrix row that is not that bid's,
    and the caller must not try to tell them apart: both are "no such thing here" to a
    bidder who cannot see either, and the router answers 404 for both.
    """
    params = {
        "company_id": company_id,
        "bid_id": bid_id,
        "matrix_row_id": matrix_row_id,
        "rating": rating.value,
        "comment": comment,
    }
    async with db.connection() as conn:
        record = await (await conn.execute(INSERT_FEEDBACK, params)).fetchone()
    return None if record is None else _record(record)


async def fetch_feedback(
    db: ConnectionSource, *, company_id: str, bid_id: str
) -> list[FeedbackRecord]:
    """The bidder's latest rating of each target in this bid, re-validated on the way out."""
    async with db.connection() as conn:
        records = await (
            await conn.execute(
                SELECT_LATEST_FEEDBACK, {"company_id": company_id, "bid_id": bid_id}
            )
        ).fetchall()
    return [_record(record) for record in records]


def _record(record: Mapping[str, Any]) -> FeedbackRecord:
    """A row back into the contract. The table is external data, so the model re-validates —
    a `rating` outside the check constraint's two values fails here rather than reaching a
    screen that has no word for it."""
    row_id = record["matrix_row_id"]
    return FeedbackRecord.model_validate(
        {
            "id": record["id"],
            "bid_id": str(record["bid_id"]),
            "matrix_row_id": None if row_id is None else str(row_id),
            "rating": record["rating"],
            "comment": record["comment"],
            "created_at": record["created_at"],
        }
    )
