"""S3.1.1 — the outer graph: `parse_docs → extract_reqs → await_review`, checkpointed.

**The outer graph is a deterministic workflow with a human interrupt, not an agent.** Every
edge below is fixed: parse the pack, extract the requirements, stop for the reviewer. No
model decides what runs next, and nothing here calls a tool. The *agentic* part of Crossbid
— a small ReAct loop per requirement with a bounded tool budget — lives inside `check_reqs`
(F3.3), which later stories add between `extract_reqs` and the interrupt along with
`score_verdict`, `apply_review` and `finalize`. Extraction fans out for latency and nothing
else (ADR-0011). Describing the graph this way is a CLAUDE.md convention, and this module is
where the description has to be true.

Three decisions.

**1. Every node runs inside a stage, and the stage keeps the read model current.** The
browser polls `GET /bids/{id}`, which reads `bids.status` and never a checkpoint. So each
node is wrapped: on entry the stage writes its status (`parsing`, `extracting`, ...) to the
read model; on exit it projects what the node produced — the accumulated problem list after
every node, the requirement rows after extraction — and merges `status` into the node's own
update so the checkpoint records which stage its values came from. Nodes stay pure functions
of `(state, config)`; the projection is one seam, `RunProjection`, that tests replace with a
recorder and the runner wires to `readmodel/`.

**2. The interrupt is a node that calls `interrupt()`, not `interrupt_after=`.** Measured on
langgraph 1.2.11 before choosing: a static `interrupt_after` on the graph's *last* node
leaves `aget_state().next == ()` and no `interrupts` — indistinguishable from a finished
run, and `ainvoke(None)` on it does nothing. A node that raises `interrupt()` parks with
`next == ("await_review",)` and a payload in `interrupts`, which is exactly what S3.4.2's
resume needs to *find* the pause and what S4.5.3 needs to show what is being waited for. It
continues with `Command(resume=review)`, and the review arrives as the node's return value,
typed, with no `aupdate_state` on channels. One documented caveat: on resume the node re-runs
from its top, so the `awaiting_review` write happens twice; the value is the same both times
and `apply_review`'s stage overwrites it at once.

**3. A failure names the stage, never the document.** An exception out of a node is
re-raised as `StageError`, whose message is `"<stage> failed: <ExceptionType>"` — what the
runner stores as `failure_reason` and the dashboard shows. The exception's own message is
deliberately dropped: a parser or a validator quotes its input, and that input is a tender
(ADR-0008). The traceback is in the log. LangGraph's own control-flow exceptions
(`GraphBubbleUp`, which `interrupt()` uses) pass through untouched, or the pause would be
reported as a crash.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Mapping, Sequence
from typing import Any, Final, Optional, Protocol

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.errors import GraphBubbleUp
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt

from crossbid.agent.nodes.extract_reqs import build_extract_reqs
from crossbid.agent.nodes.parse_docs import build_parse_docs
from crossbid.agent.state import BidState, ExtractionProblem
from crossbid.db import Database
from crossbid.models.requirement import Requirement
from crossbid.models.tender import BidStatus
from crossbid.readmodel.bids import (
    BidRow,
    ConnectionSource,
    set_bid_problems,
    set_bid_status,
)
from crossbid.readmodel.requirements import write_requirements
from crossbid.settings import Settings

logger = logging.getLogger(__name__)

PARSE_DOCS: Final = "parse_docs"
EXTRACT_REQS: Final = "extract_reqs"
AWAIT_REVIEW: Final = "await_review"
"""Node names. `AWAIT_REVIEW` is what `aget_state().next` reports while a bid is parked,
and S3.4.2 resumes by that name."""

INTERRUPT_BID_ID: Final = "bid_id"
INTERRUPT_REQUIREMENTS: Final = "requirements"
INTERRUPT_PROBLEMS: Final = "problems"
"""Keys of the interrupt payload: enough for a poller to say "waiting on you, with N rows
and M problems". Plain JSON, because the Postgres saver stores it."""

BidUpdate = Mapping[str, Any]
"""A node's partial state. `ParseUpdate` and `ExtractionUpdate` both satisfy it."""


