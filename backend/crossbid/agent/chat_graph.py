"""S3.5.1 — "ask the tender": a ReAct agent on its own thread, whose citations cannot be
invented.

`POST /bids/{id}/chat` asks a question about one bid and gets an answer in the bidder's own
language with a document and a page behind every claim. This module is the agent that
produces it: a small ReAct loop over three tools, bounded, followed by one structured call
whose citations are resolved against what the tools actually returned.

It is the *second* agentic surface in Crossbid and the second only. The bid graph
(`agent/graph.py`) is a deterministic workflow with a human interrupt, and the one agentic
node inside it is `check_reqs`; this is a separate graph on a separate thread that no bid run
ever enters. Nothing here writes to the read model, resumes a bid, or changes a matrix row —
a chat turn is a read, and the review step stays the only place a verdict can move.

Six decisions carry this module.

**1. The conversation lives in the LangGraph checkpointer, on thread `bid:{id}:chat`.** The
alternative — a stateless endpoint whose request carries the history — was rejected on a
security argument rather than a convenience one. Citations are the whole point of this story,
and a history the browser sends is a history in which the browser can put words, and
citations, into the assistant's mouth; the next turn would then build on a transcript we
never wrote. Holding it server-side also costs nothing to build: `db.checkpointer` already
exists, is already `.setup()` at startup (S0.2.2), and needs no migration, no table and no
new writer. The known cost is `AsyncPostgresSaver`'s single `asyncio.Lock` (CLAUDE.md) — but
a chat turn is a handful of checkpoint writes on a thread of its own, made while a human
types, where the checking fan-out is hundreds of writes in a burst.

**2. A citation is a document, a page and a verbatim quote, and it is taken off the tool's
artifact — never out of the model's prose.** The mechanism is `check_reqs`': every retrieval
tool returns `content_and_artifact`, the model reads a rendering and cites a passage by
**two integers** (`PassageRef`: which search, which `[n]` in its result), and the `Citation`
that reaches the bidder is built from the retrieved object. A model that retypes a quote
changes nothing; a model that cites a passage nobody retrieved cites nothing at all, because
`_resolve` drops a reference that names no passage.

There is a second guarantee the checkpointer hands us for free, and it is worth stating
because it looks like a bug until it is understood: **an artifact comes back from the
checkpoint as a plain `dict`, not as the model it was stored from** (verified against
`JsonPlusSerializer`). So `retrieved_from` recognises nothing on an earlier turn's tool message,
and a reference can only ever resolve against a search made *while answering this question*.
That is the safe direction, it is deliberate, and `prompts/chat.md` tells the model so.

**3. Retrieving nothing is an answer, and it is ours rather than the model's.** When no tool
call in this turn found anything — including when the model made no tool call at all — the
model is not asked for prose. The answer is `NOTHING_FOUND`, fixed, with no citations. A
model invited to write a paragraph after four empty searches writes the most plausible
paragraph it can, and a plausible paragraph about a tender the bidder is deciding whether to
spend three weeks on is the failure this whole codebase is arranged against. The cost is
bluntness on a question that was never about the documents ("hello") and one saved model
call on every question that was.

**4. An answer that cites nothing is visibly uncited, not silently plausible.** When the
structured call returns references that all resolve to nothing, the answer keeps the model's
prose — it may be right — and gains `UNCITED_ANSWER`, exactly as `check_loop` downgrades an
uncited `supported` row and says why in the cell. The bidder sees a paragraph with no
citations *and* a sentence saying it is unverified, which is a different thing from a
paragraph with no citations.

**5. The tool budget is spent, never exceeded, and a batch that would not fit is refused
whole.** `ToolNode` runs a turn's tool calls or none of them, so the routing refuses a batch
that would take the count past `agent.max_tool_calls_per_requirement` rather than letting it
overshoot; the pending calls are answered with `BUDGET_SPENT` messages, because a provider
rejects the next request when a tool call is left dangling. The bound is therefore a property
of the graph rather than of the model's restraint.

**6. The model's draft never enters the transcript.** `ask` returns its message only when it
carries tool calls. The prose the model writes when it has decided to stop is the *draft*,
written before any citation was resolved and before the uncited notice was decided; what the
next turn reads back is the answer the bidder was actually given. Keeping both would teach
the model that its unresolved draft is part of the record, and would pay for it twice in
tokens on every following turn.

The bidder's question is **not** wrapped as a data block. `guards/wrap.py` exists for text
Crossbid did not write and cannot trust to be data; the question is the caller's own
instruction to their own agent, and the operative ask of the turn. What protects the answer
from a bidder who tries to talk their agent into a fabricated citation is not the wrapper —
it is that a citation cannot be produced by prose at all (decision 2). Retrieved passages are
wrapped, by the tools themselves, before the model ever sees them.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Any, Final, Optional, Protocol, TypedDict

from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, ConfigDict, Field

from crossbid.agent.nodes.check_loop import ModelRunnable, ToolTurn, tool_turn
from crossbid.agent.prompts import render
from crossbid.db import ConnectionSource
from crossbid.ingestion.embeddings import EmbeddingsClient
from crossbid.llm import chat_model, resilient
from crossbid.models.review import ChatRole, ChatTurn, Citation
from crossbid.settings import ModelRole, Settings
from crossbid.tools.get_matrix import MatrixDigest
from crossbid.tools.rag import RagHit, RagSearchResult

logger = logging.getLogger(__name__)

CHAT_TOOLS: Final = frozenset({"tender_rag_search", "company_rag_search", "get_matrix"})
"""The tools an *answer about this bid* is made of, which is not the toolbox this deployment
allows (ADR-0052: `enabled_tools` is the operator's permission, this is the node's job).

