"""S3.1.1 — a bid's graph run in the background, and picking runs up after a restart.

`POST /bids` answers 202 and the graph runs after the response has gone; the browser polls.
That is an `asyncio.Task` on the API's event loop rather than a worker process or a queue,
because there is one API process, one pool (ADR-0010) and one checkpointer lock, and a
second process would only queue on the same lock. Three properties are what the story asks
for and what this module exists to hold.

**1. No task is fire-and-forget.** Every run is held in `BidRunner`'s registry until it
finishes, so `shutdown()` can cancel what is in flight and wait for it, and so `running`
can say which bids are being worked on. A bare `create_task` whose reference is dropped can
be garbage-collected mid-run and its exception lost with it; that is the failure mode the
registry prevents.

**2. A crash is recorded where the bidder will look.** An exception out of the graph is
logged with its traceback and written to the read model as `failed` with a
`failure_reason` — the stage and the exception's type (`graph.StageError`), never its
message, because a node's message can quote the tender (ADR-0008). If even *that* write
fails, the traceback is logged again; nothing is swallowed, and there is nowhere further
for a background task to report to.

**3. Restart recovery needs no bookkeeping of its own.** The checkpointer already holds a
run's completed nodes; what a restart loses is the *task*. So `resume_unfinished_runs`
asks the read model which bids say they should be running (`UNFINISHED_STATUSES` — not
`awaiting_review`, which is parked for a human) and re-invokes the graph on each thread
with no input, which LangGraph takes as "continue from the checkpoint". A bid that has no
checkpoint at all — it was created and the process died before its first node finished —
is started from its row instead, because `ainvoke(None)` on an empty thread raises
`EmptyInputError` (measured, langgraph 1.2.11). The read-model status is the restart
criterion; the checkpoint supplies the state.

The graph is built lazily. Building the real one needs Storage configured
(`build_parse_docs`), and a process with no unfinished bids and no Storage should still
start; a process *with* unfinished bids and no Storage should not, and does not — the build
runs before the first resume and its `StorageError` stops startup (ADR-0010: the API starts
without a database, but not with a broken one).

**4. The graph is built from the settings in force, not the settings at boot.** S4.6.2
lets a developer change the model per role, the temperature, the prompt and the tool set
while the API runs, and a factory that had captured `Settings` at startup would keep
building the old graph — with a panel saying the change had taken effect. So
`build_runner` takes a `SettingsProvider`, a callable answering the current `Settings`,
and the compiled graph is cached only until `invalidate_graph()` is called, which the
settings route does after every successful write. The next run builds afresh; a run
already in flight keeps the graph object it started on, because a bid is one
configuration from `parse_docs` to `await_review` and half-switching it mid-run would
make its cost report and its trace describe two different agents. `RunBudget` is still
read once, and that is not an oversight: none of its inputs is a column of the row.

The story's two limits — ten minutes to `awaiting_review`, $2.50 of OpenRouter cost —
are `RunBudget`. The runner measures wall clock around the invocation and reads the cost
back out of `llm_usage` once the run stops, warning past either budget; the `live` test
asserts both against the DE pack. The cost is read rather than measured because the
runner is the wrong place to see it: the money is spent inside the nodes, and S5.2 records
each call where it happens (`crossbid/usage.py`). Reading the table is also what makes the
figure survive a restart — a run resumed from its checkpoint reports what the whole bid
cost, not what this process happened to watch. The values live in `settings.default.yaml`
under `agent.run_budget_seconds` and `agent.run_budget_usd`, and `RunBudget.from_settings`
reads them from there; the constants below are the fallback for a settings object that
carries neither, which today means a test's.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final, Protocol

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command, StateSnapshot

from crossbid.agent.graph import StageError, build_graph, initial_state
from crossbid.agent.state import BidState
from crossbid.db import Database
from crossbid.models.review import ReviewSubmission
from crossbid.readmodel.bids import (
    BidRow,
    ConnectionSource,
    mark_bid_failed,
    release_bid_to_review,
    unfinished_bids,
)
from crossbid.readmodel.usage import fetch_usage_by_node, totals_of
from crossbid.settings import Settings, bid_run_config

logger = logging.getLogger(__name__)

DEFAULT_RUN_BUDGET_SECONDS: Final = 600.0
"""Ten minutes to `awaiting_review` on the DE pack (S3.1.1). Settings key:
`agent.run_budget_seconds`."""

DEFAULT_RUN_BUDGET_USD: Final = 2.50
"""OpenRouter-reported cost per bid run (S3.1.1). Settings key: `agent.run_budget_usd`."""

"""Attribute names on `settings.runtime.agent` once the parent adds them."""

RUN_NAME: Final = "bid_run"
REVIEW_RUN_NAME: Final = "bid_review"
"""Traces of the resume are named apart from the run that parked (S0.3.3): the two happen
minutes or days apart and reading them as one trace would misreport both."""
TASK_NAME_PREFIX: Final = "bid-run:"

Clock = Callable[[], float]


class RunnerError(RuntimeError):
    """The runner refused an operation; the message says which and why."""


class BidGraph(Protocol):
    """The slice of a compiled graph the runner uses; `build_graph`'s result satisfies it."""

    async def ainvoke(self, input: Any, config: RunnableConfig | None = None) -> Any: ...  # noqa: A002 -- LangGraph's own parameter name

    async def aget_state(self, config: RunnableConfig) -> StateSnapshot: ...


