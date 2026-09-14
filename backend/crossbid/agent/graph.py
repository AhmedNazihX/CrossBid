"""S3.1.1 — the outer graph: parse, extract, check, then stop for a human. Checkpointed.

**The outer graph is a deterministic workflow with a human interrupt, not an agent.** Every
edge below is fixed: parse the pack, extract the requirements, check them, stop for the
reviewer. No model decides what runs next, and nothing here calls a tool. The *agentic* part
of Crossbid — a small ReAct loop per requirement with a bounded tool budget — lives inside
`check_reqs` (S3.3.1), the node this graph fans out to. `score_verdict` (S3.4.1) is a rules
engine and calls no model either, and so are `apply_review` and `finalize` (S3.4.2) --
no model runs anywhere past the fan-out.
Extraction fans out for latency and nothing else (ADR-0011).
Describing the graph this way is a CLAUDE.md convention, and this module is where the
description has to be true.

Four decisions.

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

**3. Checking fans out by lane, and the number of lanes is the concurrency limit.**
`plan_checks` resolves who the bidder is and a conditional edge then emits one `Send` per
lane of requirements — `min(agent.check_concurrency, len(requirements))` of them, dealt
round-robin by `check_reqs.lanes_of`. The bound is therefore structural: there is no
semaphore to re-establish after a resume, and the Postgres checkpointer writes once per lane
instead of once per requirement, which matters because it serialises every operation on one
lock (CLAUDE.md). A bid whose extraction found nothing skips the fan-out and goes straight to
the interrupt; a lane's rows are projected by its own stage, so the matrix fills in lane by
lane rather than all at the end. The reasoning is in `nodes/check_reqs.py`.

**4. A failure names the stage, never the document.** An exception out of a node is
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
from langgraph.types import Send, interrupt

from crossbid.agent.nodes.check_reqs import (
    build_check_reqs,
    build_plan_checks,
    lane_state,
    lanes_of,
)
from crossbid.agent.nodes.extract_reqs import build_extract_reqs
from crossbid.agent.nodes.parse_docs import build_parse_docs
from crossbid.agent.nodes.review import build_apply_review, finalize
from crossbid.agent.nodes.score_verdict import build_score_verdict
from crossbid.agent.state import BidState, ExtractionProblem
from crossbid.db import Database
from crossbid.models.matrix import MatrixRow
from crossbid.models.requirement import Requirement
from crossbid.models.review import ReviewSubmission
from crossbid.models.tender import BidStatus
from crossbid.models.verdict import Decision, Verdict
from crossbid.readmodel.bids import (
    BidRow,
    ConnectionSource,
    record_review,
    set_bid_problems,
    set_bid_status,
    set_bid_verdict,
)
from crossbid.readmodel.matrix import write_matrix_rows, write_reviewed_rows
from crossbid.readmodel.requirements import write_requirements
from crossbid.readmodel.usage import DatabaseUsageSink
from crossbid.settings import Settings
from crossbid.usage import UsageNode, UsageRecorder, UsageSink, recording_usage

logger = logging.getLogger(__name__)

PARSE_DOCS: Final = UsageNode.PARSE_DOCS.value
EXTRACT_REQS: Final = UsageNode.EXTRACT_REQS.value
PLAN_CHECKS: Final = UsageNode.PLAN_CHECKS.value
CHECK_REQS: Final = UsageNode.CHECK_REQS.value
SCORE_VERDICT: Final = UsageNode.SCORE_VERDICT.value
AWAIT_REVIEW: Final = UsageNode.AWAIT_REVIEW.value
APPLY_REVIEW: Final = UsageNode.APPLY_REVIEW.value
FINALIZE: Final = UsageNode.FINALIZE.value
"""Node names. `AWAIT_REVIEW` is what `aget_state().next` reports while a bid is parked,
and S3.4.2 resumes by that name.

