"""Recover the language each existing analysis was actually written in.

    DATABASE_URL=… uv run python scripts/backfill_bid_languages.py              # dry run
    DATABASE_URL=… uv run python scripts/backfill_bid_languages.py --apply

**Why this is not one line of SQL.** `bids.bidder_language` arrived empty in migration 0011,
deliberately. Until then the field was read from `companies.language`, so "the language this
analysis explains requirements in" silently meant "the language this company prefers now" —
and the bug that exposed it was a bidder switching that setting and watching German
requirements relabel themselves English (2026-09-18). Backfilling from `companies.language`
would therefore write the *new* preference onto exactly the bids the column exists to protect,
and make the mistake permanent.

**Where the truth is.** The run's own LangGraph state. `BidState.bidder_language` is what
`extract_reqs` translated into, what `check_reqs` wrote rationales in and what `score_verdict`
argued in, and it is checkpointed on the thread `bid:{id}` like the rest of the state. Reading
it back is a record, not a heuristic: no language detector is run over the prose and nothing is
inferred from what the text looks like.

**A bid whose checkpoint is gone is left null**, and that is the honest answer for it. Nothing
else in the database remembers: `requirements` stores `source_lang` and a `translation` with no
language of its own, and the matrix stores prose. A null reads as "not recorded", the read model
falls back to the company's language exactly as it does today, and nobody is told a language the
system cannot stand behind.

Costs nothing and touches no model: two queries and a checkpoint read per bid.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, LiteralString

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    # `[tool.uv] package = false`, so `crossbid` is importable only via the project root.
    sys.path.insert(0, str(BACKEND_DIR))

from crossbid.agent.state import bidder_language_of  # noqa: E402
from crossbid.db import Database, DatabaseError  # noqa: E402
from crossbid.readmodel.bids import thread_id_of  # noqa: E402
from crossbid.settings import SettingsError, load_settings  # noqa: E402

INPUT_ERROR: Final = 2

UNRECORDED_BIDS_SQL: Final[LiteralString] = """
select bids.id::text               as bid_id,
       bids.ted_publication_number as notice_number,
       bids.title                  as title,
       companies.language          as company_language
from bids
join companies on companies.id = bids.company_id
where bids.bidder_language is null
order by bids.created_at
"""

RECORD_LANGUAGE_SQL: Final[LiteralString] = """
update bids set bidder_language = %(language)s where id = %(bid_id)s
"""


@dataclass(frozen=True, slots=True)
class Unrecorded:
    bid_id: str
    notice_number: str | None
    title: str
    company_language: str

    @property
    def label(self) -> str:
        return self.notice_number or self.title


async def unrecorded_bids(db: Database) -> tuple[Unrecorded, ...]:
    async with db.connection() as conn:
        rows = await (await conn.execute(UNRECORDED_BIDS_SQL)).fetchall()
    return tuple(
        Unrecorded(
            bid_id=row["bid_id"],
            notice_number=row["notice_number"],
            title=row["title"],
            company_language=str(row["company_language"]),
        )
        for row in rows
    )


async def recorded_language(db: Database, bid_id: str) -> str | None:
    """What the run itself used, from its checkpoint, or `None` when there is no checkpoint."""
    config: Any = {"configurable": {"thread_id": thread_id_of(bid_id)}}
    snapshot = await db.checkpointer.aget_tuple(config)
    if snapshot is None:
        return None
    values = snapshot.checkpoint.get("channel_values", {})
    language = values.get("bidder_language")
    if not isinstance(language, str):
        return None
    # Through the accessor the graph uses, so a blank is treated the way the run treated it.
    return bidder_language_of({"bidder_language": language})  # type: ignore[typeddict-item]


async def run(*, apply: bool) -> int:
    settings = load_settings()
    dsn = settings.env.database_url
    if dsn is None:
        print("DATABASE_URL is not set — point it at the database to backfill", file=sys.stderr)
        return INPUT_ERROR

    db = await Database.connect(dsn.get_secret_value())
    try:
        bids = await unrecorded_bids(db)
        if not bids:
            print("Nothing to do: every bid records the language it was analysed in.")
            return 0

        print(f"{len(bids)} bid(s) with no recorded language:\n")
        recovered = 0
        for bid in bids:
            language = await recorded_language(db, bid.bid_id)
            if language is None:
                print(
                    f"  {bid.label}  {bid.bid_id}  no checkpoint — left unrecorded "
                    f"(reads as {bid.company_language}, the company's current setting)"
                )
                continue
            changes = "" if language == bid.company_language else "  ← differs from the company"
            print(f"  {bid.label}  {bid.bid_id}  analysed in {language}{changes}")
            if apply:
                async with db.connection() as conn:
                    await conn.execute(
                        RECORD_LANGUAGE_SQL, {"language": language, "bid_id": bid.bid_id}
                    )
            recovered += 1

        if not apply:
            print("\nDry run: nothing was written. Re-run with --apply.")
            return 0
        print(f"\n{recovered} bid(s) now record their own language.")
    finally:
        await db.close()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--apply", action="store_true", help="Write. Without it nothing is changed."
    )
    args = parser.parse_args(argv)
    try:
        return asyncio.run(run(apply=args.apply))
    except (SettingsError, DatabaseError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return INPUT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