class BidNode(Protocol):
    """What the graph calls: `(state, config) -> partial state`. Both nodes fit by shape.

    `Optional[...]` rather than `| None` for the reason every node states: LangGraph reads
    the annotation as a string and only the `Optional` spelling gets `config` injected.
    """

    def __call__(
        self,
        state: BidState,
        config: Optional[RunnableConfig] = None,  # noqa: UP045
    ) -> Awaitable[BidUpdate]: ...


class StageNode(Protocol):
    """A wrapped node: same call shape as `BidNode`, and its update always carries `status`."""

    def __call__(
        self,
        state: BidState,
        config: Optional[RunnableConfig] = None,  # noqa: UP045
    ) -> Awaitable[dict[str, Any]]: ...


class RunProjection(Protocol):
    """The read-model writes a stage makes. `ReadModelProjection` is the real one."""

    async def set_status(self, *, company_id: str, bid_id: str, status: BidStatus) -> None: ...

    async def set_problems(
        self, *, company_id: str, bid_id: str, problems: Sequence[ExtractionProblem]
    ) -> None: ...

    async def write_requirements(
        self, *, company_id: str, rows: Sequence[Requirement]
    ) -> int: ...


class StageError(RuntimeError):
    """A node failed. `stage` says which; the message names the exception's type only."""

    def __init__(self, stage: BidStatus, cause: BaseException) -> None:
        super().__init__(f"{stage.value} failed: {type(cause).__name__}")
        self.stage = stage


class ReadModelProjection:
    """`RunProjection` over the read model, scoped by `company_id` on every call."""

    def __init__(self, db: ConnectionSource) -> None:
        self._db = db

    async def set_status(self, *, company_id: str, bid_id: str, status: BidStatus) -> None:
        await set_bid_status(self._db, company_id=company_id, bid_id=bid_id, status=status)

    async def set_problems(
        self, *, company_id: str, bid_id: str, problems: Sequence[ExtractionProblem]
    ) -> None:
        await set_bid_problems(
            self._db,
            company_id=company_id,
            bid_id=bid_id,
            problems=[problem.model_dump(mode="json") for problem in problems],
        )

    async def write_requirements(self, *, company_id: str, rows: Sequence[Requirement]) -> int:
        return await write_requirements(self._db, company_id=company_id, rows=rows)


# ------------------------------------------------------------------------------- stages


def stage(status: BidStatus, node: BidNode, projection: RunProjection) -> StageNode:
    """`node`, wrapped so the read model learns the stage on entry and its output on exit.

    See decisions 1 and 3 in the module docstring. Everything inside — the status write, the
    node, the projection — is under the one `except`, so a failed *write* names the stage as
    well: "parsing failed: OperationalError" is a better dashboard line than a traceback.
    """

    async def run(
        state: BidState,
        # `Optional[...]`, not `RunnableConfig | None`: LangGraph matches this annotation
        # as a *string* under postponed annotations, and the modern spelling is silently
        # never injected (CLAUDE.md).
        config: Optional[RunnableConfig] = None,  # noqa: UP045
    ) -> dict[str, Any]:
        try:
            bid_id, company_id = _identity_of(state)
            await projection.set_status(company_id=company_id, bid_id=bid_id, status=status)
            update = await node(state, config)
            await _project(projection, state, update, bid_id=bid_id, company_id=company_id)
        except GraphBubbleUp:
            raise  # `interrupt()` and friends: LangGraph's control flow, not a failure.
        except Exception as exc:
            raise StageError(status, exc) from exc
        return {**update, "status": status}

    run.__name__ = f"{status.value}_stage"
    return run


async def _project(
    projection: RunProjection,
    state: BidState,
    update: BidUpdate,
    *,
    bid_id: str,
    company_id: str,
) -> None:
    """What the poller may read the moment the node is done: problems always, rows if any.

    The problem list is the *accumulated* one — the state's plus the node's — because the
    read model holds the whole list and `extraction_problems` is an appending channel.
    """
    problems = [*state.get("extraction_problems", []), *update.get("extraction_problems", [])]
    await projection.set_problems(company_id=company_id, bid_id=bid_id, problems=problems)
    rows: Sequence[Requirement] = update.get("requirements", [])
    if rows:
        written = await projection.write_requirements(company_id=company_id, rows=rows)
        logger.info("Bid %s: %d requirement(s) written to the read model", bid_id, written)