One question is being answered here: what do this bid's papers say about the thing the
bidder just asked? `tender_rag_search` reads the buyer's documents, `company_rag_search`
reads the bidder's own, and `get_matrix` reads the answer the run already produced — every
question a bidder can sensibly ask about a bid is one of those three.

The three absentees are absent for one shared reason, not three. `ecertis_evidence_lookup`,
`currency_convert` and `search_ted` all return facts that are true and **not citable**: a
register entry, an ECB rate, another buyer's notice. None of them is a passage on a page of
this bid's documents, so an answer resting on one could only ever come back uncited
(decision 4) — a worse experience than not offering the tool. `search_ted` would also put a
live third-party call inside an interactive request, which is the problem ADR-0045 recorded
and ADR-0052 fixed for `check_reqs`.

Not a manifest field, for the reason ADR-0052 gives: which tools a node needs is a fact
about the node's job, and a tool should not have to know the graph to be added to it.
"""

CHAT_MODEL_ROLE: Final = ModelRole.CHEAP
"""The `cheap` slug — `settings.default.yaml` names this role "classification, chat, injection
guard", so this constant is the code agreeing with the file rather than choosing.

It is also the right size for the work. A chat turn reads a few retrieved German passages and
writes three sentences about them; the expensive slug is there for extraction, where one call
has to find every requirement in six pages. At $0.20/1M a bidder can ask twenty questions
about a bid for a fraction of the run that produced it, which is what makes asking rather
than re-reading the cheaper habit."""

FALLBACK_MODEL_ROLE: Final = ModelRole.FALLBACK
"""Where a timed-out call goes after one retry (S3.4.4), on a different vendor by design."""

NODE_NAME: Final = "chat"
"""What the registry calls this caller in a log line about its tools."""

CHAT_PROMPT_NAME: Final = "chat"
BIDDER_LANGUAGE_MARKER: Final = "bidder_language"
TOOL_BUDGET_MARKER: Final = "tool_budget"

CHAT_THREAD_SUFFIX: Final = ":chat"
"""What separates a bid's chat thread from the bid's own. The bid's `thread_id` is read from
its row rather than rebuilt from its id, so there is one definition of `bid:{id}` and this
appends to it (`readmodel.bids.THREAD_ID_PREFIX` writes the other half)."""

MAX_ANSWER_CHARS: Final = 2000
"""A chat bubble, not a report. Three or four paragraphs of German is already more than the
question asked for, and an answer without a bound is a place for a model to put a payload
that some renderer downstream has to survive. `check_loop.MAX_RATIONALE_CHARS` bounds a table
cell at 600 for the same reason and is deliberately a different number: this is a different
surface with a different reader."""

ASK: Final = "ask"
TOOLS: Final = "tools"
BUDGET: Final = "budget"
ANSWER: Final = "answer"
"""Node names. `budget` is the node that answers pending tool calls when the budget cannot
cover them; the loop is `ask ⇄ tools`, and both exits lead to `answer`."""


class ChatError(RuntimeError):
    """A chat turn could not be produced. Never carries document text or a model's words."""


