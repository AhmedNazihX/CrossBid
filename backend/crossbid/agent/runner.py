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

The story's two limits — ten minutes to `awaiting_review`, $2.50 of OpenRouter cost —
are `RunBudget`. The runner measures wall clock and warns past the budget; the `live` test
asserts both against the DE pack. The values are meant to live in
`settings.default.yaml` under `agent.run_budget_seconds` and `agent.run_budget_usd`, and
`RunBudget.from_settings` reads them from there once they exist, falling back to the
constants here until then.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final, Protocol

from langchain_core.runnables import RunnableConfig
from langgraph.types import StateSnapshot

from crossbid.agent.graph import StageError, build_graph, initial_state
from crossbid.agent.state import BidState
from crossbid.db import Database
from crossbid.readmodel.bids import (
    BidRow,
    ConnectionSource,
    mark_bid_failed,
    unfinished_bids,
)
from crossbid.settings import Settings, bid_run_config

logger = logging.getLogger(__name__)

DEFAULT_RUN_BUDGET_SECONDS: Final = 600.0
"""Ten minutes to `awaiting_review` on the DE pack (S3.1.1). Settings key:
`agent.run_budget_seconds`."""

DEFAULT_RUN_BUDGET_USD: Final = 2.50
"""OpenRouter-reported cost per bid run (S3.1.1). Settings key: `agent.run_budget_usd`."""

"""Attribute names on `settings.runtime.agent` once the parent adds them."""

RUN_NAME: Final = "bid_run"
TASK_NAME_PREFIX: Final = "bid-run:"

Clock = Callable[[], float]


class RunnerError(RuntimeError):
    """The runner refused an operation; the message says which and why."""


class BidGraph(Protocol):
    """The slice of a compiled graph the runner uses; `build_graph`'s result satisfies it."""

    async def ainvoke(self, input: Any, config: RunnableConfig | None = None) -> Any: ...  # noqa: A002 -- LangGraph's own parameter name

    async def aget_state(self, config: RunnableConfig) -> StateSnapshot: ...


GraphFactory = Callable[[], BidGraph]


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

    @property
    def graph(self) -> BidGraph:
        """The compiled graph, built on first use. May raise `StorageError`; see the module."""
        if self._graph is None:
            self._graph = self._graph_factory()
        return self._graph

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
        try:
            payload = await self._input_for(bid, config, resume=resume)
            await self.graph.ainvoke(payload, config)
        except asyncio.CancelledError:
            logger.info("Bid %s: run cancelled; it resumes from its checkpoint", bid.id)
            raise
        except Exception as exc:
            reason = failure_reason_of(exc)
            logger.exception("Bid %s: %s", bid.id, reason)
            await self._record_failure(bid, reason)
            return
        self._report_elapsed(bid, self._clock() - started)

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

    async def _record_failure(self, bid: BidRow, reason: str) -> None:
        try:
            await mark_bid_failed(
                self._db, company_id=bid.company_id, bid_id=bid.id, reason=reason
            )
        except Exception:
            # The last place a background task can report to is the log.
            logger.exception("Bid %s: could not record the failure '%s'", bid.id, reason)

    def _report_elapsed(self, bid: BidRow, elapsed: float) -> None:
        if elapsed > self._budget.seconds:
            logger.warning(
                "Bid %s: run took %.0fs, over the %.0fs budget",
                bid.id,
                elapsed,
                self._budget.seconds,
            )
            return
        logger.info("Bid %s: run parked after %.0fs", bid.id, elapsed)


def build_runner(db: Database, settings: Settings) -> BidRunner:
    """The production runner: the real graph, built lazily, over the process pool."""
    return BidRunner(
        lambda: build_graph(settings, db), db, budget=RunBudget.from_settings(settings)
    )


async def resume_unfinished_runs(
    db: Database, settings: Settings, *, runner: BidRunner | None = None
) -> BidRunner:
    """Startup hook: re-invoke the graph on every bid the read model says is still running.

    Returns the runner so the lifespan can keep it (`app.state.bid_runner`, which the router
    shares) and call `shutdown()` on exit. With nothing to resume the graph is not built,
    so a process without Storage still starts; with something to resume it is built first,
    and a configuration gap stops startup rather than failing the bids.
    """
    active = runner if runner is not None else build_runner(db, settings)
    rows = await unfinished_bids(db)
    if not rows:
        logger.info("no unfinished bid runs to resume")
        return active
    active.graph  # noqa: B018 -- build now, so a StorageError stops startup, not the bids
    for row in rows:
        active.resume(row)
    logger.info("resuming %d unfinished bid run(s)", len(rows))
    return active
