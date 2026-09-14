"""S5.2 — the `llm_usage` table: what each node spent, written once and summed on the way out.

`migrations/0001_init.sql` declared the table and this story is its first writer, so there is
no migration here. Four decisions shape what is below.

**The write proves the bid belongs to the tenant rather than binding the tenant as a value.**
The API connects as a `BYPASSRLS` role, so the `company_id` predicate in each statement is
the only thing between two companies (ADR-0009), and `readmodel/feedback.py` sets the
pattern: the insert selects the bid, the `where` proves whose it is, and `company_id` is
written from *that row* instead of from the parameter. Here the pairing is the same hazard
in a quieter place — a cost row filed under the wrong tenant is a tenant reading another's
spend — and the select form also turns a bid that has been deleted mid-run into `rowcount`
zero, which the sink can log, rather than a foreign-key violation raised inside a LangChain
callback where the exception is swallowed.

**`bid_id` is nullable in the column and required here.** The column is nullable for spend
that belongs to no bid, which S5.6 will write when a company runs on its own key outside a
run. Nothing in this increment produces such a row: the one non-bid model call is S5.3's
injection review during ingestion, which `usage._warn_unattributed` deliberately leaves in
the log (see that module for why). Requiring a bid on the write keeps the statement to one
shape; the readers still treat `bid_id` as nullable, because the column is.

**Unpriced calls are counted, not hidden.** `cost_usd` is `not null default 0`, so a
response OpenRouter did not price has to be stored as zero — and a zero that means "we do
not know" is indistinguishable from a zero that means "free" unless somebody counts it. Both
read statements therefore carry `count(*) filter (where cost_usd = 0 and input_tokens +
output_tokens > 0)`: a call that moved tokens and cost nothing is either unpriced or too
small to round above the column's sixth decimal place, and either way the total beside it is
a lower bound. Reporting the total alone would be wrong in the safe-looking direction, which
is the direction nobody audits.

**Money is `numeric` in Postgres and a `float` on the wire.** The sums are done by the
database in `numeric`, exact to the column's six places. They leave as floats because
Pydantic renders a `Decimal` as a JSON *string*, and `frontend/lib/api.ts` is generated from
this schema — a panel that had to parse `"1.380000"` before adding it up would be paying for
a precision no cost report needs.

Every statement carries `company_id` in its text; `SCOPED_STATEMENTS` lets a test assert it.
The connection protocol is `readmodel.bids.ConnectionSource`.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Final, LiteralString

from pydantic import BaseModel, ConfigDict, Field

from crossbid.models.provider import Provider
from crossbid.readmodel.bids import ConnectionSource
from crossbid.usage import UsageEvent, UsageNode

logger = logging.getLogger(__name__)

DEFAULT_BID_LIMIT: Final = 50
MAX_BID_LIMIT: Final = 200
"""How many bids `GET /dev/costs` lists at once. A developer panel reads the recent ones and
narrows to a bid id for the rest; an unbounded `group by` over every bid a company has ever
run is a query whose cost grows with the product."""

UNPRICED_COST: Final = 0
"""What a response the provider did not price is stored as, because the column is
`not null`. See the module docstring: it is counted separately so the zero cannot be read
as "free"."""


# ------------------------------------------------------------------------------- rows


class UsageTotals(BaseModel):
    """Tokens, calls and money over some set of `llm_usage` rows.

    The base of both breakdowns and the shape of the grand total, so the panel adds up the
    same five numbers wherever it shows them.
    """

    model_config = ConfigDict(frozen=True)

    calls: int = Field(description="Model responses counted, one row per response")
    input_tokens: int
    output_tokens: int
    cost_usd: float = Field(
        description="What OpenRouter charged, as OpenRouter reported it — never a local rate"
    )
    unpriced_calls: int = Field(
        description=(
            "Calls that moved tokens and reported no cost, so cost_usd is a lower bound. "
            "Non-zero means the provider stopped pricing responses, or the calls were "
            "smaller than the stored sixth decimal place."
        )
    )


class NodeUsage(UsageTotals):
    """One node's spend on one model. Grouped by model as well as node on purpose.

    The `fallback` role means a single logical call can be answered by two different
    vendors: the primary times out, `llm.ResilientModel` reissues, and the tokens are bought
    twice from two places. `model` is read off the provider's own response (`usage.CallUsage`),
    so a node that fell back shows two lines whose totals add up, rather than one line
    claiming the configured slug did all of it.
    """

    node: UsageNode
    provider: Provider = Field(description="Where the tokens were bought")
    model: str = Field(description="The slug that answered, as the response reported it")


class BidUsage(UsageTotals):
    """One bid's whole spend, across every node and model it used."""

    bid_id: str | None = Field(
        default=None,
        description="The bid, or null for spend that belongs to no run (S5.6 writes those)",
    )
    last_call_at: datetime = Field(description="The most recent model call charged to it")