# ------------------------------------------------------------------- what the model answers


class PassageRef(BaseModel):
    """A pointer at a passage a search returned during **this** turn — two integers, no more.

    Deliberately not `check_loop.EvidenceRef`, and the difference is the one sentence that
    matters. A check is one conversation per requirement, so "your tool calls in this
    conversation" is unambiguous there. A chat thread carries every earlier turn's calls, and
    a reference resolved against the wrong turn's retrieval would be a citation of a passage
    that answered a different question — which is exactly the failure a citation exists to
    prevent. The field descriptions are the contract the model is bound with, so the two
    models say different things and are therefore two models.
    """

    model_config = ConfigDict(frozen=True)

    search: int = Field(
        ge=1,
        description=(
            "Which tool call the passage came from, counting only the tool calls you have "
            "made since the current question, from 1, in the order you made them. Tool "
            "calls from earlier turns in this conversation do not count."
        ),
    )
    passage: int = Field(
        ge=1, description="The number in square brackets beside the passage in that result."
    )


class ChatAnswer(BaseModel):
    """One turn's answer as the model returns it, before anything about it is believed.

    Looser than `ChatTurn` on purpose, exactly as `CheckedRequirement` is looser than
    `MatrixRow`: the prose has no length bound here and the references are not yet resolved,
    so one unusable citation costs a citation rather than the whole answer.
    """

    model_config = ConfigDict(frozen=True)

    answer: str = Field(description="The answer to the bidder's question, in their language")
    citations: list[PassageRef] = Field(
        default_factory=list,
        description="The passages you are relying on. An answer with none is unverified.",
    )


# --------------------------------------------------------------------------------- seams

Messages = Sequence[BaseMessage]

AnswerCall = Callable[[Messages], Awaitable[ChatAnswer]]
"""The closing structured call. Separate from `ToolTurn` because it is a different binding
of the same model — tools bound for the loop, a schema bound for the answer — and because a
test scripts the two independently."""


def structured_answer(model: ModelRunnable) -> AnswerCall:
    """Adapt a schema-bound chat model to the `AnswerCall` seam.

    Re-validated rather than trusted: `with_structured_output` may hand back a dict, and
    CLAUDE.md's rule is that a model's output is schema-validated before use.
    """

    async def call(messages: Messages) -> ChatAnswer:
        return ChatAnswer.model_validate(await model.ainvoke(list(messages)))

    return call


@dataclass(frozen=True, slots=True)
class ChatContext:
    """Everything one chat turn needs, built once per request and never mutated.

    Two callables, a tool list and two numbers, which is what lets every branch below run
    against a scripted model with no provider and no socket — the shape `CheckContext`
    already proved out for the checking loop.
    """

    turn: ToolTurn
    answer: AnswerCall
    tools: tuple[BaseTool, ...]
    max_tool_calls: int
    preamble: tuple[BaseMessage, ...] = ()

    def __post_init__(self) -> None:
        if self.max_tool_calls < 0:
            raise ValueError(f"max_tool_calls cannot be negative, got {self.max_tool_calls}")


