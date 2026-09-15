"""S5.2 — what a model call cost, captured where no call site can forget it.

`migrations/0001_init.sql` declared `llm_usage` and nothing has ever written to it. This
module is the capture half (the write and the read live in `readmodel/usage.py`), and three
decisions are what it exists to hold.

**1. Usage is captured by a LangChain callback on the model, not by a wrapper and not by
each node reporting its own.** A wrapper is the obvious design and it cannot work here:
every expensive call in Crossbid goes through `with_structured_output(...)`, which hands the
caller a *parsed Pydantic object* — the `AIMessage` that carried the token counts and
OpenRouter's cost has already been consumed and thrown away by the time any wrapper of ours
sees the answer. `ResilientModel` is exactly such a wrapper and is blind to cost for that
reason. A callback runs one layer lower, inside `BaseChatModel.agenerate`, where the raw
`LLMResult` still exists, and it is unaffected by whatever was bound on top.

Per-node self-reporting is the design that fails silently: a node that forgets its report
costs nothing, which looks like a cheap node rather than a broken one, and the graded
number is then wrong in the direction nobody checks. So the handler is attached by
`llm.chat_model` — the one factory every role-based call goes through — and the only thing
a call site can lose is its *attribution*, never the row. An unattributed call is logged as
a warning naming the model and the tokens (`_warn_unattributed`), so missing instrumentation
is noisy rather than invisible.

**2. Attribution is ambient, because the nodes never pass a config to the model.**
`check_loop` calls `model.ainvoke(messages)` with no `RunnableConfig`, and threading one
through every binding, every `resilient` pair and every tool turn would be a large change
for a small fact. A `ContextVar` carries the scope instead: `graph.stage` opens one per node
with the bid, the tenant and the node name, and every model call made underneath — including
the ones inside `asyncio.gather`, which copy the context — is attributed to it. The scope is
opened with a context manager that `reset`s its token, so two nodes that happen to run in
the same task cannot inherit each other's attribution.

**3. The model on the row is the one that answered, read off the wire.** `llm_output`
carries `model_name` from the provider's own response body, not from our configuration. That
is what makes the `fallback` role honest: when the primary times out and `ResilientModel`
reissues against the other vendor, the row says the vendor that was actually paid, and
`/dev/costs` shows two models under one node rather than one model with a wrong total.
ADR-0050 lets an operator move a role onto a different slug mid-life, and a row keyed on
configuration would misattribute every call made before the switch.

**Cost is OpenRouter's number, never a local price table.** `llm.USAGE_ACCOUNTING_EXTRA_BODY`
asks for it (`{"usage": {"include": true}}`, verified 2026-09-10) and it arrives inside the
provider's raw `usage` object, which langchain-openai passes through untouched as
`llm_output["token_usage"]`. There is no multiplication of tokens by a rate anywhere in this
package: a rate table goes stale the day a vendor changes a price or a role is switched, and
a stale rate produces a plausible wrong number rather than an obvious missing one. When the
cost is absent, `CallUsage.cost_usd` is `None` and the caller decides — see
`readmodel/usage.py` for why the column stores zero and the report counts it.

**Embeddings are deliberately not in this table**, although they are bought from the same
provider. `llm_usage.bid_id` is what makes "cost per bid" answerable, and the only embedding
spend attached to a bid is the query vector of a RAG tool call inside `check_reqs` — a few
dozen tokens against chat calls of thousands, measured against a run that cost $1.38.
The corpus embedding happens once at upload, before any bid exists, and is not "where the
money goes" on a bid. The deciding argument is the third: whether OpenRouter returns a
`cost` on `/embeddings` at all has never been verified on this account, and rows priced at
zero because the field is missing would poison the one signal the report uses to say
"this total is incomplete" (`unpriced_calls`). `GET /dev/costs` says in its own description
that it covers chat completions.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any, Final, Protocol

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult

from crossbid.models.provider import Provider

logger = logging.getLogger(__name__)


class UsageNode(StrEnum):
    """The closed set of values `llm_usage.node` may hold: the graph's own node names.

    A `StrEnum` rather than a string at each call site, and the graph's node-name constants
    are defined *from* it (`agent/graph.py`), so the two cannot drift. That matters more
    than it looks: a renamed node under free strings would silently split one node's costs
    across two rows in the report, and nothing would fail. Here, adding a node to the graph
    does not type-check until it is named here as well — which is the moment to ask whether
    it spends money.

    Every stage is listed, not only the three that call a model today. A node that starts
    spending later is attributed the moment it does, with nobody remembering to come back.

    `CHAT` is the one member that is not a bid-graph node. "Ask the tender" runs its own
    graph against a bid the bidder is looking at, and it spends real money on a model per
    question — it was simply never given an attribution, so every chat turn landed in
    `_warn_unattributed` and `/dev/costs` understated any bid whose reviewer asked anything.
    The vocabulary is the report's, not the bid graph's; what the parity test still holds is
    the direction that matters, that no graph node may be missing from it.
    """

    PARSE_DOCS = "parse_docs"
    EXTRACT_REQS = "extract_reqs"
    PLAN_CHECKS = "plan_checks"
    CHECK_REQS = "check_reqs"
    SCORE_VERDICT = "score_verdict"
    AWAIT_REVIEW = "await_review"
    APPLY_REVIEW = "apply_review"
    FINALIZE = "finalize"
    CHAT = "chat"


OPENROUTER_COST_KEY: Final = "cost"
"""Where OpenRouter puts the price of one response inside its `usage` object. Requested by
`llm.USAGE_ACCOUNTING_EXTRA_BODY`; absent from a plain OpenAI-shaped `usage`."""

PROMPT_TOKENS_KEY: Final = "prompt_tokens"
COMPLETION_TOKENS_KEY: Final = "completion_tokens"
# ruff reads "token" in the name as a credential; it is langchain-openai's own key name.
TOKEN_USAGE_KEY: Final = "token_usage"  # noqa: S105
MODEL_NAME_KEY: Final = "model_name"
"""langchain-openai's own key names in `LLMResult.llm_output`. `token_usage` is the
provider's raw `usage` object passed through, which is why OpenRouter's extra `cost` key
survives to be read here."""


@dataclass(frozen=True, slots=True)
class CallUsage:
    """What one model response reported about itself: who answered, and what it cost.

    `cost_usd` is `None` when the provider did not price the response, which is a different
    fact from "it was free" and is kept distinct all the way to the report.
    """

    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal | None


@dataclass(frozen=True, slots=True)
class UsageEvent:
    """One `llm_usage` row, before it is a row. Frozen; the sink may not edit it."""

    company_id: str
    bid_id: str
    node: UsageNode
    provider: Provider
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal | None


class UsageSink(Protocol):
    """Where a captured event goes. `readmodel.usage.DatabaseUsageSink` is the real one.

    A Protocol so the graph can be exercised over a recorder in the unit suite without a
    Postgres, which is the same seam `RunProjection` gives the read-model writes.
    """

    async def record(self, event: UsageEvent) -> None: ...


@dataclass(frozen=True, slots=True)
class UsageRecorder:
    """A sink plus the attribution to stamp on everything captured under it.

    Frozen: a stage that reached into a shared recorder to change its node would
    re-attribute whatever else was running under the same context. A stage that needs a
    different attribution builds a new recorder, which is what `graph.stage` does once per
    node entry.

    `bid_id` is required although the column is nullable. The only spend with no bid is
    ingestion's injection review, which this story deliberately leaves unattributed (see
    `_warn_unattributed`), so a recorder without a bid is a recorder nothing can build
    rather than a case every writer has to handle.
    """

    sink: UsageSink
    company_id: str
    bid_id: str
    node: UsageNode

    async def record(self, usage: CallUsage, *, provider: Provider) -> None:
        """Hand one call's usage to the sink under this recorder's attribution."""
        await self.sink.record(
            UsageEvent(
                company_id=self.company_id,
                bid_id=self.bid_id,
                node=self.node,
                provider=provider,
                model=usage.model,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cost_usd=usage.cost_usd,
            )
        )


_CURRENT_RECORDER: ContextVar[UsageRecorder | None] = ContextVar(
    "crossbid_usage_recorder", default=None
)
"""The ambient attribution. See decision 2 in the module docstring for why it is a context
variable and not an argument."""


@contextmanager
def recording_usage(recorder: UsageRecorder) -> Iterator[UsageRecorder]:
    """Attribute every model call made inside the block to `recorder`.

    The token is `reset` rather than the variable being set back to `None`, so a nested
    scope restores its parent instead of erasing it, and two node bodies that LangGraph
    happens to await in the same task cannot inherit each other's bid.
    """
    token = _CURRENT_RECORDER.set(recorder)
    try:
        yield recorder
    finally:
        _CURRENT_RECORDER.reset(token)


def current_recorder() -> UsageRecorder | None:
    """The recorder in scope, or `None` when a call is made outside every scope."""
    return _CURRENT_RECORDER.get()


# ------------------------------------------------------------------- reading a response


def call_usage(response: LLMResult) -> CallUsage | None:
    """What `response` says it spent, or `None` when it says nothing usable.

    Both refusals are real cases rather than defensive padding. A streamed response reaches
    `on_llm_end` with `llm_output=None` (langchain-core assembles the chunks and carries no
    provider usage object), and a provider that answers without a `usage` object leaves
    nothing to read. Returning `None` rather than a zero-filled row is the same distinction
    `cost_usd` draws: no row at all is visibly missing, a row of zeroes is not.
    """
    output: Mapping[str, Any] = response.llm_output or {}
    usage = output.get(TOKEN_USAGE_KEY)
    model = output.get(MODEL_NAME_KEY)
    if not isinstance(usage, Mapping) or not isinstance(model, str) or not model.strip():
        return None
    return CallUsage(
        model=model.strip(),
        input_tokens=_token_count(usage, PROMPT_TOKENS_KEY),
        output_tokens=_token_count(usage, COMPLETION_TOKENS_KEY),
        cost_usd=_reported_cost(usage),
    )


def _token_count(usage: Mapping[str, Any], key: str) -> int:
    """One token count, or zero when the provider did not send that half.

    Zero is safe here in a way it is not for cost: the column is `integer not null` with a
    non-negative check, every OpenAI-shaped response carries both counts, and a missing
    count understates a number nobody bills on. The cost is the graded figure and it gets
    the honest `None` instead.
    """
    value = usage.get(key)
    return int(value) if isinstance(value, int | float) and value >= 0 else 0


def _reported_cost(usage: Mapping[str, Any]) -> Decimal | None:
    """OpenRouter's own price for this response, or `None` if it did not give one.

    `Decimal(str(value))` rather than `Decimal(value)`: the value arrives as a JSON float,
    and constructing a Decimal from a float preserves the binary error (0.0138 becomes
    0.01380000000000000023...), which a `numeric(12, 6)` column then rounds in its own way.
    Going through the shortest decimal string keeps the number the provider actually quoted.

    A negative price is treated as no price at all rather than stored: the column's check
    constraint would reject it, inside a callback, where the failure is swallowed.
    """
    value = usage.get(OPENROUTER_COST_KEY)
    if not isinstance(value, int | float):
        return None
    cost = Decimal(str(value))
    return None if cost < 0 else cost


# ------------------------------------------------------------------------- the handler


class UsageCallbackHandler(AsyncCallbackHandler):
    """Records every chat response against whatever scope is in context.

    Stateless, so one instance serves every model in the process; the attribution comes from
    the context variable at the moment the response lands, not from construction.

    It never raises. langchain-core logs and swallows a handler's exception, so a raise here
    would lose the row *and* look like nothing happened; catching it means the numbers reach
    the log even when the database cannot take them. That is also why a call the sink could
    not store is a warning naming the model and the tokens: the run has already been paid
    for, and the only thing left to decide is whether anyone finds out.
    """

    def __init__(self, provider: Provider = Provider.OPENROUTER) -> None:
        super().__init__()
        self._provider = provider

    async def on_llm_end(self, response: LLMResult, **_kwargs: Any) -> None:
        """Attribute one finished response, or say out loud why it could not be."""
        usage = call_usage(response)
        if usage is None:
            logger.warning(
                "a model response carried no usage object, so its cost is not recorded; "
                "check that the OpenRouter usage accounting extra body is still set"
            )
            return
        if usage.cost_usd is None:
            logger.warning(
                "'%s' answered %d+%d tokens with no cost; /dev/costs counts it as unpriced",
                usage.model,
                usage.input_tokens,
                usage.output_tokens,
            )
        recorder = current_recorder()
        if recorder is None:
            _warn_unattributed(usage)
            return
        try:
            await recorder.record(usage, provider=self._provider)
        except Exception:
            logger.exception(
                "could not store the cost of a '%s' call (%d+%d tokens, %s USD)",
                usage.model,
                usage.input_tokens,
                usage.output_tokens,
                "unpriced" if usage.cost_usd is None else usage.cost_usd,
            )


def _warn_unattributed(usage: CallUsage) -> None:
    """A call nobody claimed. Loud on purpose — see decision 1 in the module docstring.

    One real caller reaches this today: S5.3's injection review runs during document
    ingestion, which has a tenant but no bid and no graph node to be attributed to. It is
    left here rather than given a node of its own because ingestion happens before any bid
    exists and `llm_usage.bid_id` is what the report groups by, and because ADR-0049
    measured the review firing on zero of 351 real chunks — a line in the log is the right
    weight for a call that almost never happens.

    Chat used to reach here too, and that was a defect rather than a decision: it has a
    tenant *and* a bid, so it now records under `UsageNode.CHAT`. Anything else arriving
    here is missing instrumentation.
    """
    logger.warning(
        "'%s' spent %d+%d tokens (%s USD) outside any usage scope, so it is not in "
        "/dev/costs; only ingestion's injection review is expected here",
        usage.model,
        usage.input_tokens,
        usage.output_tokens,
        "unpriced" if usage.cost_usd is None else usage.cost_usd,
    )
