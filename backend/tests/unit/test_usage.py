"""S5.2 — capturing what a model call cost, offline and without a model.

Nothing here builds a `ChatOpenAI` or opens a socket: `UsageCallbackHandler` is fed the
`LLMResult` langchain-openai would hand it, which is the whole contract between this module
and the provider. The shapes used below are the real ones — `llm_output["token_usage"]` is
the provider's raw `usage` object passed through untouched, which is why OpenRouter's extra
`cost` key is in it and why `model_name` is the slug that *answered* rather than the one
that was asked (`_create_chat_result` in langchain-openai 1.6.2).

Two groups carry the story's weight. The first is that an unpriced response and a free one
stay distinguishable all the way through: `cost_usd is None` never quietly becomes zero
here. The second is that a call nobody scoped is *loud* — the design rule of this story is
that missing instrumentation must be visible, and a silent drop would make a broken node
look like a cheap one.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from decimal import Decimal

import pytest
from langchain_core.outputs import LLMResult

from crossbid.models.provider import Provider
from crossbid.usage import (
    CallUsage,
    UsageCallbackHandler,
    UsageEvent,
    UsageNode,
    UsageRecorder,
    call_usage,
    current_recorder,
    recording_usage,
)

pytestmark = pytest.mark.anyio

COMPANY_ID = str(uuid.uuid4())
BID_ID = str(uuid.uuid4())
MODEL = "openai/gpt-5.6-terra"
FALLBACK_MODEL = "google/gemini-2.5-flash"


# --------------------------------------------------------------------------------- fakes


class RecordingSink:
    """A `UsageSink` that keeps what it was handed, in order."""

    def __init__(self, *, raising: bool = False) -> None:
        self.events: list[UsageEvent] = []
        self._raising = raising

    async def record(self, event: UsageEvent) -> None:
        if self._raising:
            raise OSError("database unreachable")
        self.events.append(event)


def result(
    *,
    model: str | None = MODEL,
    prompt_tokens: object = 1_200,
    completion_tokens: object = 300,
    cost: object = 0.0138,
    usage: object | None = None,
) -> LLMResult:
    """The `LLMResult` `on_llm_end` receives, in langchain-openai's real shape.

    `usage=...` replaces the whole `token_usage` object, which is how the tests build the
    two responses a provider can really send: one with no usage object at all, and one
    whose usage object is not a mapping.
    """
    token_usage: object = usage
    if usage is None:
        token_usage = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost": cost,
        }
    output: dict[str, object] = {"token_usage": token_usage}
    if model is not None:
        output["model_name"] = model
    return LLMResult(generations=[], llm_output=output)


def recorder(sink: RecordingSink, node: UsageNode = UsageNode.EXTRACT_REQS) -> UsageRecorder:
    return UsageRecorder(sink=sink, company_id=COMPANY_ID, bid_id=BID_ID, node=node)


# ------------------------------------------------------------- reading a model response


def test_it_reads_the_tokens_and_the_cost_the_provider_reported() -> None:
    # Act
    usage = call_usage(result())

    # Assert
    assert usage == CallUsage(
        model=MODEL, input_tokens=1_200, output_tokens=300, cost_usd=Decimal("0.0138")
    )


def test_the_model_is_the_one_that_answered_not_the_one_configured() -> None:
    """The `fallback` role means the slug on the row is only right if it comes off the wire."""
    # Act
    usage = call_usage(result(model=FALLBACK_MODEL))

    # Assert
    assert usage is not None
    assert usage.model == FALLBACK_MODEL


def test_the_cost_keeps_the_decimal_the_provider_quoted() -> None:
    """Through `str`, never `Decimal(float)`, or 0.0138 becomes 0.01380000000000000023..."""
    # Act
    usage = call_usage(result(cost=0.0138))

    # Assert
    assert usage is not None
    assert str(usage.cost_usd) == "0.0138"


@pytest.mark.parametrize(
    "response",
    [
        LLMResult(generations=[], llm_output=None),
        result(usage="none"),
        result(model=None),
        result(model="   "),
    ],
    ids=["streamed, no llm_output", "usage is not an object", "no model name", "blank model"],
)
def test_a_response_with_nothing_usable_reports_nothing(response: LLMResult) -> None:
    """`None` rather than a row of zeroes: a missing row is visible, a zero row is not."""
    # Act & Assert
    assert call_usage(response) is None


@pytest.mark.parametrize(
    ("cost", "expected"),
    [
        (None, None),
        ("0.0138", None),
        (-1.0, None),
        (0, Decimal("0")),
        (2, Decimal("2")),
    ],
    ids=["absent", "a string", "negative", "integer zero", "integer"],
)
def test_an_unusable_cost_is_no_cost_rather_than_zero(cost: object, expected: object) -> None:
    """Zero would be stored as a price. `None` is stored as unpriced and counted as such."""
    # Act
    usage = call_usage(result(cost=cost))

    # Assert
    assert usage is not None
    assert usage.cost_usd == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, 0), ("many", 0), (-5, 0), (17.0, 17)],
    ids=["absent", "not a number", "negative", "a float"],
)
def test_a_token_count_that_is_not_a_count_is_zero(value: object, expected: int) -> None:
    """Safe here in a way it is not for cost: nobody is billed on our copy of the count."""
    # Act
    usage = call_usage(result(prompt_tokens=value, completion_tokens=value))

    # Assert
    assert usage is not None
    assert (usage.input_tokens, usage.output_tokens) == (expected, expected)


# ------------------------------------------------------------------------ the ambient scope


def test_there_is_no_recorder_outside_every_scope() -> None:
    assert current_recorder() is None


def test_a_scope_is_restored_rather_than_erased_when_it_closes() -> None:
    """Nested scopes must restore the parent, or a fan-out would lose its own attribution."""
    # Arrange
    sink = RecordingSink()
    outer = recorder(sink, UsageNode.PARSE_DOCS)
    inner = recorder(sink, UsageNode.CHECK_REQS)

    # Act & Assert
    with recording_usage(outer):
        assert current_recorder() is outer
        with recording_usage(inner):
            assert current_recorder() is inner
        assert current_recorder() is outer
    assert current_recorder() is None


async def test_a_scope_reaches_the_tasks_opened_inside_it() -> None:
    """Extraction fans its sections out with `gather`; a task copies the context it was
    created in, which is what makes an ambient scope work at all."""
    # Arrange
    sink = RecordingSink()
    scope = recorder(sink)

    async def seen() -> UsageRecorder | None:
        return current_recorder()

    # Act
    with recording_usage(scope):
        found = await asyncio.gather(seen(), seen())

    # Assert
    assert found == [scope, scope]


async def test_a_recorder_stamps_its_own_attribution_on_the_event() -> None:
    # Arrange
    sink = RecordingSink()
    scope = recorder(sink, UsageNode.CHECK_REQS)
    usage = CallUsage(
        model=MODEL, input_tokens=10, output_tokens=2, cost_usd=Decimal("0.000123")
    )

    # Act
    await scope.record(usage, provider=Provider.OPENROUTER)

    # Assert
    assert sink.events == [
        UsageEvent(
            company_id=COMPANY_ID,
            bid_id=BID_ID,
            node=UsageNode.CHECK_REQS,
            provider=Provider.OPENROUTER,
            model=MODEL,
            input_tokens=10,
            output_tokens=2,
            cost_usd=Decimal("0.000123"),
        )
    ]


# ----------------------------------------------------------------------------- the handler


async def test_a_finished_response_is_recorded_against_the_scope_in_force() -> None:
    # Arrange
    sink = RecordingSink()

    # Act
    with recording_usage(recorder(sink, UsageNode.EXTRACT_REQS)):
        await UsageCallbackHandler().on_llm_end(result())

    # Assert
    [event] = sink.events
    assert (event.node, event.bid_id, event.model) == (
        UsageNode.EXTRACT_REQS,
        BID_ID,
        MODEL,
    )
    assert event.cost_usd == Decimal("0.0138")


async def test_an_unpriced_response_is_still_recorded_and_said_out_loud(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The row keeps its tokens and `None` for the cost; the log says which model did it."""
    # Arrange
    sink = RecordingSink()

    # Act
    with (
        caplog.at_level(logging.WARNING, logger="crossbid.usage"),
        recording_usage(recorder(sink)),
    ):
        await UsageCallbackHandler().on_llm_end(result(cost=None))

    # Assert
    [event] = sink.events
    assert event.cost_usd is None
    assert "unpriced" in caplog.text and MODEL in caplog.text