GraphFactory = Callable[[], BidGraph]
SettingsProvider = Callable[[], Settings]
"""Answers the `Settings` in force *now*. `main.settings_provider` reads them off
`app.state`, which is the one place the developer panel's write route replaces them."""


@dataclass(frozen=True, slots=True)
class RunBudget:
    """What one bid run may take, in wall clock and in OpenRouter cost."""

    seconds: float = DEFAULT_RUN_BUDGET_SECONDS
    usd: float = DEFAULT_RUN_BUDGET_USD

    @classmethod
    def from_settings(cls, settings: Settings) -> RunBudget:
        """The budget from `agent.run_budget_seconds` / `agent.run_budget_usd`."""
        agent = settings.runtime.agent
        return cls(seconds=float(agent.run_budget_seconds), usd=float(agent.run_budget_usd))


OVER_BUDGET_TEMPLATE: Final = "run stopped: over the {seconds:.0f}s budget"
"""What a timed-out bid's `failure_reason` says.

Named rather than derived from the exception, because `failure_reason_of` would render a
`TimeoutError` as "run failed: TimeoutError" -- true, and useless to a bidder deciding
whether to start again. The number is in the sentence so the operator can see which budget
it was measured against without opening the settings.
"""


def failure_reason_of(exc: BaseException) -> str:
    """The sentence stored on the bid. A `StageError` already names its stage."""
    if isinstance(exc, StageError):
        return str(exc)
    return f"run failed: {type(exc).__name__}"