ChatUpdate = dict[str, Any]
"""A node's partial state. Plain, because every key here is either a message list, an int or
one `ChatTurn` — there is no second shape worth a name."""


class ChatNode(Protocol):
    """What the graph calls: `(state, config) -> partial state`.

    `Optional[...]` rather than `| None` for the reason every node in this codebase states:
    LangGraph reads the annotation as a string and only that spelling gets `config` injected.
    """

    def __call__(
        self,
        state: ChatState,
        config: Optional[RunnableConfig] = None,  # noqa: UP045
    ) -> Awaitable[ChatUpdate]: ...


class ChatState(TypedDict):
    """The thread's state. `messages` is the transcript; the other two are this turn's.

    `pending` is how many tool calls the last `ask` requested, and it is what the routing
    reads — not the last message. That is what lets `ask` withhold a tool-call-free draft
    from the transcript (decision 6) and still be routed on.

    `answer` is the delivered turn as **plain JSON**, not as a `ChatTurn`, and the reason is
    the checkpointer rather than taste: LangGraph 1.2's msgpack serialiser warns on every
    unregistered class it reads back and says it will refuse them in a future version, so a
    channel holding a Pydantic model is a thread that stops loading after an upgrade.
    `run_chat_turn` validates it on the way out, which is the same split
    `readmodel.bids.BidRow.verdict` makes for the same kind of reason: raw in the store,
    typed at the boundary. It is overwritten every question and nothing reads the stored one.
    """

    messages: Annotated[list[AnyMessage], add_messages]
    pending: int
    answer: dict[str, Any] | None


# ------------------------------------------------------------------------- the fixed text

ANSWER_ASK: Final = (
    "Answer the bidder's question above now, from the passages you retrieved for it. Give "
    "the answer in their language, and a reference to every retrieved passage you are "
    "relying on: `search` counts only the tool calls you made since that question, from 1, "
    "and `passage` is the number in square brackets in that call's result. If what you "
    "retrieved does not settle the question, say so and say what is missing — do not fill "
    "the gap."
)

BUDGET_SPENT: Final = (
    "Not run: your tool budget for this question is spent. Answer from what you have already "
    "retrieved, and say in the answer what is still missing."
)
"""Names nothing but the budget. A tool error message can quote a URL, a row or a document,
and an error built from untrusted input is how untrusted input escapes (ADR-0008)."""

TOOL_FAILED: Final = (
    "That tool could not answer ({error}). The call has been counted against your budget. "
    "Try a different search or answer from what you have; do not assume the evidence exists."
)
"""What `ToolNode` says to the model when a tool raises. The exception's *type* and nothing
else — `ToolNode`'s own default formats `repr(exc)`, and a `ChunkStoreError` or an
`EmbeddingsError` is free to quote what it was given."""

NOTHING_FOUND: Final = (
    "I could not find anything about this in the tender documents, in your own documents or "
    "in this bid's compliance matrix, so I am not going to answer. Everything I say has to "
    "come from a page I can point you at. Try naming the document, the clause or the figure "
    "you have in mind and I will search again."
)
"""Decision 3. English, like every other fixed notice Crossbid writes into a bidder-language
field (`check_loop.UNCITED_SUPPORT` does the same inside a German rationale): the UI is
English in v1, and a half-translated surface reads worse than a consistent one."""

UNCITED_ANSWER: Final = (
    "Shown without citations: nothing retrieved for this question backs the answer above, so "
    "treat it as unverified."
)
"""Decision 4. Appended to the model's own prose rather than replacing it."""

NO_ANSWER: Final = (
    "The model returned an empty answer to this question. Nothing is being shown rather than "
    "a guess; ask again, or ask it a different way."
)

