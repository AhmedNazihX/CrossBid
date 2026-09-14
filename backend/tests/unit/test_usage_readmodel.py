"""S5.2 — the `llm_usage` statements: what they say, and what they refuse to say.

Offline, over `conftest`'s recording connection. The SQL is never executed, so what is
asserted is the text the route and the sink *send* — which is the only thing that stands
between two companies, because the API connects as a `BYPASSRLS` role and row-level
security is silently inert for it (ADR-0009).

Three claims are worth stating before the tests.

**The tenant is in every statement's text, not in a caller's discipline.** `SCOPED_STATEMENTS`
is asserted as a whole rather than one statement at a time, so a fourth statement added later
is covered by a test nobody has to remember to extend.

**The insert takes the tenant off the bid row rather than binding it.** The parameter is
what proves ownership; the column is written from the matched row. A bid that is not this
company's therefore inserts nothing at all, which is the property the last group checks by
reading the SQL rather than by trusting a fake to model it.

**An unpriced call is counted the same way in both readers.** They are separate statements
on purpose (`ingestion/embeddings.py` states why a scoped query is never composed), so the
one thing they must agree on is asserted directly.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from crossbid.models.provider import Provider
from crossbid.readmodel.usage import (
    DEFAULT_BID_LIMIT,
    INSERT_USAGE,
    MAX_BID_LIMIT,
    SCOPED_STATEMENTS,
    SELECT_USAGE_BY_BID,
    SELECT_USAGE_BY_NODE,
    TENANT_PARAMETER,
    UNPRICED_EXPRESSION,
    BidUsage,
    DatabaseUsageSink,
    NodeUsage,
    UsageTotals,
    fetch_usage_by_bid,
    fetch_usage_by_node,
    totals_of,
)
from crossbid.usage import UsageEvent, UsageNode
from tests.conftest import FakeConnectionSource

pytestmark = pytest.mark.anyio

COMPANY_ID = str(uuid.uuid4())
BID_ID = uuid.uuid4()
MODEL = "openai/gpt-5.6-terra"
FALLBACK_MODEL = "google/gemini-2.5-flash"
NOW = datetime(2026, 9, 14, 10, 30, tzinfo=UTC)


def event(**overrides: Any) -> UsageEvent:
    values: dict[str, Any] = {
        "company_id": COMPANY_ID,
        "bid_id": str(BID_ID),
        "node": UsageNode.CHECK_REQS,
        "provider": Provider.OPENROUTER,
        "model": MODEL,
        "input_tokens": 1_200,
        "output_tokens": 300,
        "cost_usd": Decimal("0.0138"),
    }
    return UsageEvent(**(values | overrides))


def node_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "node": UsageNode.CHECK_REQS.value,
        "provider": Provider.OPENROUTER.value,
        "model": MODEL,
        "calls": 42,
        "input_tokens": 90_000,
        "output_tokens": 12_000,
        "cost_usd": Decimal("1.234500"),
        "unpriced_calls": 0,
    }
    return row | overrides


def bid_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "bid_id": BID_ID,
        "last_call_at": NOW,
        "calls": 49,
        "input_tokens": 100_000,
        "output_tokens": 14_000,
        "cost_usd": Decimal("1.380000"),
        "unpriced_calls": 0,
    }
    return row | overrides


# ------------------------------------------------------------------------ tenant scope


def test_every_statement_carries_the_tenant_in_its_own_text() -> None:
    """The only thing between two companies. Asserted over the whole tuple, so a statement
    added later is covered without anyone extending this test."""
    # Assert
    assert SCOPED_STATEMENTS
    for statement in SCOPED_STATEMENTS:
        assert TENANT_PARAMETER in statement


def test_both_readers_count_an_unpriced_call_the_same_way() -> None:
    """They are separate statements by design; the total and the per-bid list would
    otherwise disagree about the same rows."""
    # Assert
    assert UNPRICED_EXPRESSION in SELECT_USAGE_BY_NODE
    assert UNPRICED_EXPRESSION in SELECT_USAGE_BY_BID


def test_the_insert_writes_the_tenant_from_the_bid_row_and_not_from_the_parameter() -> None:
    """`readmodel/feedback.py`'s rule: a pair of ids is proved, never bound blind."""
    # Assert
    assert "select b.company_id, b.id" in INSERT_USAGE
    assert "from bids b" in INSERT_USAGE
    assert "b.id = %(bid_id)s::uuid" in INSERT_USAGE