class BidRunner:
    """Starts, resumes, tracks and cancels bid runs on the current event loop."""

    def __init__(
        self,
        graph_factory: GraphFactory,
        db: ConnectionSource,
        *,
        budget: RunBudget = RunBudget(),
        clock: Clock = time.monotonic,
    ) -> None:
        self._graph_factory = graph_factory
        self._graph: BidGraph | None = None
        self._db = db
        self._budget = budget
        self._clock = clock
        self._tasks: dict[str, asyncio.Task[None]] = {}
        # Reviews are not tasks — they run inside the caller's request — but they need the
        # same "only one at a time" property, and for a sharper reason. See `submit_review`.
        self._reviewing: set[str] = set()

    @property
    def graph(self) -> BidGraph:
        """The compiled graph, built on first use. May raise `StorageError`; see the module."""
        if self._graph is None:
            self._graph = self._graph_factory()
        return self._graph

    def invalidate_graph(self) -> None:
        """Drop the cached graph so the next run is built from the current settings.

        Called by `PUT /dev/settings` after the row is stored (point 4). Runs in flight
        are untouched: each holds the graph object it started on. Nothing is rebuilt here
        — the factory may raise `StorageError`, and a settings write is not the place to
        surface a Storage misconfiguration; the next `start` is, exactly as at boot.
        """
        self._graph = None

    @property
    def budget(self) -> RunBudget:
        return self._budget

    @property
    def running(self) -> frozenset[str]:
        """Ids of the bids whose run is in flight right now."""
        return frozenset(self._tasks)

    def start(self, bid: BidRow) -> asyncio.Task[None]:
        """Schedule a fresh run of `bid` and return at once; the task is tracked."""
        return self._schedule(bid, resume=False)

    def resume(self, bid: BidRow) -> asyncio.Task[None]:
        """Schedule `bid` to continue from its checkpoint (or from scratch if it has none)."""
        return self._schedule(bid, resume=True)

    async def submit_review(self, bid: BidRow, review: ReviewSubmission) -> None:
        """Resume the parked run with `review` and wait for it, in the caller's request.

        Inline rather than a background task, and that is a considered difference from
        `start`. Everything past the interrupt — applying the edits, re-scoring, writing the
        audit record — is rules and two statements; there is no model call and no page to
        parse, so it finishes in the time an HTTP request already takes. Answering 202 and
        making the reviewer poll for the consequence of their own click would be latency
        invented for the sake of symmetry.

        Failure is recorded the way a background run's is, then re-raised: the bid was
        claimed off `awaiting_review` before this was called, so a silent failure would
        strand it at `applying_review` with nothing saying why. The router turns the
        exception into a 5xx after the reason is on the row.
        """
        if bid.id in self._reviewing:
            # The database claim alone does not close this. On resume LangGraph re-runs the
            # `await_review` node from its top, and the stage wrapper's first act is to write
            # `awaiting_review` again (graph.py, decision 2) — so for the several awaited
            # round-trips until `apply_review` writes its own status, the row is claimable a
            # second time. A double-click would then resume the same thread twice: two audit
            # rows, two decisions, two passes of `write_reviewed_rows`. This set closes that
            # window, and it is checked before the first `await` so nothing can interleave
            # between the test and the insert. One API process (ADR-0010) is what makes an
            # in-process guard sufficient.
            raise RunnerError(f"bid {bid.id} is already being reviewed")
        self._reviewing.add(bid.id)
        config = bid_run_config(bid.id, thread_id=bid.thread_id, run_name=REVIEW_RUN_NAME)
        try:
            await self.graph.ainvoke(Command(resume=review), config)
        except Exception as exc:
            reason = failure_reason_of(exc)
            logger.exception("Bid %s: %s", bid.id, reason)
            await self._release_claim(bid, reason)
            raise
        finally:
            self._reviewing.discard(bid.id)

    async def shutdown(self) -> None:
        """Cancel every run in flight and wait for the cancellations to land.

        Completed nodes are already checkpointed; the node that was running is lost and
        re-run by `resume_unfinished_runs` on the next start. Called from the lifespan.
        """
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            logger.info("cancelled %d bid run(s) on shutdown", len(tasks))

    def _schedule(self, bid: BidRow, *, resume: bool) -> asyncio.Task[None]:
        if bid.id in self._tasks:
            raise RunnerError(f"bid {bid.id} is already running")
        task = asyncio.create_task(
            self._run(bid, resume=resume), name=f"{TASK_NAME_PREFIX}{bid.id}"
        )
        self._tasks[bid.id] = task
        task.add_done_callback(lambda _done: self._tasks.pop(bid.id, None))
        return task

    async def _run(self, bid: BidRow, *, resume: bool) -> None:
        """One run, start to park (or crash). Never raises except on cancellation."""
        config = bid_run_config(bid.id, thread_id=bid.thread_id, run_name=RUN_NAME)
        started = self._clock()
        outcome = "parked"
        try:
            payload = await self._input_for(bid, config, resume=resume)
            # A real deadline, not a note written afterwards. `run_budget_seconds` was only
            # ever read once the run had already stopped, so nothing bounded a run at all:
            # at `llm_timeout_seconds` x the model's attempts per section, a pathological
            # pack could hold a worker for the better part of an hour while the bidder
            # watched a status that never moved. `asyncio.timeout` re-raises a cancellation
            # that was not its own, so `shutdown()` still reads as a cancellation below.
            async with asyncio.timeout(self._budget.seconds):
                await self.graph.ainvoke(payload, config)
        except TimeoutError:
            outcome = "timed out"
            reason = OVER_BUDGET_TEMPLATE.format(seconds=self._budget.seconds)
            logger.warning("Bid %s: %s", bid.id, reason)
            await self._record_failure(bid, reason)
        except asyncio.CancelledError:
            logger.info("Bid %s: run cancelled; it resumes from its checkpoint", bid.id)
            raise
        except Exception as exc:
            outcome = "failed"
            reason = failure_reason_of(exc)
            logger.exception("Bid %s: %s", bid.id, reason)
            await self._record_failure(bid, reason)
        self._report_elapsed(bid, self._clock() - started, outcome=outcome)
        # Outside the branch on purpose: a run that failed in `check_reqs` has already
        # bought most of what a finished one would, and that is the run whose bill an
        # operator most wants to see.
        await self._report_cost(bid)

    async def _input_for(
        self, bid: BidRow, config: RunnableConfig, *, resume: bool
    ) -> BidState | None:
        """`None` continues from the checkpoint; a full state starts over. See point 3."""
        if not resume:
            return initial_state(bid)
        snapshot = await self.graph.aget_state(config)
        if snapshot.created_at is not None:
            logger.info("Bid %s: resuming from checkpoint, next=%s", bid.id, snapshot.next)
            return None
        logger.info("Bid %s: no checkpoint yet; starting from the row", bid.id)
        return initial_state(bid)

    async def _release_claim(self, bid: BidRow, reason: str) -> None:
        """A failed review goes back to `awaiting_review`, not to `failed`.

        `failed` is terminal and unreachable by every recovery path the product has — the
        startup resume skips it and `claim_bid_for_review` refuses it — so a transient pool
        timeout would strand the bid for good. The graph is still parked at its interrupt;
        resubmitting is the affordance, and this is what leaves it available.
        """
        try:
            await release_bid_to_review(
                self._db, company_id=bid.company_id, bid_id=bid.id, reason=reason
            )
        except Exception:
            logger.exception("Bid %s: could not release the review claim", bid.id)

    async def _record_failure(self, bid: BidRow, reason: str) -> None:
        try:
            await mark_bid_failed(
                self._db, company_id=bid.company_id, bid_id=bid.id, reason=reason
            )
        except Exception:
            # The last place a background task can report to is the log.
            logger.exception("Bid %s: could not record the failure '%s'", bid.id, reason)

    def _report_elapsed(self, bid: BidRow, elapsed: float, *, outcome: str) -> None:
        """How long the run held a worker, whatever became of it.

        Reported on every path, including the ones that raised. It used to be the `else`
        branch alone, so the runs whose wall clock an operator most wants -- the ones that
        died -- were the runs that reported none.
        """
        if elapsed > self._budget.seconds:
            logger.warning(
                "Bid %s: run %s after %.0fs, over the %.0fs budget",
                bid.id,
                outcome,
                elapsed,
                self._budget.seconds,
            )
            return
        logger.info("Bid %s: run %s after %.0fs", bid.id, outcome, elapsed)

    async def _report_cost(self, bid: BidRow) -> None:
        """What the run actually bought, against `budget.usd`. Never raises (S5.2).

        Summed from `llm_usage` rather than accumulated in memory, so the figure is the same
        one `GET /dev/costs` shows and a resumed run reports the whole bid rather than the
        slice this process saw. `unpriced_calls` rides along in both messages because a
        total with unpriced calls behind it is a lower bound, and a budget compared against
        a lower bound can pass for the wrong reason.

        A read that fails is logged and nothing else: the run is already over, the bid's
        status is already written, and refusing to finish a task over a cost report would
        trade a number for a state machine.
        """
        try:
            lines = await fetch_usage_by_node(
                self._db, company_id=bid.company_id, bid_id=bid.id
            )
        except Exception:
            logger.exception("Bid %s: could not read what the run cost", bid.id)
            return
        spent = totals_of(lines)
        tokens = spent.input_tokens + spent.output_tokens
        if spent.cost_usd > self._budget.usd:
            logger.warning(
                "Bid %s: run cost $%.4f, over the $%.2f budget "
                "(%d call(s), %d tokens, %d unpriced)",
                bid.id,
                spent.cost_usd,
                self._budget.usd,
                spent.calls,
                tokens,
                spent.unpriced_calls,
            )
            return
        logger.info(
            "Bid %s: run cost $%.4f (%d call(s), %d tokens, %d unpriced)",
            bid.id,
            spent.cost_usd,
            spent.calls,
            tokens,
            spent.unpriced_calls,
        )