UNCITED_ANSWER_ROOM: Final = MAX_ANSWER_CHARS - len(UNCITED_ANSWER) - 1
"""What the model's own prose gets when the uncited notice is appended to it.

The cap is a cap on the *bubble*, not on the model's half of it: trimming to
`MAX_ANSWER_CHARS` and then appending 110 more characters would put an over-long answer in a
place sized for a short one, which is the thing the cap exists to prevent. The prose gives
way and the notice never does — the notice is the reason the answer has no citations, and
half of it tells the bidder nothing. The same arithmetic, and the same reason, as
`check_loop.UNCITED_SUPPORT_ROOM`."""


# ------------------------------------------------------------- reading a turn's retrievals


@dataclass(frozen=True, slots=True)
class Retrieved:
    """What one tool call came back with: its citable passages, and whether it found anything.

    The two are not the same question, which is why both are here. A `get_matrix` call over a
    bid whose requirements all came from a published DUME finds rows and offers no citable
    passage (those rows have no page — see `tools/get_matrix.py`), and answering "I found
    nothing" to a bidder whose matrix is full would be a lie of exactly the kind decision 3
    exists to prevent.
    """

    citations: tuple[Citation | None, ...]
    found: bool


NOTHING: Final = Retrieved(citations=(), found=False)
"""What a failed, refused or unrecognised tool message contributes: a slot in the numbering,
and no passage in it. The slot is what keeps the model's `[n]` and ours in step — the reason
`check_loop` appends an empty tuple for every call it could not run."""


def _citation_of(hit: RagHit) -> Citation:
    """A retrieved passage as the citation a bidder is shown. No re-derivation: the quote,
    the name and the page are the bytes the store returned (`RagHit.from_match`)."""
    return Citation(
        document_id=hit.document_id,
        document_name=hit.document_name,
        page=hit.page,
        quote=hit.quote,
    )


def retrieved_from(message: ToolMessage) -> Retrieved:
    """What a tool message contributes to this turn's ledger.

    Three shapes and no fourth. A `RagSearchResult` is what the two retrieval tools put on
    the artifact, a `MatrixDigest` is what `get_matrix` puts there, and anything else — a
    failed call, a refused one, an artifact that came back from the checkpoint as a `dict`
    (decision 2) — contributes a numbered slot with nothing citable in it.
    """
    artifact = message.artifact
    if isinstance(artifact, RagSearchResult):
        return Retrieved(
            citations=tuple(_citation_of(hit) for hit in artifact.hits),
            found=bool(artifact.hits),
        )
    if isinstance(artifact, MatrixDigest):
        return Retrieved(citations=artifact.citations, found=bool(artifact.lines))
    return NOTHING


def this_turn(messages: Sequence[BaseMessage]) -> tuple[BaseMessage, ...]:
    """The messages produced since the bidder's most recent question.

    The bidder's question is the only `HumanMessage` this graph ever stores — the closing ask
    is sent to the model and never written to the transcript — so "since the last
    `HumanMessage`" is exactly "since the current question", which is the unit `PassageRef`
    is numbered in.
    """
    for index in range(len(messages) - 1, -1, -1):
        if isinstance(messages[index], HumanMessage):
            return tuple(messages[index + 1 :])
    return tuple(messages)


def ledger_of(messages: Sequence[BaseMessage]) -> tuple[Retrieved, ...]:
    """This turn's tool results in call order — the coordinate system `PassageRef` uses."""
    return tuple(
        retrieved_from(message)
        for message in this_turn(messages)
        if isinstance(message, ToolMessage)
    )


def _resolve(refs: Sequence[PassageRef], ledger: Sequence[Retrieved]) -> tuple[Citation, ...]:
    """Each reference as the passage it names, dropping the ones that name nothing.

    Deduplicated in the order first cited: a model that cites the same passage from two
    searches is citing one piece of paper, and the bidder should be sent to it once. Both
    indexes are 1-based to the model, and a reference past the end of either — an invented
    search, a passage number the result never printed, a clause with no page to cite — is
    dropped with a line in the log rather than repaired into a neighbouring passage.
    """
    found: dict[tuple[str, int, str | None], Citation] = {}
    for ref in refs:
        citation = _citation_at(ref, ledger)
        if citation is None:
            logger.info(
                "Dropped a chat citation of search %d passage %d: no such passage",
                ref.search,
                ref.passage,
            )
            continue
        found.setdefault((citation.document_id, citation.page, citation.quote), citation)
    return tuple(found.values())