They are read off `UsageNode` rather than written out again, because `llm_usage.node` is
the same vocabulary (S5.2) and the column is free text. Renaming a node under two
independent lists of strings would split that node's costs across two labels in
`/dev/costs` with nothing failing; here the enum is the single source and a new node does
not type-check until it is named in both places."""

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

    async def write_matrix_rows(
        self, *, company_id: str, bid_id: str, rows: Sequence[MatrixRow]
    ) -> int: ...

    async def set_verdict(self, *, company_id: str, bid_id: str, verdict: Verdict) -> None: ...

    async def record_review(
        self,
        *,
        company_id: str,
        bid_id: str,
        decision: Decision,
        agent_verdict: Verdict | None,
        final_verdict: Verdict,
        override_reason: str | None,
    ) -> None: ...

    async def write_reviewed_rows(
        self, *, company_id: str, bid_id: str, rows: Sequence[MatrixRow]
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

    async def write_matrix_rows(
        self, *, company_id: str, bid_id: str, rows: Sequence[MatrixRow]
    ) -> int:
        return await write_matrix_rows(
            self._db, company_id=company_id, bid_id=bid_id, rows=rows
        )

    async def set_verdict(self, *, company_id: str, bid_id: str, verdict: Verdict) -> None:
        await set_bid_verdict(
            self._db,
            company_id=company_id,
            bid_id=bid_id,
            verdict=verdict.model_dump(mode="json"),
        )

    async def write_reviewed_rows(
        self, *, company_id: str, bid_id: str, rows: Sequence[MatrixRow]
    ) -> int:
        return await write_reviewed_rows(
            self._db, company_id=company_id, bid_id=bid_id, rows=rows
        )

    async def record_review(
        self,
        *,
        company_id: str,
        bid_id: str,
        decision: Decision,
        agent_verdict: Verdict | None,
        final_verdict: Verdict,
        override_reason: str | None,
    ) -> None:
        await record_review(
            self._db,
            company_id=company_id,
            bid_id=bid_id,
            decision=decision,
            agent_verdict=(
                None if agent_verdict is None else agent_verdict.model_dump(mode="json")
            ),
            final_verdict=final_verdict.model_dump(mode="json"),
            override_reason=override_reason,
        )


# ------------------------------------------------------------------------------- stages


def stage(
    name: UsageNode,
    status: BidStatus,
    node: BidNode,
    projection: RunProjection,
    usage: UsageSink,
) -> StageNode:
    """`node`, wrapped so the read model learns the stage and the cost table learns the node.

    See decisions 1 and 3 in the module docstring. Everything inside — the status write, the
    node, the projection — is under the one `except`, so a failed *write* names the stage as
    well: "parsing failed: OperationalError" is a better dashboard line than a traceback.

    **The usage scope is opened here rather than inside the nodes that spend (S5.2).** Three
    nodes call a model today and the others do not, but the wrapper every node already goes
    through is the only place where forgetting is impossible: a node added later is
    attributed the moment it starts spending, and a node that stops spending simply stops
    producing rows. The scope carries the bid, the tenant and this node's name, and
    `crossbid.usage` explains why it travels in a context variable instead of an argument —
    in short, because `check_loop` invokes its model with no `RunnableConfig` to put it in.

    `name` is a `UsageNode` rather than the node's string so that the graph's vocabulary and
    the cost table's are one closed set; `status` cannot serve instead, because `plan_checks`
    and `check_reqs` share `BidStatus.CHECKING` and their costs are nothing alike.
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
            recorder = UsageRecorder(
                sink=usage, company_id=company_id, bid_id=bid_id, node=name
            )
            with recording_usage(recorder):
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
    read model holds the whole list and `extraction_problems` is an appending channel. A
    checking lane therefore carries the list into its `Send` payload although it adds none
    (`check_reqs.lane_state`): arriving without it would write an empty list over the one
    extraction reported. Requirements and matrix rows are written only when the node
    produced some, so the five lanes of a fan-out write five slices of the matrix and
    nothing else.
    """
    problems = [*state.get("extraction_problems", []), *update.get("extraction_problems", [])]
    await projection.set_problems(company_id=company_id, bid_id=bid_id, problems=problems)
    rows: Sequence[Requirement] = update.get("requirements", [])
    if rows:
        written = await projection.write_requirements(company_id=company_id, rows=rows)
        logger.info("Bid %s: %d requirement(s) written to the read model", bid_id, written)
    matrix: Sequence[MatrixRow] = update.get("matrix_rows", [])
    if matrix:
        written = await projection.write_matrix_rows(
            company_id=company_id, bid_id=bid_id, rows=matrix
        )
        logger.info("Bid %s: %d matrix row(s) written to the read model", bid_id, written)
    verdict: Verdict | None = update.get("verdict")
    if verdict is not None:
        await projection.set_verdict(company_id=company_id, bid_id=bid_id, verdict=verdict)
        logger.info("Bid %s: verdict %s written to the read model", bid_id, verdict.decision)
    await _project_review(projection, state, update, bid_id=bid_id, company_id=company_id)


async def _project_review(
    projection: RunProjection,
    state: BidState,
    update: BidUpdate,
    *,
    bid_id: str,
    company_id: str,
) -> None:
    """The audit record, written when `finalize` reports a decision and not before.

    `decision` in an update is the signal, and everything else the record needs is already
    on the state by then — the review the interrupt returned, the agent's verdict as
    `apply_review` preserved it, and the re-score that replaced it. Doing it here rather
    than from the node keeps the rule the module docstring states: a node returns state, the
    stage decides what the read model learns from it (decision 1).
    """
    decision: Decision | None = update.get("decision")
    if decision is None:
        return
    final: Verdict | None = state.get("verdict")
    if final is None:  # pragma: no cover -- apply_review always writes one first
        raise ValueError("a review cannot be recorded before the bid has been scored")
    # The reviewer's own columns, which the agent's upsert deliberately cannot write
    # (`readmodel/matrix.py`). Every row, not just the edited ones: an untouched row is
    # `confirmed` at this moment, and that is a fact about it.
    written = await projection.write_reviewed_rows(
        company_id=company_id, bid_id=bid_id, rows=state.get("matrix_rows", [])
    )
    logger.info("Bid %s: %d row(s) marked with the reviewer's disposition", bid_id, written)
    review: ReviewSubmission | None = state.get("review")
    await projection.record_review(
        company_id=company_id,
        bid_id=bid_id,
        decision=decision,
        agent_verdict=state.get("agent_verdict"),
        final_verdict=final,
        override_reason=None if review is None else review.override_reason,
    )
    logger.info("Bid %s: review recorded, the reviewer decided %s", bid_id, decision.value)


async def _request_review(
    state: BidState,
    config: Optional[RunnableConfig] = None,  # noqa: UP045
) -> BidUpdate:
    """The interrupt node's body. Parks the run; returns only once a human resumes it.

    `interrupt()` returns whatever `Command(resume=...)` carried, so the reviewer's
    submission arrives here as the node's own value — typed, checkpointed with the rest of
    the state, and with no `aupdate_state` on a channel from outside the graph (S3.4.2).
    It is re-validated rather than trusted: a resume can be issued by anything holding the
    thread id, and `ReviewSubmission` is the contract the nodes downstream rely on.

    One documented caveat, unchanged: on resume the node re-runs from its top, so the
    `awaiting_review` status write happens twice. The value is identical both times and
    `apply_review`'s stage overwrites it at once.
    """
    resumed = interrupt(
        {
            INTERRUPT_BID_ID: state.get("bid_id", ""),
            INTERRUPT_REQUIREMENTS: len(state.get("requirements", [])),
            INTERRUPT_PROBLEMS: len(state.get("extraction_problems", [])),
        }
    )
    return {"review": ReviewSubmission.model_validate(resumed)}


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


def fan_out_checks(state: BidState, *, concurrency: int) -> list[Send] | str:
    """One `Send` per checking lane, or straight to scoring when there is nothing to check.

    The conditional edge out of `plan_checks`, and the only place the story's concurrency
    limit is decided — see decision 3. It returns a node *name* rather than an empty list
    for the empty case: an empty list of `Send`s leaves the superstep with no successor at
    all, and the run would finish without ever parking for its reviewer. The name is
    `score_verdict` rather than the interrupt, because a bid whose extraction found nothing
    still owes its reviewer an answer — `insufficient_evidence`, which S3.4.1 refuses to
    let an empty matrix turn into a `go`.
    """
    lanes = lanes_of(state.get("requirements", []), concurrency)
    if not lanes:
        return SCORE_VERDICT
    return [Send(CHECK_REQS, lane_state(state, lane)) for lane in lanes]


def build_graph(
    settings: Settings,
    db: Database,
    *,
    parse_docs: BidNode | None = None,
    extract_reqs: BidNode | None = None,
    plan_checks: BidNode | None = None,
    check_reqs: BidNode | None = None,
    score_verdict: BidNode | None = None,
    apply_review: BidNode | None = None,
    projection: RunProjection | None = None,
    usage: UsageSink | None = None,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
) -> CompiledStateGraph[Any, Any, Any, Any]:
    """The compiled outer graph — a deterministic workflow with a human interrupt.

    `START → parse_docs → extract_reqs → plan_checks →` a lane of `check_reqs` per
    `agent.check_concurrency` `→ score_verdict → await_review → apply_review → finalize →
    END`, compiled on the process checkpointer
    so that a run interrupted by a restart continues from its last completed node
    (`runner.resume_unfinished_runs`). The nine keyword seams exist for tests, which run the
    real wiring over fake nodes, a recording projection, a recording usage sink and a
    `MemorySaver`; production passes none of them. Building the real `parse_docs` raises
    `StorageError` when Storage is not configured — see `build_parse_docs` — and that is
    left to the caller to answer.
    """
    parse = parse_docs if parse_docs is not None else build_parse_docs(settings, db)
    extract = extract_reqs if extract_reqs is not None else build_extract_reqs(settings)
    plan = plan_checks if plan_checks is not None else build_plan_checks(db)
    check = check_reqs if check_reqs is not None else build_check_reqs(settings, db)
    scorer = score_verdict if score_verdict is not None else build_score_verdict(db)
    applier = apply_review if apply_review is not None else build_apply_review(db)
    project = projection if projection is not None else ReadModelProjection(db)
    spend = usage if usage is not None else DatabaseUsageSink(db)
    saver = checkpointer if checkpointer is not None else db.checkpointer
    concurrency = settings.runtime.agent.check_concurrency

    builder: StateGraph[BidState] = StateGraph(BidState)
    # Workflow nodes: fixed order, no model chooses the next step. `check_reqs` is the one
    # agentic node, reached by a `Send` per lane; the interrupt stays last before F3.4.
    builder.add_node(
        PARSE_DOCS, stage(UsageNode.PARSE_DOCS, BidStatus.PARSING, parse, project, spend)
    )
    builder.add_node(
        EXTRACT_REQS,
        stage(UsageNode.EXTRACT_REQS, BidStatus.EXTRACTING, extract, project, spend),
    )
    builder.add_node(
        PLAN_CHECKS, stage(UsageNode.PLAN_CHECKS, BidStatus.CHECKING, plan, project, spend)
    )
    builder.add_node(
        CHECK_REQS, stage(UsageNode.CHECK_REQS, BidStatus.CHECKING, check, project, spend)
    )
    builder.add_node(
        SCORE_VERDICT, stage(UsageNode.SCORE_VERDICT, BidStatus.SCORING, scorer, project, spend)
    )
    builder.add_node(
        AWAIT_REVIEW,
        stage(
            UsageNode.AWAIT_REVIEW, BidStatus.AWAITING_REVIEW, _request_review, project, spend
        ),
    )
    builder.add_node(
        APPLY_REVIEW,
        stage(UsageNode.APPLY_REVIEW, BidStatus.APPLYING_REVIEW, applier, project, spend),
    )
    builder.add_node(
        FINALIZE, stage(UsageNode.FINALIZE, BidStatus.COMPLETE, finalize, project, spend)
    )
    builder.add_edge(START, PARSE_DOCS)
    builder.add_edge(PARSE_DOCS, EXTRACT_REQS)
    builder.add_edge(EXTRACT_REQS, PLAN_CHECKS)
    builder.add_conditional_edges(
        PLAN_CHECKS,
        lambda state: fan_out_checks(state, concurrency=concurrency),
        [CHECK_REQS, SCORE_VERDICT],
    )
    builder.add_edge(CHECK_REQS, SCORE_VERDICT)
    builder.add_edge(SCORE_VERDICT, AWAIT_REVIEW)
    builder.add_edge(AWAIT_REVIEW, APPLY_REVIEW)
    builder.add_edge(APPLY_REVIEW, FINALIZE)
    builder.add_edge(FINALIZE, END)
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
        "bidder_country": "",
        "matrix_rows": [],
    }