def test_a_bid_filter_that_is_absent_widens_the_query_instead_of_narrowing_it() -> None:
    """One statement serves "this company" and "this bid"; a second would be a second
    place for the scope to be got wrong."""
    # Assert
    for statement in (SELECT_USAGE_BY_NODE, SELECT_USAGE_BY_BID):
        assert "%(bid_id)s::uuid is null or bid_id = %(bid_id)s::uuid" in statement


def test_the_node_breakdown_is_ordered_by_what_it_cost() -> None:
    """ "Where the money goes" is a question about order, not only about numbers."""
    assert "order by sum(cost_usd) desc" in SELECT_USAGE_BY_NODE


def test_the_bid_list_is_ordered_the_way_0001_indexed_it() -> None:
    """`llm_usage_company_id_created_at_idx` is `(company_id, created_at desc)`."""
    assert "order by max(created_at) desc" in SELECT_USAGE_BY_BID


# -------------------------------------------------------------------------- the write


async def test_one_call_is_one_row_with_the_node_and_the_model_that_answered() -> None:
    # Arrange
    source = FakeConnectionSource([{"ok": 1}])

    # Act
    await DatabaseUsageSink(source).record(event(model=FALLBACK_MODEL))

    # Assert
    statement = source.only
    assert statement.sql == INSERT_USAGE
    assert statement.params == {
        "company_id": COMPANY_ID,
        "bid_id": str(BID_ID),
        "node": "check_reqs",
        "provider": "openrouter",
        "model": FALLBACK_MODEL,
        "input_tokens": 1_200,
        "output_tokens": 300,
        "cost_usd": Decimal("0.0138"),
    }


async def test_an_unpriced_call_is_stored_as_zero_because_the_column_is_not_null() -> None:
    """The distinction survives as `unpriced_calls`, which both readers compute."""
    # Arrange
    source = FakeConnectionSource([{"ok": 1}])

    # Act
    await DatabaseUsageSink(source).record(event(cost_usd=None))

    # Assert
    assert source.only.params["cost_usd"] == 0