def _citation_at(ref: PassageRef, ledger: Sequence[Retrieved]) -> Citation | None:
    """The passage a reference points at, or `None`."""
    if ref.search > len(ledger):
        return None
    citations = ledger[ref.search - 1].citations
    if ref.passage > len(citations):
        return None
    return citations[ref.passage - 1]


def _tool_calls_spent(messages: Sequence[BaseMessage]) -> int:
    """How much of this turn's budget is gone. One answered tool call, one `ToolMessage` —
    including the failed and the refused ones, which is what keeps this count and the
    model's own numbering of its searches in step."""
    return sum(1 for message in this_turn(messages) if isinstance(message, ToolMessage))


# --------------------------------------------------------------------------- the delivery


def _bounded(prose: str, limit: int = MAX_ANSWER_CHARS) -> str:
    """The bidder's answer: trimmed, bounded, and never empty. See `MAX_ANSWER_CHARS`."""
    return prose.strip()[:limit] or NO_ANSWER


def deliver(answer: ChatAnswer, ledger: Sequence[Retrieved]) -> ChatTurn:
    """The model's answer as the turn the bidder is shown, with its citations resolved.

    The uncited case is decision 4, applied here rather than left to a renderer: an answer
    whose references all named nothing keeps its prose and gains the notice that says so, and
    the notice never gives way to the prose (`UNCITED_ANSWER_ROOM`).
    """
    citations = _resolve(answer.citations, ledger)
    if not citations:
        prose = f"{_bounded(answer.answer, UNCITED_ANSWER_ROOM)} {UNCITED_ANSWER}"
        return ChatTurn(role=ChatRole.ASSISTANT, content=prose, citations=())
    return ChatTurn(
        role=ChatRole.ASSISTANT, content=_bounded(answer.answer), citations=citations
    )


def nothing_found() -> ChatTurn:
    """The turn a question gets when no search found anything. Decision 3."""
    return ChatTurn(role=ChatRole.ASSISTANT, content=NOTHING_FOUND, citations=())


# ------------------------------------------------------------------------------ the nodes


def build_ask(context: ChatContext) -> ChatNode:
    """The `ask` node: one turn of the loop, and how many tools it wants next."""

    async def ask(
        state: ChatState,
        # `Optional[...]`, not `RunnableConfig | None`: LangGraph matches this annotation as
        # a *string* under postponed annotations and the modern spelling is silently never
        # injected (CLAUDE.md).
        config: Optional[RunnableConfig] = None,  # noqa: UP045
    ) -> ChatUpdate:
        """Ask the tool-bound model what to do next.

        The preamble is prepended to the outgoing messages and never stored: the system
        prompt and the task are ours, they are identical on every turn, and writing them into
        the transcript would checkpoint the same two kilobytes once per question and pin the
        thread to the prompt version that started it.

        A message with no tool calls is deliberately dropped (decision 6): it is the draft,
        and `pending == 0` is what routes past it.
        """
        answer = await context.turn([*context.preamble, *state["messages"]])
        calls = len(answer.tool_calls)
        return {"messages": [answer] if calls else [], "pending": calls}

    return ask


def refuse_batch(state: ChatState) -> ChatUpdate:
    """The `budget` node: answer every pending tool call with "not run", and move on.

    A provider rejects the next request when a tool call is left unanswered, so a batch the
    budget cannot cover is refused *in writing* rather than ignored. Reached only from the
    routing, which means the last message carries tool calls.
    """
    last = state["messages"][-1]
    calls = last.tool_calls if isinstance(last, AIMessage) else []
    return {
        "messages": [
            ToolMessage(
                content=BUDGET_SPENT,
                tool_call_id=str(call.get("id") or f"call-{index}"),
                name=str(call.get("name") or ""),
            )
            for index, call in enumerate(calls, start=1)
        ],
        "pending": 0,
    }