# ------------------------------------------------------------------------- statements

INSERT_USAGE: Final[LiteralString] = """
insert into llm_usage
    (company_id, bid_id, node, provider, model, input_tokens, output_tokens, cost_usd)
select b.company_id, b.id, %(node)s, %(provider)s, %(model)s,
       %(input_tokens)s, %(output_tokens)s, %(cost_usd)s
from bids b
where b.company_id = %(company_id)s::uuid
  and b.id = %(bid_id)s::uuid
"""
"""The one write. See the module docstring for why it selects the bid rather than binding
the tenant as a value.

The `::uuid` casts are not decoration: psycopg sends a `str` parameter as `unknown`, and
comparing an unknown to a `uuid` column is a planner error rather than a match."""

UNPRICED_EXPRESSION: Final = (
    "count(*) filter (where cost_usd = 0 and input_tokens + output_tokens > 0)"
)
"""How both readers count a call the provider did not price. Written out again in each
statement below rather than interpolated into them — `ingestion/embeddings.py` states the
rule and the reason: a query built by string composition is a query that can be built
wrongly, and psycopg's `LiteralString` typing is what enforces it. This constant exists so
a test can assert the two statements count the same thing, not so they can share a string."""

SELECT_USAGE_BY_NODE: Final[LiteralString] = """
select node,
       provider,
       model,
       count(*) as calls,
       sum(input_tokens) as input_tokens,
       sum(output_tokens) as output_tokens,
       sum(cost_usd) as cost_usd,
       count(*) filter (where cost_usd = 0 and input_tokens + output_tokens > 0)
           as unpriced_calls
from llm_usage
where company_id = %(company_id)s::uuid
  and (%(bid_id)s::uuid is null or bid_id = %(bid_id)s::uuid)
group by node, provider, model
order by sum(cost_usd) desc, node, model
"""
"""Where the money went, dearest first — which is the question the story asks.

`%(bid_id)s::uuid is null` is how one statement serves both "this company" and "this bid":
a second statement differing by one predicate is a second place for the scope to be got
wrong, and the cast is what lets Postgres resolve the null."""

SELECT_USAGE_BY_BID: Final[LiteralString] = """
select bid_id,
       max(created_at) as last_call_at,
       count(*) as calls,
       sum(input_tokens) as input_tokens,
       sum(output_tokens) as output_tokens,
       sum(cost_usd) as cost_usd,
       count(*) filter (where cost_usd = 0 and input_tokens + output_tokens > 0)
           as unpriced_calls
from llm_usage
where company_id = %(company_id)s::uuid
  and (%(bid_id)s::uuid is null or bid_id = %(bid_id)s::uuid)
group by bid_id
order by max(created_at) desc
limit %(limit)s
"""
"""What each recent run cost. Most recently active first rather than dearest, because the
panel's other question is "what did the bid I just ran cost", and `llm_usage_company_id_
created_at_idx` is the index 0001 already built for exactly this ordering."""

SCOPED_STATEMENTS: Final[tuple[LiteralString, ...]] = (
    INSERT_USAGE,
    SELECT_USAGE_BY_NODE,
    SELECT_USAGE_BY_BID,
)

TENANT_PARAMETER: Final = "company_id = %(company_id)s::uuid"
"""What the scope looks like in all three statements, aliased or not."""


# -------------------------------------------------------------------------- operations