async def test_a_row_that_matched_no_bid_is_logged_rather_than_lost_in_silence(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The insert selects the bid, so a bid that is not this company's inserts nothing and
    raises nothing. Without this line the run's cost would quietly stop being counted."""
    # Arrange
    source = FakeConnectionSource()

    # Act
    with caplog.at_level(logging.WARNING, logger="crossbid.readmodel.usage"):
        await DatabaseUsageSink(source).record(event())

    # Assert
    assert "was not stored" in caplog.text
    assert MODEL in caplog.text


# --------------------------------------------------------------------------- the reads


async def test_the_node_breakdown_comes_back_as_typed_lines() -> None:
    # Arrange
    source = FakeConnectionSource([node_row(), node_row(model=FALLBACK_MODEL, calls=2)])

    # Act
    lines = await fetch_usage_by_node(source, company_id=COMPANY_ID)

    # Assert
    assert [line.model for line in lines] == [MODEL, FALLBACK_MODEL]
    assert lines[0] == NodeUsage(
        node=UsageNode.CHECK_REQS,
        provider=Provider.OPENROUTER,
        model=MODEL,
        calls=42,
        input_tokens=90_000,
        output_tokens=12_000,
        cost_usd=1.2345,
        unpriced_calls=0,
    )
    assert source.only.params == {"company_id": COMPANY_ID, "bid_id": None}


async def test_a_bid_filter_reaches_the_statement_as_a_parameter() -> None:
    # Arrange
    source = FakeConnectionSource([node_row()])

    # Act
    await fetch_usage_by_node(source, company_id=COMPANY_ID, bid_id=str(BID_ID))

    # Assert
    assert source.only.params["bid_id"] == str(BID_ID)


async def test_a_node_value_the_graph_does_not_have_is_refused_on_the_way_out() -> None:
    """The column is `text` with no check constraint, so the closed set is enforced here."""
    # Arrange
    source = FakeConnectionSource([node_row(node="chat_with_the_bidder")])

    # Act & Assert
    with pytest.raises(ValidationError):
        await fetch_usage_by_node(source, company_id=COMPANY_ID)


async def test_a_provider_nothing_in_this_package_writes_is_refused_too() -> None:
    # Arrange
    source = FakeConnectionSource([node_row(provider="some-reseller")])

    # Act & Assert
    with pytest.raises(ValidationError):
        await fetch_usage_by_node(source, company_id=COMPANY_ID)


async def test_the_bid_list_carries_the_id_and_when_it_last_spent() -> None:
    # Arrange
    source = FakeConnectionSource([bid_row()])

    # Act
    lines = await fetch_usage_by_bid(source, company_id=COMPANY_ID)

    # Assert
    assert lines == (
        BidUsage(
            bid_id=str(BID_ID),
            last_call_at=NOW,
            calls=49,
            input_tokens=100_000,
            output_tokens=14_000,
            cost_usd=1.38,
            unpriced_calls=0,
        ),
    )
    assert source.only.params["limit"] == DEFAULT_BID_LIMIT


async def test_spend_that_belongs_to_no_bid_keeps_a_null_id() -> None:
    """The column is nullable for S5.6's non-run spend; a reader must not assume otherwise."""
    # Arrange
    source = FakeConnectionSource([bid_row(bid_id=None)])

    # Act
    [line] = await fetch_usage_by_bid(source, company_id=COMPANY_ID)

    # Assert
    assert line.bid_id is None


async def test_the_bid_list_is_bounded_by_the_limit_it_was_given() -> None:
    # Arrange
    source = FakeConnectionSource([bid_row()])

    # Act
    await fetch_usage_by_bid(source, company_id=COMPANY_ID, limit=MAX_BID_LIMIT)

    # Assert
    assert source.only.params["limit"] == MAX_BID_LIMIT


# ------------------------------------------------------------------------- the total


def test_the_total_is_the_breakdown_added_up() -> None:
    """Summed here rather than asked of the database: the breakdown is never truncated, so
    the sum is exact and cannot disagree with the lines beneath it."""
    # Arrange
    lines = (
        NodeUsage.model_validate(node_row()),
        NodeUsage.model_validate(
            node_row(model=FALLBACK_MODEL, calls=7, cost_usd=Decimal("0.145500"))
        ),
    )

    # Act
    total = totals_of(lines)

    # Assert
    assert total == UsageTotals(
        calls=49,
        input_tokens=180_000,
        output_tokens=24_000,
        cost_usd=1.38,
        unpriced_calls=0,
    )


def test_a_company_that_has_spent_nothing_totals_zero_rather_than_nothing() -> None:
    """A panel must render an empty report, not a missing one."""
    # Act
    total = totals_of([])

    # Assert
    assert total == UsageTotals(
        calls=0, input_tokens=0, output_tokens=0, cost_usd=0.0, unpriced_calls=0
    )


def test_unpriced_calls_are_carried_into_the_total_so_it_reads_as_a_lower_bound() -> None:
    # Arrange
    lines = (NodeUsage.model_validate(node_row(unpriced_calls=3)),)

    # Act & Assert
    assert totals_of(lines).unpriced_calls == 3