def build_answer(context: ChatContext) -> ChatNode:
    """The `answer` node: the closing structured call, or the honest refusal to make one."""

    async def answer(
        state: ChatState,
        config: Optional[RunnableConfig] = None,  # noqa: UP045
    ) -> ChatUpdate:
        """One `ChatTurn`, appended to the transcript as the assistant's word.

        The ledger is read from the messages of *this* turn only, in tool-call order, which
        is the coordinate system the model was told to cite in. When it holds nothing found,
        the model is never asked for prose (decision 3) and the turn costs one call less.
        """
        messages = state["messages"]
        ledger = ledger_of(messages)
        if not any(result.found for result in ledger):
            turn = nothing_found()
        else:
            asked = [*context.preamble, *messages, HumanMessage(content=ANSWER_ASK)]
            turn = deliver(await context.answer(asked), ledger)
        return {
            "messages": [AIMessage(content=turn.content)],
            "answer": turn.model_dump(mode="json"),
            "pending": 0,
        }

    return answer


def route(state: ChatState, *, budget: int) -> str:
    """Where the loop goes after `ask`: answer, run the tools, or refuse the batch.

    The budget test is `spent + pending > budget`, not `spent >= budget`, and the difference
    is decision 5: `ToolNode` runs a batch or none of it, so a batch that would overshoot is
    refused whole. The budget is therefore spent and never exceeded, which is the promise
    `agent.max_tool_calls_per_requirement` makes everywhere else in this codebase.
    """
    pending = state.get("pending", 0)
    if pending <= 0:
        return ANSWER
    if _tool_calls_spent(state["messages"]) + pending > budget:
        return BUDGET
    return TOOLS


# --------------------------------------------------------------------------- the building


def build_chat_graph(
    context: ChatContext, *, checkpointer: BaseCheckpointSaver[Any] | None = None
) -> CompiledStateGraph[Any, Any, Any, Any]:
    """`START → ask ⇄ tools → answer → END`, compiled on the thread's checkpointer.

    `ToolNode` runs the tools rather than a loop written here, and its error handling is
    replaced with one that names the exception's *type* and nothing else: the default
    formats `repr(exc)`, and a retrieval error is free to quote the row or the URL it
    failed on (ADR-0008).

    `checkpointer=None` compiles a graph with no memory, which is what a test that only
    wants one turn uses; production passes `db.checkpointer` and a `bid:{id}:chat` thread.
    """
    builder: StateGraph[ChatState] = StateGraph(ChatState)
    builder.add_node(ASK, build_ask(context))
    builder.add_node(
        TOOLS,
        ToolNode(
            list(context.tools),
            handle_tool_errors=lambda exc: TOOL_FAILED.format(error=type(exc).__name__),
        ),
    )
    builder.add_node(BUDGET, refuse_batch)
    builder.add_node(ANSWER, build_answer(context))
    builder.add_edge(START, ASK)
    builder.add_conditional_edges(
        ASK,
        lambda state: route(state, budget=context.max_tool_calls),
        [TOOLS, BUDGET, ANSWER],
    )
    builder.add_edge(TOOLS, ASK)
    builder.add_edge(BUDGET, ANSWER)
    builder.add_edge(ANSWER, END)
    return builder.compile(checkpointer=checkpointer)


def chat_thread_id(bid_thread_id: str) -> str:
    """The chat thread for a bid whose own thread is `bid_thread_id`.

    Derived from the bid row's `thread_id` rather than rebuilt from the bid id, so there is
    exactly one definition of `bid:{id}` in the system and this only says what is appended
    to it. A run and its chat must never collide on one thread: the bid's checkpoint holds
    an interrupt a reviewer resumes, and a chat turn written into it would be a message
    where `BidState` expects a matrix.
    """
    return f"{bid_thread_id}{CHAT_THREAD_SUFFIX}"