async def test_a_response_with_no_usage_object_is_reported_and_not_recorded(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Arrange
    sink = RecordingSink()

    # Act
    with (
        caplog.at_level(logging.WARNING, logger="crossbid.usage"),
        recording_usage(recorder(sink)),
    ):
        await UsageCallbackHandler().on_llm_end(LLMResult(generations=[]))

    # Assert
    assert sink.events == []
    assert "usage accounting" in caplog.text


async def test_a_call_nobody_scoped_is_a_warning_naming_the_model_and_the_tokens(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The design rule of this story: missing instrumentation is noisy, never invisible."""
    # Act
    with caplog.at_level(logging.WARNING, logger="crossbid.usage"):
        await UsageCallbackHandler().on_llm_end(result())

    # Assert
    assert current_recorder() is None
    assert "outside any usage scope" in caplog.text
    assert MODEL in caplog.text
    assert "1200" in caplog.text


async def test_a_sink_that_cannot_store_the_row_logs_the_numbers_it_lost(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The call is already paid for. Raising would lose the row *and* look like nothing
    happened, because langchain swallows a handler's exception."""
    # Arrange
    sink = RecordingSink(raising=True)

    # Act
    with (
        caplog.at_level(logging.ERROR, logger="crossbid.usage"),
        recording_usage(recorder(sink)),
    ):
        await UsageCallbackHandler().on_llm_end(result())

    # Assert -- no exception escaped, and the cost reached the log instead of the table
    [record] = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert "could not store the cost" in record.getMessage()
    assert record.exc_info is not None


async def test_an_unpriced_lost_row_says_unpriced_rather_than_none(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Both failure messages render the missing cost as a word, not as `None`."""
    # Act
    with caplog.at_level(logging.WARNING, logger="crossbid.usage"):
        with recording_usage(recorder(RecordingSink(raising=True))):
            await UsageCallbackHandler().on_llm_end(result(cost=None))
        await UsageCallbackHandler().on_llm_end(result(cost=None))

    # Assert
    assert "unpriced USD" in caplog.text


# ----------------------------------------------------------------- the vocabulary itself


def test_every_node_value_is_the_graph_node_name_it_stands_for() -> None:
    """`llm_usage.node` is free text; the enum is what keeps it joinable to a trace."""
    from crossbid.agent import graph as graph_module

    names = {
        graph_module.PARSE_DOCS,
        graph_module.EXTRACT_REQS,
        graph_module.PLAN_CHECKS,
        graph_module.CHECK_REQS,
        graph_module.SCORE_VERDICT,
        graph_module.AWAIT_REVIEW,
        graph_module.APPLY_REVIEW,
        graph_module.FINALIZE,
    }
    assert {node.value for node in UsageNode} == names