class DatabaseUsageSink:
    """`usage.UsageSink` over the `llm_usage` table, one row per model response.

    Writes as the call finishes rather than buffering per node. A buffer would spare the
    pool a few borrows and would lose every row of a run that crashed — and a run that
    crashed halfway through checking is exactly the run whose cost somebody wants to see.
    The volume is what makes that affordable: the measured DE pack spent 49 calls.
    """

    def __init__(self, db: ConnectionSource) -> None:
        self._db = db

    async def record(self, event: UsageEvent) -> None:
        """Store one call's usage, or say why it stored nothing.

        `rowcount` zero means the bid is not this company's or no longer exists — the insert
        selects it (see the module docstring), so there is nothing to insert and no error to
        raise. It is logged because the alternative is a run whose cost quietly stops being
        counted halfway through.
        """
        async with self._db.connection() as conn:
            cursor = await conn.execute(INSERT_USAGE, _insert_params(event))
            written = cursor.rowcount
        if written == 0:
            logger.warning(
                "Bid %s: the cost of a '%s' call was not stored — no such bid for this "
                "company, so /dev/costs will understate the run",
                event.bid_id,
                event.model,
            )


def _insert_params(event: UsageEvent) -> dict[str, Any]:
    """One event as bound parameters. `None` cost becomes the column's zero; see the module."""
    return {
        "company_id": event.company_id,
        "bid_id": event.bid_id,
        "node": event.node.value,
        "provider": event.provider.value,
        "model": event.model,
        "input_tokens": event.input_tokens,
        "output_tokens": event.output_tokens,
        "cost_usd": UNPRICED_COST if event.cost_usd is None else event.cost_usd,
    }


async def fetch_usage_by_node(
    db: ConnectionSource, *, company_id: str, bid_id: str | None = None
) -> tuple[NodeUsage, ...]:
    """Spend per node and model, dearest first. `bid_id` narrows it to one run."""
    async with db.connection() as conn:
        records = await (
            await conn.execute(
                SELECT_USAGE_BY_NODE, {"company_id": company_id, "bid_id": bid_id}
            )
        ).fetchall()
    return tuple(
        NodeUsage.model_validate(_totals(record) | _node_fields(record)) for record in records
    )


async def fetch_usage_by_bid(
    db: ConnectionSource,
    *,
    company_id: str,
    bid_id: str | None = None,
    limit: int = DEFAULT_BID_LIMIT,
) -> tuple[BidUsage, ...]:
    """Spend per bid, most recently active first. `bid_id` narrows it to one run."""
    async with db.connection() as conn:
        records = await (
            await conn.execute(
                SELECT_USAGE_BY_BID,
                {"company_id": company_id, "bid_id": bid_id, "limit": limit},
            )
        ).fetchall()
    return tuple(
        BidUsage.model_validate(_totals(record) | _bid_fields(record)) for record in records
    )


def totals_of(lines: Sequence[UsageTotals]) -> UsageTotals:
    """The grand total of a breakdown, added up here rather than asked of the database.

    The per-node breakdown is unlimited, so summing it is exact and costs one statement
    fewer than a third query — and a total that came from its own `select` could disagree
    with the lines under it if the two ran either side of a write.
    """
    return UsageTotals(
        calls=sum(line.calls for line in lines),
        input_tokens=sum(line.input_tokens for line in lines),
        output_tokens=sum(line.output_tokens for line in lines),
        cost_usd=sum(line.cost_usd for line in lines),
        unpriced_calls=sum(line.unpriced_calls for line in lines),
    )


def _totals(record: Mapping[str, Any]) -> dict[str, Any]:
    """The five aggregate columns every row carries, as the models want them."""
    return {
        "calls": record["calls"],
        "input_tokens": record["input_tokens"],
        "output_tokens": record["output_tokens"],
        "cost_usd": float(record["cost_usd"]),
        "unpriced_calls": record["unpriced_calls"],
    }


def _node_fields(record: Mapping[str, Any]) -> dict[str, Any]:
    """The grouping columns of a per-node line. `node` and `provider` are re-validated by
    the model against their closed sets: the table is `text` with no check constraint on
    either, so a value nothing in this package writes would otherwise reach a panel."""
    return {
        "node": record["node"],
        "provider": record["provider"],
        "model": record["model"],
    }


def _bid_fields(record: Mapping[str, Any]) -> dict[str, Any]:
    """The grouping columns of a per-bid line, with the nullable id kept nullable."""
    bid_id = record["bid_id"]
    return {
        "bid_id": None if bid_id is None else str(bid_id),
        "last_call_at": record["last_call_at"],
    }