def preamble_for(settings: Settings, *, bidder_language: str) -> tuple[BaseMessage, ...]:
    """The standing instructions for a chat thread: the system prompt, then the task.

    Two system messages rather than one string, because they come from two places an
    operator edits separately — `app_settings.system_prompt` and `prompts/chat.md` — and a
    concatenation would make a diff of either look like a change to both.
    """
    task = render(
        CHAT_PROMPT_NAME,
        {
            BIDDER_LANGUAGE_MARKER: bidder_language,
            TOOL_BUDGET_MARKER: str(settings.runtime.agent.max_tool_calls_per_requirement),
        },
    )
    system = settings.runtime.system_prompt
    standing: list[BaseMessage] = [] if system is None else [SystemMessage(content=system)]
    return (*standing, SystemMessage(content=task))


@asynccontextmanager
async def openrouter_chat(
    settings: Settings, db: ConnectionSource, *, company_id: str, bid_id: str, language: str
) -> AsyncIterator[ChatContext]:
    """The production context: one embeddings client, the enabled tools, two bindings.

    The two bindings are the same slug twice — tools bound for the loop, the answer schema
    bound for the closing call — so a settings change cannot give the loop and the answer
    different models. Each is wrapped in `resilient`, so a timed-out turn *or* a timed-out
    answer is retried once and then asked of the fallback slug (S3.4.4).

    The client is opened for the turn and closed with it: both RAG tools embed their query,
    and a tool left to build its own would open an `httpx` pool closed by garbage collection
    — the reason `ToolContext` carries an `embedder` at all (S3.3.1).

    A schema violation is deliberately **not** re-asked here, unlike `check_loop`, and the
    asymmetry is the cost of a retry: re-asking a requirement saves a row out of two hundred
    on a run that has already spent a euro, where a chat turn costs a cent and the bidder is
    sitting in front of it. A malformed answer becomes a 500 and the bidder asks again.
    """
    # Imported here rather than at module scope: `registry` walks and imports every tool
    # module, and a graph that dragged the whole tool package into its import graph would
    # make `agent/` depend on `tools/` at import time as well as at run time.
    from crossbid.tools.manifest import ToolContext
    from crossbid.tools.registry import build_enabled_tools

    async with EmbeddingsClient(settings) as embedder:
        tools = build_enabled_tools(
            ToolContext(
                settings=settings,
                company_id=company_id,
                bid_id=bid_id,
                db=db,
                embedder=embedder,
            ),
            settings,
            needed=CHAT_TOOLS,
            caller=NODE_NAME,
        )
        model = chat_model(CHAT_MODEL_ROLE, settings)
        spare = chat_model(FALLBACK_MODEL_ROLE, settings)
        yield ChatContext(
            turn=tool_turn(resilient(model.bind_tools(tools), spare.bind_tools(tools))),
            answer=structured_answer(
                resilient(
                    model.with_structured_output(ChatAnswer),
                    spare.with_structured_output(ChatAnswer),
                )
            ),
            tools=tools,
            max_tool_calls=settings.runtime.agent.max_tool_calls_per_requirement,
            preamble=preamble_for(settings, bidder_language=language),
        )


async def run_chat_turn(
    graph: CompiledStateGraph[Any, Any, Any, Any], *, question: str, thread_id: str
) -> ChatTurn:
    """Ask one question on one thread and return the answer that was delivered.

    Re-validated on the way out for the reason every boundary in this codebase re-validates:
    the value comes back through a channel the checkpointer also writes, and a turn that
    reached the bidder without a `role` or with an unbounded `content` would be a contract
    break nobody upstream would notice.
    """
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content=question)], "pending": 0, "answer": None},
        {"configurable": {"thread_id": thread_id}},
    )
    delivered = result.get("answer")
    if delivered is None:  # pragma: no cover - the answer node always writes one
        raise ChatError("the chat graph finished without an answer")
    return ChatTurn.model_validate(delivered)