def build_runner(db: Database, current_settings: SettingsProvider) -> BidRunner:
    """The production runner: the real graph, built lazily from the settings in force.

    `current_settings` is called on every build, not once here, so a graph rebuilt after
    `invalidate_graph()` sees what the developer panel stored (point 4). The budget is
    read once because nothing in `AppSettingsRow` can change it.
    """
    return BidRunner(
        lambda: build_graph(current_settings(), db),
        db,
        budget=RunBudget.from_settings(current_settings()),
    )


async def resume_unfinished_runs(
    db: Database, current_settings: SettingsProvider, *, runner: BidRunner | None = None
) -> BidRunner:
    """Startup hook: re-invoke the graph on every bid the read model says is still running.

    Returns the runner so the lifespan can keep it (`app.state.bid_runner`, which the router
    shares) and call `shutdown()` on exit. With nothing to resume the graph is not built,
    so a process without Storage still starts; with something to resume it is built first,
    and a configuration gap stops startup rather than failing the bids.
    """
    active = runner if runner is not None else build_runner(db, current_settings)
    rows = await unfinished_bids(db)
    if not rows:
        logger.info("no unfinished bid runs to resume")
        return active
    active.graph  # noqa: B018 -- build now, so a StorageError stops startup, not the bids
    for row in rows:
        active.resume(row)
    logger.info("resuming %d unfinished bid run(s)", len(rows))
    return active
