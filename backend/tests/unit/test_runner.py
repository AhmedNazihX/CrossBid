"""S3.1.1 — background runs: tracked, recorded when they crash, resumed after a restart.

Offline. Every run goes through the real `build_graph` over fake nodes and a `MemorySaver`,
so the runner is tested against LangGraph's real resume semantics (`ainvoke(None)` on a
thread with a checkpoint continues; on an empty thread it would raise) rather than a mock
of them. The read model is replaced at the two functions the runner calls.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver

from crossbid.agent import runner as runner_module
from crossbid.agent.graph import AWAIT_REVIEW, StageError, build_graph
from crossbid.agent.runner import (
    DEFAULT_RUN_BUDGET_SECONDS,
    DEFAULT_RUN_BUDGET_USD,
    BidRunner,
    RunBudget,
    RunnerError,
    build_runner,
    failure_reason_of,
    resume_unfinished_runs,
)
from crossbid.agent.state import BidState
from crossbid.ingestion.storage import StorageError
from crossbid.models.review import ReviewSubmission
from crossbid.models.tender import BidStatus
from crossbid.models.verdict import Decision, Verdict
from crossbid.readmodel.bids import BidRow, thread_id_of
from crossbid.readmodel.usage import SELECT_USAGE_BY_NODE
from crossbid.settings import Settings, bid_run_config
from tests.conftest import FakeConnectionSource

pytestmark = pytest.mark.anyio

COMPANY_ID = str(uuid.uuid4())


# --------------------------------------------------------------------------------- fakes


def bid_row(bid_id: str | None = None, **overrides: Any) -> BidRow:
    identifier = bid_id or str(uuid.uuid4())
    values: dict[str, Any] = {
        "id": identifier,
        "company_id": COMPANY_ID,
        "thread_id": thread_id_of(identifier),
        "notice_number": "614251-2026",
        "title": "Netztechnik",
        "source_language": "de",
        "bidder_language": "de",
        "status": BidStatus.QUEUED,
    }
    return BidRow(**(values | overrides))


WAIT_TIMEOUT_S = 5.0
"""Long enough for a scheduled coroutine to start; short enough that a guard that never
releases fails the suite instead of hanging it."""


class RecordingProjection:
    def __init__(self) -> None:
        self.statuses: list[BidStatus] = []
        self.reviews: list[dict[str, Any]] = []

    async def set_status(self, *, company_id: str, bid_id: str, status: BidStatus) -> None:
        self.statuses.append(status)

    async def set_problems(self, *, company_id: str, bid_id: str, problems: Any) -> None:
        pass

    async def write_requirements(self, *, company_id: str, rows: Any) -> int:
        return len(rows)

    async def write_matrix_rows(self, *, company_id: str, bid_id: str, rows: Any) -> int:
        return len(rows)

    async def set_verdict(self, *, company_id: str, bid_id: str, verdict: Any) -> None:
        pass

    async def write_reviewed_rows(self, *, company_id: str, bid_id: str, rows: Any) -> int:
        return len(rows)

    async def record_review(self, *, company_id: str, bid_id: str, **record: Any) -> None:
        self.reviews.append(record)


USAGE_ROWS: tuple[dict[str, Any], ...] = (
    {
        "node": "check_reqs",
        "provider": "openrouter",
        "model": "openai/gpt-5.6-terra",
        "calls": 49,
        "input_tokens": 100_000,
        "output_tokens": 14_000,
        "cost_usd": Decimal("1.380000"),
        "unpriced_calls": 0,
    },
)
"""What `llm_usage` holds after the measured DE pack run: $1.38 over 49 calls."""


class FakeDatabase:
    """The checkpointer, plus the one connection the runner now borrows.

    S5.2 made the runner a *reader*: when a run stops it sums the bid's `llm_usage` rows and
    compares the total with `budget.usd`. The lent connection answers `rows` for whatever it
    is asked, and `usage.log` is what the tests assert against -- the runner must borrow for
    the cost read and for nothing else, which is what the old `raise` here used to say.
    """

    def __init__(self, rows: Any = USAGE_ROWS) -> None:
        self.checkpointer = MemorySaver()
        self.usage = FakeConnectionSource(rows)

    def connection(self) -> Any:
        return self.usage.connection()


async def quiet_parse(state: BidState, config: RunnableConfig | None = None) -> Any:
    return {"documents": [], "extraction_problems": []}


async def quiet_plan(state: BidState, config: RunnableConfig | None = None) -> Any:
    """Stands in for `plan_checks`, which would otherwise read the companies table."""
    return {"bidder_country": "de"}


async def quiet_extract(state: BidState, config: RunnableConfig | None = None) -> Any:
    return {"requirements": [], "extraction_problems": []}


async def crashing(state: BidState, config: RunnableConfig | None = None) -> Any:
    raise RuntimeError("boom")


def hanging_node(started: asyncio.Event) -> Any:
    async def hang(state: BidState, config: RunnableConfig | None = None) -> Any:
        started.set()
        await asyncio.Event().wait()  # never set: only cancellation ends this

    return hang


async def quiet_check(state: BidState, config: RunnableConfig | None = None) -> Any:
    return {"matrix_rows": []}


async def quiet_score(state: BidState, config: RunnableConfig | None = None) -> Any:
    """Stands in for `score_verdict`, which would otherwise read the companies table."""
    return {
        "verdict": Verdict(
            decision=Decision.INSUFFICIENT_EVIDENCE,
            rationale="nothing was extracted",
            mandatory_total=0,
            mandatory_supported=0,
            partially_supported_rows=0,
        )
    }


async def quiet_apply(state: BidState, config: RunnableConfig | None = None) -> Any:
    """Stands in for `apply_review`, which would otherwise read the companies table."""
    return {
        "agent_verdict": state.get("verdict"),
        "verdict": Verdict(
            decision=Decision.INSUFFICIENT_EVIDENCE,
            rationale="re-scored on the reviewer's statuses",
            mandatory_total=0,
            mandatory_supported=0,
            partially_supported_rows=0,
        ),
    }


def graph_over(
    settings: Settings,
    saver: MemorySaver,
    projection: RecordingProjection,
    *,
    parse: Any = quiet_parse,
    extract: Any = quiet_extract,
    apply: Any = quiet_apply,
) -> Any:
    """The real wiring, with every node that would reach a database or a model replaced.

    `quiet_extract` finds no requirements, so the checking fan-out emits no `Send` and
    `check_reqs` is never reached; it is injected anyway so that a future change to that
    edge cannot quietly build the real, model-calling node in a unit test.
    """
    return build_graph(
        settings,
        FakeDatabase(),  # type: ignore[arg-type]
        parse_docs=parse,
        extract_reqs=extract,
        plan_checks=quiet_plan,
        check_reqs=quiet_check,
        score_verdict=quiet_score,
        apply_review=apply,
        projection=projection,
        checkpointer=saver,
    )


class FailureRecorder:
    """Replaces `readmodel.bids.mark_bid_failed` for the runner."""

    def __init__(self, *, raising: bool = False) -> None:
        self.calls: list[tuple[str, str, str]] = []
        self._raising = raising

    async def __call__(self, db: Any, *, company_id: str, bid_id: str, reason: str) -> None:
        if self._raising:
            raise OSError("database unreachable")
        self.calls.append((company_id, bid_id, reason))


@pytest.fixture
def failures(monkeypatch: pytest.MonkeyPatch) -> FailureRecorder:
    recorder = FailureRecorder()
    monkeypatch.setattr(runner_module, "mark_bid_failed", recorder)
    return recorder


def runner_for(graph: Any, *, db: Any = None, **kwargs: Any) -> BidRunner:
    return BidRunner(lambda: graph, db if db is not None else FakeDatabase(), **kwargs)


# ---------------------------------------------------------------------------- starting


async def test_start_runs_the_graph_in_the_background_and_tracks_the_task(
    offline_settings: Settings, failures: FailureRecorder
) -> None:
    # Arrange
    projection = RecordingProjection()
    saver = MemorySaver()
    runner = runner_for(graph_over(offline_settings, saver, projection))
    bid = bid_row()

    # Act
    task = runner.start(bid)

    # Assert -- scheduled, not run: nothing has been written when `start` returns
    assert runner.running == {bid.id}
    assert projection.statuses == []
    await task
    assert runner.running == frozenset()
    assert projection.statuses == [
        BidStatus.PARSING,
        BidStatus.EXTRACTING,
        BidStatus.CHECKING,
        BidStatus.SCORING,
        BidStatus.AWAITING_REVIEW,
    ]
    snapshot = await runner.graph.aget_state(bid_run_config(bid.id, thread_id=bid.thread_id))
    assert snapshot.next == (AWAIT_REVIEW,)
    assert failures.calls == []


async def test_starting_a_bid_that_is_already_running_is_refused(
    offline_settings: Settings, failures: FailureRecorder
) -> None:
    runner = runner_for(graph_over(offline_settings, MemorySaver(), RecordingProjection()))
    bid = bid_row()
    task = runner.start(bid)

    with pytest.raises(RunnerError, match=bid.id):
        runner.start(bid)

    await task


async def test_the_task_is_named_after_the_bid(
    offline_settings: Settings, failures: FailureRecorder
) -> None:
    """`asyncio` task names show up in debug dumps; a bid id there beats `Task-17`."""
    runner = runner_for(graph_over(offline_settings, MemorySaver(), RecordingProjection()))
    bid = bid_row()

    task = runner.start(bid)

    assert task.get_name() == f"bid-run:{bid.id}"
    await task


# ------------------------------------------------------------------------- what it cost


class UnreadableDatabase(FakeDatabase):
    """A pool that cannot lend a connection, so the cost read fails after the run does not."""

    def connection(self) -> Any:
        raise OSError("database unreachable")


async def test_a_parked_run_reports_what_it_bought(
    offline_settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    """S5.2's budget half: the figure is summed from `llm_usage`, not measured in flight,
    so a resumed run reports the whole bid rather than the slice this process watched."""
    # Arrange
    db = FakeDatabase()
    runner = runner_for(
        graph_over(offline_settings, MemorySaver(), RecordingProjection()), db=db
    )
    bid = bid_row()

    # Act
    with caplog.at_level(logging.INFO, logger="crossbid.agent.runner"):
        await runner.start(bid)

    # Assert -- one borrow, for the per-node read, scoped to this bid
    statement = db.usage.only
    assert statement.sql == SELECT_USAGE_BY_NODE
    assert statement.params == {"company_id": COMPANY_ID, "bid_id": bid.id}
    assert f"Bid {bid.id}: run cost $1.3800 (49 call(s), 114000 tokens, 0 unpriced)" in (
        caplog.text
    )


async def test_a_run_over_the_dollar_budget_is_a_warning_naming_both_numbers(
    offline_settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    """The story's second limit. $2.50 is what the plan holds a DE-pack run to."""
    # Arrange
    dear = [dict(USAGE_ROWS[0]) | {"cost_usd": Decimal("3.500000"), "unpriced_calls": 2}]
    runner = runner_for(
        graph_over(offline_settings, MemorySaver(), RecordingProjection()),
        db=FakeDatabase(dear),
    )
    bid = bid_row()

    # Act
    with caplog.at_level(logging.WARNING, logger="crossbid.agent.runner"):
        await runner.start(bid)

    # Assert
    [record] = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert record.getMessage() == (
        f"Bid {bid.id}: run cost $3.5000, over the $2.50 budget "
        "(49 call(s), 114000 tokens, 2 unpriced)"
    )