async def _request_review(
    state: BidState,
    config: Optional[RunnableConfig] = None,  # noqa: UP045
) -> BidUpdate:
    """The interrupt node's body. Parks the run; returns only once a human resumes it.

    In this increment nothing follows, so the return is empty and the wrapping stage's
    `status` is all the resume records. S3.4.2 replaces the return with the review payload
    `interrupt()` hands back.
    """
    interrupt(
        {
            INTERRUPT_BID_ID: state.get("bid_id", ""),
            INTERRUPT_REQUIREMENTS: len(state.get("requirements", [])),
            INTERRUPT_PROBLEMS: len(state.get("extraction_problems", [])),
        }
    )
    return {}


def _identity_of(state: BidState) -> tuple[str, str]:
    """`bid_id` and `company_id`, or a `ValueError` naming the gap.

    Both are set by the runner before the first node; a state without one cannot be
    projected under any tenant, and writing it nowhere would leave the poller on `queued`.
    """
    bid_id = state.get("bid_id", "").strip()
    company_id = state.get("company_id", "").strip()
    missing = [
        name for name, value in (("bid_id", bid_id), ("company_id", company_id)) if not value
    ]
    if missing:
        raise ValueError(f"the graph state needs {', '.join(missing)}")
    return bid_id, company_id


# ------------------------------------------------------------------------------- building


def build_graph(
    settings: Settings,
    db: Database,
    *,
    parse_docs: BidNode | None = None,
    extract_reqs: BidNode | None = None,
    projection: RunProjection | None = None,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
) -> CompiledStateGraph[Any, Any, Any, Any]:
    """The compiled outer graph — a deterministic workflow with a human interrupt.

    `START → parse_docs → extract_reqs → await_review → END`, compiled on the process
    checkpointer so that a run interrupted by a restart continues from its last completed
    node (`runner.resume_unfinished_runs`). The four keyword seams exist for tests, which run
    the real wiring over fake nodes, a recording projection and a `MemorySaver`; production
    passes none of them. Building the real `parse_docs` raises `StorageError` when Storage
    is not configured — see `build_parse_docs` — and that is left to the caller to answer.
    """
    parse = parse_docs if parse_docs is not None else build_parse_docs(settings, db)
    extract = extract_reqs if extract_reqs is not None else build_extract_reqs(settings)
    project = projection if projection is not None else ReadModelProjection(db)
    saver = checkpointer if checkpointer is not None else db.checkpointer

    builder: StateGraph[BidState] = StateGraph(BidState)
    # Workflow nodes: fixed order, no model chooses the next step. The agentic loop of
    # F3.3 slots in after `extract_reqs`; the interrupt stays last before the review nodes.
    builder.add_node(PARSE_DOCS, stage(BidStatus.PARSING, parse, project))
    builder.add_node(EXTRACT_REQS, stage(BidStatus.EXTRACTING, extract, project))
    builder.add_node(AWAIT_REVIEW, stage(BidStatus.AWAITING_REVIEW, _request_review, project))
    builder.add_edge(START, PARSE_DOCS)
    builder.add_edge(PARSE_DOCS, EXTRACT_REQS)
    builder.add_edge(EXTRACT_REQS, AWAIT_REVIEW)
    builder.add_edge(AWAIT_REVIEW, END)
    return builder.compile(checkpointer=saver)


def initial_state(bid: BidRow) -> BidState:
    """The state a fresh run starts from: identity from the row, every channel empty.

    `source_language` and `notice_number` are nullable columns; the graph wants strings,
    and `parse_docs` refuses a blank language with a message naming it, so an empty string
    here is a failure the dashboard can explain rather than a `None` deep in a node.
    """
    return {
        "bid_id": bid.id,
        "company_id": bid.company_id,
        "notice_number": bid.notice_number or "",
        "source_language": bid.source_language or "",
        "bidder_language": bid.bidder_language,
        "status": BidStatus.QUEUED,
        "documents": [],
        "requirements": [],
        "extraction_problems": [],
    }