async def test_a_crashed_run_still_reports_what_it_had_already_bought(
    offline_settings: Settings, failures: FailureRecorder, caplog: pytest.LogCaptureFixture
) -> None:
    """A run that died in `check_reqs` has spent most of what a finished one would, and is
    the run whose bill somebody most wants to see."""
    # Arrange
    runner = runner_for(
        graph_over(offline_settings, MemorySaver(), RecordingProjection(), extract=crashing)
    )
    bid = bid_row()

    # Act
    with caplog.at_level(logging.INFO, logger="crossbid.agent.runner"):
        await runner.start(bid)

    # Assert
    assert failures.calls == [(COMPANY_ID, bid.id, "extracting failed: RuntimeError")]
    assert f"Bid {bid.id}: run cost $1.3800" in caplog.text


async def test_a_cost_read_that_fails_is_logged_and_changes_nothing_else(
    offline_settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    """The run is over and its status is written; refusing to finish the task over a cost
    report would trade a number for a state machine."""
    # Arrange
    runner = runner_for(
        graph_over(offline_settings, MemorySaver(), RecordingProjection()),
        db=UnreadableDatabase(),
    )
    bid = bid_row()

    # Act
    with caplog.at_level(logging.ERROR, logger="crossbid.agent.runner"):
        await runner.start(bid)

    # Assert
    [record] = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert record.getMessage() == f"Bid {bid.id}: could not read what the run cost"
    assert record.exc_info is not None
    assert runner.running == frozenset()


# ---------------------------------------------------------------------------- crashing


async def test_a_crash_marks_the_bid_failed_with_a_readable_reason_and_is_logged(
    offline_settings: Settings, failures: FailureRecorder, caplog: pytest.LogCaptureFixture
) -> None:
    projection = RecordingProjection()
    graph = graph_over(offline_settings, MemorySaver(), projection, extract=crashing)
    runner = runner_for(graph)
    bid = bid_row()

    with caplog.at_level(logging.ERROR, logger="crossbid.agent.runner"):
        await runner.start(bid)

    # Assert -- the task did not raise, the row was marked, and the traceback was logged
    assert failures.calls == [(COMPANY_ID, bid.id, "extracting failed: RuntimeError")]
    assert projection.statuses == [BidStatus.PARSING, BidStatus.EXTRACTING]
    [record] = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert record.getMessage() == f"Bid {bid.id}: extracting failed: RuntimeError"
    assert record.exc_info is not None, "the traceback must reach the log"
    assert runner.running == frozenset()


async def test_a_failure_the_read_model_cannot_record_is_still_logged(
    offline_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(runner_module, "mark_bid_failed", FailureRecorder(raising=True))
    graph = graph_over(offline_settings, MemorySaver(), RecordingProjection(), extract=crashing)
    runner = runner_for(graph)
    bid = bid_row()

    with caplog.at_level(logging.ERROR, logger="crossbid.agent.runner"):
        await runner.start(bid)

    messages = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert messages == [
        f"Bid {bid.id}: extracting failed: RuntimeError",
        f"Bid {bid.id}: could not record the failure 'extracting failed: RuntimeError'",
    ]


def test_failure_reason_of_names_a_plain_exception_by_type_only() -> None:
    assert failure_reason_of(ValueError("bid abc has no documents")) == "run failed: ValueError"


# ---------------------------------------------------------------------------- resuming


async def test_resume_continues_from_the_checkpoint_after_a_crash(
    offline_settings: Settings, failures: FailureRecorder, caplog: pytest.LogCaptureFixture
) -> None:
    """The restart criterion, offline: parse is not repeated, extraction is, the run parks."""
    saver = MemorySaver()
    bid = bid_row()
    broken = runner_for(
        graph_over(offline_settings, saver, RecordingProjection(), extract=crashing)
    )
    await broken.start(bid)
    assert failures.calls[0][2] == "extracting failed: RuntimeError"

    # Act -- "after the restart": a new runner and graph over the same saver
    projection = RecordingProjection()
    repaired = runner_for(graph_over(offline_settings, saver, projection))
    with caplog.at_level(logging.INFO, logger="crossbid.agent.runner"):
        await repaired.resume(bid_row(bid.id, status=BidStatus.EXTRACTING))

    # Assert
    assert projection.statuses == [
        BidStatus.EXTRACTING,
        BidStatus.CHECKING,
        BidStatus.SCORING,
        BidStatus.AWAITING_REVIEW,
    ]
    assert any("resuming from checkpoint" in r.getMessage() for r in caplog.records)


async def test_resume_without_a_checkpoint_starts_from_the_row(
    offline_settings: Settings, failures: FailureRecorder, caplog: pytest.LogCaptureFixture
) -> None:
    """A bid created just before the process died has a row and no checkpoint; `ainvoke(None)`
    on that thread would raise `EmptyInputError`, so the runner starts it properly."""
    projection = RecordingProjection()
    runner = runner_for(graph_over(offline_settings, MemorySaver(), projection))

    with caplog.at_level(logging.INFO, logger="crossbid.agent.runner"):
        await runner.resume(bid_row())

    assert projection.statuses[0] is BidStatus.PARSING
    assert projection.statuses[-1] is BidStatus.AWAITING_REVIEW
    assert any("no checkpoint yet" in r.getMessage() for r in caplog.records)
    assert failures.calls == []


# ---------------------------------------------------------------------------- shutdown


async def test_shutdown_cancels_runs_in_flight(
    offline_settings: Settings, failures: FailureRecorder, caplog: pytest.LogCaptureFixture
) -> None:
    started = asyncio.Event()
    projection = RecordingProjection()
    graph = graph_over(offline_settings, MemorySaver(), projection, parse=hanging_node(started))
    runner = runner_for(graph)
    bid = bid_row()
    task = runner.start(bid)
    await started.wait()

    # Act
    with caplog.at_level(logging.INFO, logger="crossbid.agent.runner"):
        await runner.shutdown()

    # Assert -- cancelled, not failed: the bid stays `parsing` for the next start to resume
    assert task.cancelled()
    assert runner.running == frozenset()
    assert failures.calls == []
    assert projection.statuses == [BidStatus.PARSING]
    messages = [r.getMessage() for r in caplog.records]
    assert f"Bid {bid.id}: run cancelled; it resumes from its checkpoint" in messages
    assert "cancelled 1 bid run(s) on shutdown" in messages


async def test_shutdown_with_nothing_running_is_quiet(
    offline_settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    runner = runner_for(graph_over(offline_settings, MemorySaver(), RecordingProjection()))

    with caplog.at_level(logging.INFO, logger="crossbid.agent.runner"):
        await runner.shutdown()

    assert caplog.records == []


# ---------------------------------------------------------------------------- the budget


async def test_a_run_over_the_time_budget_is_a_warning(
    offline_settings: Settings, failures: FailureRecorder, caplog: pytest.LogCaptureFixture
) -> None:
    ticks = iter((0.0, 1_000.0))
    runner = runner_for(
        graph_over(offline_settings, MemorySaver(), RecordingProjection()),
        budget=RunBudget(seconds=600.0),
        clock=lambda: next(ticks),
    )
    bid = bid_row()

    with caplog.at_level(logging.INFO, logger="crossbid.agent.runner"):
        await runner.start(bid)

    [warning] = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warning.getMessage() == f"Bid {bid.id}: run took 1000s, over the 600s budget"


async def test_a_run_within_the_time_budget_is_reported_as_parked(
    offline_settings: Settings, failures: FailureRecorder, caplog: pytest.LogCaptureFixture
) -> None:
    ticks = iter((0.0, 42.0))
    runner = runner_for(
        graph_over(offline_settings, MemorySaver(), RecordingProjection()),
        clock=lambda: next(ticks),
    )
    bid = bid_row()

    with caplog.at_level(logging.INFO, logger="crossbid.agent.runner"):
        await runner.start(bid)

    assert not [r for r in caplog.records if r.levelno == logging.WARNING]
    assert f"Bid {bid.id}: run parked after 42s" in [r.getMessage() for r in caplog.records]


def test_run_budget_defaults_are_the_story_limits() -> None:
    assert RunBudget() == RunBudget(seconds=600.0, usd=2.50)
    assert DEFAULT_RUN_BUDGET_SECONDS == 600.0
    assert DEFAULT_RUN_BUDGET_USD == 2.50


def test_run_budget_reads_the_shipped_defaults(offline_settings: Settings) -> None:
    """`settings.default.yaml` carries the story's two limits, so settings and code agree."""
    assert RunBudget.from_settings(offline_settings) == RunBudget()


def test_run_budget_reads_the_settings_keys_once_they_exist() -> None:
    settings = SimpleNamespace(
        runtime=SimpleNamespace(agent=SimpleNamespace(run_budget_seconds=30, run_budget_usd=1))
    )

    budget = RunBudget.from_settings(settings)  # type: ignore[arg-type]

    assert budget == RunBudget(seconds=30.0, usd=1.0)


# ------------------------------------------------------------------ the production wiring


def test_build_runner_builds_the_real_graph_lazily(offline_settings: Settings) -> None:
    """Construction touches nothing; the first `.graph` runs `build_graph`, which without
    Storage configured refuses -- proof that it is the real factory and that it is lazy."""
    runner = build_runner(FakeDatabase(), lambda: offline_settings)  # type: ignore[arg-type]

    assert runner.running == frozenset()
    assert runner.budget == RunBudget()
    with pytest.raises(StorageError, match="SUPABASE_URL"):
        runner.graph  # noqa: B018 -- the access is the act


# ------------------------------------------------- S4.6.2: the graph follows the settings


def settings_at(settings: Settings, temperature: float) -> Settings:
    runtime = settings.runtime.model_copy(update={"temperature": temperature})
    return Settings(env=settings.env, runtime=runtime)


def test_the_factory_reads_the_settings_in_force_on_every_build(
    offline_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The failure this closes: a factory that captured `Settings` at boot would run every
    later bid on them while the panel reported the change as applied. The provider is
    called per build, so a build after `invalidate_graph()` sees what the panel stored."""
    # Arrange
    built_with: list[float] = []
    monkeypatch.setattr(
        runner_module,
        "build_graph",
        lambda settings, db: built_with.append(settings.runtime.temperature) or object(),
    )
    current = {"settings": settings_at(offline_settings, 0.0)}
    runner = build_runner(FakeDatabase(), lambda: current["settings"])  # type: ignore[arg-type]

    # Act
    first = runner.graph
    current["settings"] = settings_at(offline_settings, 0.7)
    still_cached = runner.graph
    runner.invalidate_graph()
    rebuilt = runner.graph

    # Assert
    assert still_cached is first, "no rebuild until told: an in-flight run keeps its graph"
    assert rebuilt is not first
    assert built_with == [0.0, 0.7]


def test_invalidating_before_any_build_is_harmless() -> None:
    """A settings write on a process whose runner has not built yet must not build one."""

    def factory() -> Any:
        raise AssertionError("invalidation must not build the graph")

    runner = BidRunner(factory, FakeDatabase())

    runner.invalidate_graph()

    assert runner.running == frozenset()


async def test_resume_unfinished_runs_schedules_every_unfinished_bid(
    offline_settings: Settings,
    failures: FailureRecorder,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    rows = [bid_row(status=BidStatus.PARSING), bid_row(status=BidStatus.QUEUED)]

    async def unfinished_bids(db: Any) -> list[BidRow]:
        return rows

    monkeypatch.setattr(runner_module, "unfinished_bids", unfinished_bids)
    projection = RecordingProjection()
    runner = runner_for(graph_over(offline_settings, MemorySaver(), projection))

    # Act
    with caplog.at_level(logging.INFO, logger="crossbid.agent.runner"):
        returned = await resume_unfinished_runs(
            FakeDatabase(),  # type: ignore[arg-type]
            lambda: offline_settings,
            runner=runner,
        )

    # Assert
    assert returned is runner
    assert runner.running == {row.id for row in rows}
    assert "resuming 2 unfinished bid run(s)" in [r.getMessage() for r in caplog.records]
    await asyncio.gather(*[runner._tasks[row.id] for row in rows])
    assert projection.statuses.count(BidStatus.AWAITING_REVIEW) == 2


async def test_resume_unfinished_runs_with_nothing_to_do_does_not_build_the_graph(
    offline_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A process with no Storage and no unfinished bids must still start."""

    async def unfinished_bids(db: Any) -> list[BidRow]:
        return []

    def factory() -> Any:
        raise AssertionError("the graph must not be built with nothing to resume")

    monkeypatch.setattr(runner_module, "unfinished_bids", unfinished_bids)
    runner = BidRunner(factory, FakeDatabase())

    with caplog.at_level(logging.INFO, logger="crossbid.agent.runner"):
        returned = await resume_unfinished_runs(
            FakeDatabase(),  # type: ignore[arg-type]
            lambda: offline_settings,
            runner=runner,
        )

    assert returned is runner
    assert "no unfinished bid runs to resume" in [r.getMessage() for r in caplog.records]


async def test_resume_unfinished_runs_builds_a_runner_when_none_is_given(
    offline_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def unfinished_bids(db: Any) -> list[BidRow]:
        return []

    monkeypatch.setattr(runner_module, "unfinished_bids", unfinished_bids)

    returned = await resume_unfinished_runs(FakeDatabase(), lambda: offline_settings)  # type: ignore[arg-type]

    assert isinstance(returned, BidRunner)


async def test_resume_unfinished_runs_stops_startup_when_the_graph_cannot_be_built(
    offline_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With bids to resume and Storage unset, the API must not start (ADR-0010), and the
    bids must not be failed for what is a configuration gap."""

    async def unfinished_bids(db: Any) -> list[BidRow]:
        return [bid_row(status=BidStatus.PARSING)]

    def factory() -> Any:
        raise StorageError("SUPABASE_URL is not set")

    monkeypatch.setattr(runner_module, "unfinished_bids", unfinished_bids)
    runner = BidRunner(factory, FakeDatabase())

    with pytest.raises(StorageError):
        await resume_unfinished_runs(
            FakeDatabase(),  # type: ignore[arg-type]
            lambda: offline_settings,
            runner=runner,
        )

    assert runner.running == frozenset()


# ---------------------------------------------------------------------- submitting a review


REVIEW = ReviewSubmission(decision=Decision.INSUFFICIENT_EVIDENCE)


async def test_submit_review_resumes_the_parked_run_and_waits_for_it(
    offline_settings: Settings, failures: FailureRecorder
) -> None:
    """Inline rather than a background task: the reviewer sees the consequence of their own
    click in the same request, because nothing past the interrupt calls a model."""
    # Arrange
    saver = MemorySaver()
    projection = RecordingProjection()
    runner = runner_for(graph_over(offline_settings, saver, projection))
    bid = bid_row()
    await runner.start(bid)
    assert projection.statuses[-1] is BidStatus.AWAITING_REVIEW

    # Act
    await runner.submit_review(bid, REVIEW)

    # Assert
    assert projection.statuses[-2:] == [BidStatus.APPLYING_REVIEW, BidStatus.COMPLETE]
    assert len(projection.reviews) == 1
    assert projection.reviews[0]["decision"] is Decision.INSUFFICIENT_EVIDENCE
    assert failures.calls == []
    # Nothing was scheduled: the registry is for background runs, and this was not one.
    assert runner.running == frozenset()


async def test_a_failed_review_goes_back_to_awaiting_review_not_to_failed(
    offline_settings: Settings,
    releases: ReleaseRecorder,
    failures: FailureRecorder,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`failed` is terminal and every recovery path refuses it — the startup resume skips it
    and the claim only accepts `awaiting_review` — so a transient failure there would strand
    the bid for good with the reviewer's submission already in its checkpoint."""
    # Arrange
    saver = MemorySaver()
    runner = runner_for(
        graph_over(offline_settings, saver, RecordingProjection(), apply=crashing)
    )
    bid = bid_row()
    await runner.start(bid)

    # Act / Assert
    with (
        caplog.at_level(logging.ERROR, logger="crossbid.agent.runner"),
        pytest.raises(StageError, match="applying_review failed: RuntimeError"),
    ):
        await runner.submit_review(bid, REVIEW)

    assert releases.calls[-1][1:] == (bid.id, "applying_review failed: RuntimeError")
    assert failures.calls == []


async def test_a_release_that_itself_fails_is_logged_rather_than_masking_the_review_error(
    offline_settings: Settings,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reviewer has to learn the review failed; the log is where a failed repair goes."""

    # Arrange
    async def broken(db: Any, **kwargs: Any) -> None:
        raise OSError("database unreachable")

    monkeypatch.setattr(runner_module, "release_bid_to_review", broken)
    runner = runner_for(
        graph_over(offline_settings, MemorySaver(), RecordingProjection(), apply=crashing)
    )
    bid = bid_row()
    await runner.start(bid)

    # Act / Assert
    with (
        caplog.at_level(logging.ERROR, logger="crossbid.agent.runner"),
        pytest.raises(StageError),
    ):
        await runner.submit_review(bid, REVIEW)

    assert "could not release the review claim" in caplog.text


async def test_a_second_review_of_the_same_bid_in_flight_is_refused(
    offline_settings: Settings, releases: ReleaseRecorder
) -> None:
    """The database claim cannot see this one: the resumed graph rewrites `awaiting_review`
    on its way past the interrupt, so the row is claimable again for several round-trips.
    A double-click would resume one thread twice — two audit rows, two decisions."""
    # Arrange
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_apply(state: BidState, config: RunnableConfig | None = None) -> Any:
        started.set()
        await release.wait()
        return await quiet_apply(state, config)

    runner = runner_for(
        graph_over(offline_settings, MemorySaver(), RecordingProjection(), apply=slow_apply)
    )
    bid = bid_row()
    await runner.start(bid)

    # Act -- the first review parks inside `apply_review`; the second arrives meanwhile
    first = asyncio.create_task(runner.submit_review(bid, REVIEW))
    await asyncio.wait_for(started.wait(), timeout=WAIT_TIMEOUT_S)
    with pytest.raises(RunnerError, match="already being reviewed"):
        await runner.submit_review(bid, REVIEW)

    # Assert -- and the guard is released once the first finishes
    release.set()
    await first
    await runner.submit_review(bid, REVIEW)


class ReleaseRecorder:
    """Replaces `readmodel.bids.release_bid_to_review` for the runner."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    async def __call__(self, db: Any, *, company_id: str, bid_id: str, reason: str) -> None:
        self.calls.append((company_id, bid_id, reason))


@pytest.fixture
def releases(monkeypatch: pytest.MonkeyPatch) -> ReleaseRecorder:
    recorder = ReleaseRecorder()
    monkeypatch.setattr(runner_module, "release_bid_to_review", recorder)
    return recorder


async def test_a_review_is_traced_apart_from_the_run_that_parked(
    offline_settings: Settings, failures: FailureRecorder
) -> None:
    """The two happen minutes or days apart; reading them as one trace misreports both."""
    # Arrange
    configs: list[Any] = []

    class RecordingGraph:
        def __init__(self, inner: Any) -> None:
            self._inner = inner

        async def ainvoke(self, payload: Any, config: Any = None) -> Any:
            configs.append(config)
            return await self._inner.ainvoke(payload, config)

        async def aget_state(self, config: Any) -> Any:
            return await self._inner.aget_state(config)

    saver = MemorySaver()
    inner = graph_over(offline_settings, saver, RecordingProjection())
    runner = runner_for(RecordingGraph(inner))
    bid = bid_row()
    await runner.start(bid)

    # Act
    await runner.submit_review(bid, REVIEW)

    # Assert
    assert configs[0]["run_name"] == runner_module.RUN_NAME
    assert configs[-1]["run_name"] == runner_module.REVIEW_RUN_NAME
