"""S3.3.1 — the agentic core: one requirement, one small ReAct loop, one matrix row.

**This is the agentic part of Crossbid, and the only one.** The outer graph is a
deterministic workflow with a human interrupt (`agent/graph.py`): fixed edges, no model
choosing what runs next. Inside here a model decides what to search for, reads what came
back, decides whether to search again, and then answers — a ReAct loop, bounded by
`agent.max_tool_calls_per_requirement` and by nothing else. `check_reqs.py` is the node that
runs this over a lane of requirements; this module is one requirement's worth of it and
touches neither the database nor the graph state, which is what makes every branch below
testable against a scripted model and no sockets.

Six decisions carry this module.

**1. Evidence comes off the tool's artifact, never out of the model's prose.** This is the
product's central safety promise ("every matrix cell carries a citation or is marked
partially supported") and the one place it could be lost. A retrieval tool returns
`content_and_artifact`: the model reads `RagSearchResult.render()`, and the typed
`RagSearchResult` rides along on the `ToolMessage.artifact` (S2.4.2). The loop keeps those
artifacts in call order; the model's verdict cites a passage by **two integers**
(`EvidenceRef`: which tool call, which `[n]` in its result), and `RagHit.as_evidence()` is
what becomes `MatrixRow.evidence`. So a quote, a document name and a page in the matrix are
bytes the retrieval returned — a model that retypes a quote changes nothing, and a model
that cites a passage nobody retrieved cites nothing at all.

**2. The budget is spent, not exceeded, and running out is an answer.** `searches` is both
the record of what was retrieved and the counter: it grows by one for *every* tool call the
model made, refused and failed ones included, which is what keeps its indexes and the
model's own numbering in step (decision 1). Each turn's calls run until the budget is gone
and the remainder are answered with a `ToolMessage` saying so, because a provider rejects
the next request if any tool call is left unanswered. When the budget is gone the loop stops
asking and makes the verdict call — the story's "no requirement uses more than N tool calls"
is therefore a property of that counter and not of the model's restraint.

**3. Nothing here raises, and every requirement gets a row.** A tool that fails, a model that
will not answer, a section the wrapper cannot wrap, a verdict that does not validate: all of
them land as `partially_supported` with a rationale naming the failure's *type*, which is
what sends the requirement to the reviewer instead of losing it. The alternative — an
exception out of a lane — would take a few hundred finished rows down with it.

**4. A requirement that is not a company property never reaches the model.** ADR-0003
measured this: SP.1's first checking round answered `unclear` for all eight rows it tried,
because they were all duties to *submit a form*, and no corpus of company facts can
establish "we attached Annex 4". Those rows are `partially_supported` by construction, with
a rationale that tells the reviewer what to attach, and they cost nothing. At the DE pack's
scale that is the difference between checking fitting the $2.50 run budget and not.

**5. The eCertis mapping is looked up in code, not asked for.** `lookup_evidence` is total
and reads a committed cache, so the story's "eCertis evidence when a criterion id is set" is
a guarantee rather than a thing a model might remember to do — and it costs no tool call.
The bidder's country comes from the company profile, so a French tender's criterion resolves
to the German paper a German bidder actually files: that is the cross-border wedge, and it is
deterministic. The tool stays bound as well, for a criterion the model works out for itself.

**6. The requirement's own text is untrusted and is wrapped; the eCertis answer is not.**
`source_text` is quoted verbatim out of a tender PDF, so it reaches the model inside one
`wrap_as_data` block with its own `DOCUMENT` header (S2.3.2, ADR-0009) and the operative ask
comes after it. Retrieved passages are already wrapped by the tool itself, and this module
never re-renders `hit.quote` into a prompt — the artifact is read for its metadata only. The
eCertis lines are stated plainly because they are not document text: they are the European
Commission's own register, shipped in this repository as a reviewed JSON cache, and wrapping
them as a `DOCUMENT` would claim a citable page they do not have.

The model's `rationale` is prose written *about* untrusted text and is shown to a human, so
it is trimmed to `MAX_RATIONALE_CHARS` on the way out: the reviewer needs two sentences, and
a six-thousand-character "rationale" is a payload looking for a renderer.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Protocol

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from crossbid.agent.prompts import render
from crossbid.guards.wrap import DataBlock, wrap_as_data
from crossbid.models.matrix import EcertisEvidence, Evidence, MatrixRow, RowStatus
from crossbid.models.requirement import Checkability, Requirement
from crossbid.reference.ecertis_lookup import lookup_evidence
from crossbid.tools.ecertis_evidence import to_matrix_evidence
from crossbid.tools.rag import RagHit, RagSearchResult

logger = logging.getLogger(__name__)

CHECK_PROMPT_NAME: Final = "check"
BIDDER_COUNTRY_MARKER: Final = "bidder_country"
BIDDER_LANGUAGE_MARKER: Final = "bidder_language"
TOOL_BUDGET_MARKER: Final = "tool_budget"

MATRIX_ROW_ID_NAMESPACE: Final = uuid.UUID("0f2c8a91-5d3e-4b07-9c16-7a48e2b5d310")
"""Namespace for the `uuid5` a matrix row's id is, taken over the requirement id alone.

Deterministic for the same reason `extract_reqs.REQUIREMENT_ID_NAMESPACE` is: a resumed run
re-checking a requirement must *update* its row rather than add a second one, and
`matrix_rows` carries a unique index on `requirement_id` that a random id would collide with
on the second write. One row per requirement is the table's shape, so the requirement id is
the whole key.
"""

MAX_RATIONALE_CHARS: Final = 600
"""Two or three sentences. See the module docstring for why it is bounded at all."""

UNKNOWN_COUNTRY: Final = "zz"
"""What an unresolved bidder country is looked up as. `lookup_evidence` normalises anything
it cannot read to this already; passing it explicitly keeps the intent visible here."""


class CheckError(RuntimeError):
    """The check could not be completed. Never carries document text or a model's words."""


# ------------------------------------------------------------------- what the model answers


class EvidenceRef(BaseModel):
    """A pointer at a passage a search returned — two integers, and nothing else.

    The whole safety argument of this module is in the smallness of this object: a citation
    the model writes cannot contain a quote, a page or a document name, so it cannot contain
    an invented one either.
    """

    model_config = ConfigDict(frozen=True)

    search: int = Field(
        ge=1,
        description=(
            "Which tool call the passage came from, counting your tool calls in this "
            "conversation from 1 in the order you made them."
        ),
    )
    passage: int = Field(
        ge=1, description="The number in square brackets beside the passage in that result."
    )


class CheckedRequirement(BaseModel):
    """One requirement's verdict as the model returns it, before anything is believed.

    Looser than `MatrixRow` on purpose, exactly as `ExtractedRequirement` is looser than
    `Requirement`: the rationale has no length bound here and the references are not yet
    resolved, so one unusable citation costs a citation rather than the whole verdict.
    """

    model_config = ConfigDict(frozen=True)

    status: RowStatus = Field(description="Your finding for this requirement")
    rationale: str = Field(
        description="One or two sentences for the reviewer: what you found, what it settles"
    )
    evidence: list[EvidenceRef] = Field(
        default_factory=list,
        description="The passages you are citing. Required for 'supported'.",
    )


# --------------------------------------------------------------------------------- seams

Messages = Sequence[BaseMessage]

ToolTurn = Callable[[Messages], Awaitable[AIMessage]]
"""One turn of the loop: the tool-bound model, asked what to do next."""

VerdictCall = Callable[[Messages], Awaitable[CheckedRequirement]]
"""The closing structured call. Separate from `ToolTurn` because it is a different binding
of the same model — tools bound for the loop, a schema bound for the answer — and because a
test scripts the two independently."""


class ModelRunnable(Protocol):
    """The slice of a LangChain runnable this module uses. See `extract_reqs` for why."""

    async def ainvoke(self, messages: Any, /) -> Any: ...


def tool_turn(model: ModelRunnable) -> ToolTurn:
    """Adapt a tool-bound chat model to the `ToolTurn` seam.

    The type is checked rather than assumed: `bind_tools(...).ainvoke` is typed as returning
    a `BaseMessage`, and everything below reads `.tool_calls`, which only an `AIMessage` has.
    """

    async def turn(messages: Messages) -> AIMessage:
        answer = await model.ainvoke(list(messages))
        if not isinstance(answer, AIMessage):
            raise CheckError(f"the model answered with a {type(answer).__name__}, not a turn")
        return answer

    return turn


def structured_verdict(model: ModelRunnable) -> VerdictCall:
    """Adapt a schema-bound chat model to the `VerdictCall` seam.

    Re-validated rather than trusted: `with_structured_output` may hand back a dict, and
    CLAUDE.md's rule is that a model's output is schema-validated before use.
    """

    async def call(messages: Messages) -> CheckedRequirement:
        return CheckedRequirement.model_validate(await model.ainvoke(list(messages)))

    return call


@dataclass(frozen=True, slots=True)
class Bidder:
    """Who is being checked: where they are established, and what they read.

    `country` decides which national evidence eCertis names, which is the cross-border
    wedge; `language` decides what the rationale is written in. Both come from the company
    profile (S2.4.1), never from the tender.
    """

    country: str
    language: str


@dataclass(frozen=True, slots=True)
class CheckContext:
    """Everything one lane's checking needs, built once per lane and never mutated.

    Holds no per-requirement state: the loop below is a pure function of this and one
    `Requirement`, which is what lets a lane run hundreds of requirements through one
    context and a test run one requirement through a hand-built one.
    """

    turn: ToolTurn
    verdict: VerdictCall
    tools: Mapping[str, BaseTool]
    max_tool_calls: int
    bidder: Bidder
    system_prompt: str | None = None

    def __post_init__(self) -> None:
        if self.max_tool_calls < 0:
            raise ValueError(f"max_tool_calls cannot be negative, got {self.max_tool_calls}")


# ------------------------------------------------------------------------- the fixed text

CLOSING_ASK: Final = (
    "That is the requirement. Search for what would settle it, then answer with a status, a "
    "rationale for the reviewer, and references to the passages you retrieved. Cite only "
    "passages a search returned, by the two numbers described above."
)
"""The operative instruction, after the block. See `guards/wrap.py` on why it goes there."""

VERDICT_ASK: Final = (
    "Answer now for the requirement in the data block above: a status, a rationale of one or "
    "two sentences for the reviewer, and a reference to every retrieved passage you are "
    "relying on — `search` counts your tool calls in this conversation from 1, `passage` is "
    "the number in square brackets in that call's result. Use 'supported' only if you are "
    "citing at least one passage."
)

BUDGET_SPENT_ASK: Final = (
    "Your tool budget for this requirement is spent. Answer from what you have already "
    "retrieved, and say in the rationale what is still missing."
)

ECERTIS_FOUND: Final = (
    "eCertis records, for the EU criterion this requirement maps to ({criterion}), that a "
    "bidder established in {country} proves it with: {documents}. That is the register's "
    "answer, not the bidder's — it names the paper to file, and says nothing about whether "
    "this bidder holds it."
)
ECERTIS_EMPTY: Final = (
    "eCertis records no national document for {country} against the EU criterion this "
    "requirement maps to ({criterion}). That is a normal answer for many criteria, and it is "
    "not evidence either way."
)
"""Stated plainly, outside any block: see decision 6 in the module docstring."""

TOOL_FAILED: Final = (
    "The tool '{tool}' could not answer ({error}). This call has been counted against your "
    "budget. Try a different search or answer from what you have; do not assume the evidence "
    "exists."
)
UNKNOWN_TOOL: Final = (
    "There is no tool called '{tool}'. This call has been counted against your budget. Use "
    "one of the tools you were given."
)
BUDGET_REFUSED: Final = (
    "Not run: your tool budget for this requirement is already spent. Answer from what you "
    "have retrieved so far."
)
"""Every one of these names a tool and an exception *type* and nothing else. A tool error
message can quote a URL, a row or a document, and an error built from untrusted input is how
untrusted input escapes (ADR-0008)."""

NOT_COMPANY_PROPERTY: Final = (
    "This requirement is not a property of the company that evidence can settle — it is a "
    "duty to submit or declare something with the offer — so it is left for the reviewer to "
    "confirm rather than guessed at. See the quoted clause for what has to be attached."
)
CHECK_FAILED: Final = (
    "This requirement could not be checked: the attempt failed with {error}. It is left for "
    "the reviewer rather than answered, and the failure is in the run's log."
)
UNCITED_SUPPORT: Final = (
    "Recorded as partially supported rather than supported: the answer cited no retrieved "
    "passage, and an uncited claim is not evidence."
)
NO_RATIONALE: Final = "The check returned no rationale, so there is nothing to show here."


# ----------------------------------------------------------------------------- the check


async def check_requirement(requirement: Requirement, context: CheckContext) -> MatrixRow:
    """One requirement's matrix row. Total: it answers for every requirement, always.

    The three exits are the module docstring's decisions 3, 4 and 5 in order: a requirement
    evidence cannot settle never reaches the model, a failure becomes a row addressed to the
    reviewer, and the eCertis mapping is attached either way.
    """
    ecertis = ecertis_evidence_for(requirement, context.bidder)
    if requirement.checkable is not Checkability.COMPANY_PROPERTY:
        return _row(requirement, RowStatus.PARTIALLY_SUPPORTED, NOT_COMPANY_PROPERTY, ecertis)

    try:
        answer, searches = await _react(requirement, context, ecertis)
    except Exception as exc:
        # Deliberately broad and deliberately loud: a defect here is a bug a maintainer has
        # to see, and a lane that raised would lose every row it had already finished.
        logger.exception("Checking requirement %s failed", requirement.id)
        reason = CHECK_FAILED.format(error=type(exc).__name__)
        return _row(requirement, RowStatus.PARTIALLY_SUPPORTED, reason, ecertis)

    return _verdict_row(requirement, answer, searches, ecertis)


def ecertis_evidence_for(requirement: Requirement, bidder: Bidder) -> EcertisEvidence | None:
    """Which national paper proves this requirement's criterion, for this bidder.

    `None` when the requirement carries no criterion, which is most of them. Otherwise
    always an answer: `lookup_evidence` is total by construction (five ways of having
    nothing to say, all of them `not_found`), and `to_matrix_evidence` normalises a country
    it could not read to `zz`, so nothing here can raise and nothing costs a tool call.
    """
    criterion_id = requirement.ecertis_criterion_id
    if criterion_id is None:
        return None
    country = bidder.country.strip().lower() or UNKNOWN_COUNTRY
    return to_matrix_evidence(
        criterion_id, lookup_evidence(criterion_id, country, bidder.language)
    )


# ------------------------------------------------------------------------- the ReAct loop


async def _react(
    requirement: Requirement, context: CheckContext, ecertis: EcertisEvidence | None
) -> tuple[CheckedRequirement, tuple[tuple[RagHit, ...], ...]]:
    """Search, read, decide, repeat until the budget is gone; then answer.

    Returns the verdict and the retrieved passages **in tool-call order**, which is the
    coordinate system `EvidenceRef.search` is expressed in — a call that returned no
    passages (the eCertis lookup, a failure, a refusal) contributes an empty tuple so that
    the numbering the model sees and the numbering resolved here cannot drift apart.
    """
    messages: list[BaseMessage] = _opening_messages(requirement, context, ecertis)
    searches: list[tuple[RagHit, ...]] = []

    while len(searches) < context.max_tool_calls:
        answer = await context.turn(messages)
        messages.append(answer)
        if not answer.tool_calls:
            break
        for call in answer.tool_calls:
            message, hits = await _run_call(call, context, spent=len(searches))
            searches.append(hits)
            messages.append(message)

    messages.append(HumanMessage(content=_verdict_ask(len(searches), context.max_tool_calls)))
    return await context.verdict(messages), tuple(searches)


async def _run_call(
    call: Mapping[str, Any], context: CheckContext, *, spent: int
) -> tuple[ToolMessage, tuple[RagHit, ...]]:
    """Run one tool call, or say why it did not run. Always returns a `ToolMessage`.

    Every tool call the model made is answered, whatever happened — a provider rejects the
    next request when one is left dangling, so swallowing a failure here would end the
    conversation rather than the call.
    """
    call_id = str(call.get("id") or f"call-{spent + 1}")
    name = str(call.get("name") or "")
    if spent >= context.max_tool_calls:
        return ToolMessage(content=BUDGET_REFUSED, tool_call_id=call_id, name=name), ()

    tool = context.tools.get(name)
    if tool is None:
        logger.warning("The model asked for an unbound tool: %s", name)
        content = UNKNOWN_TOOL.format(tool=name)
        return ToolMessage(content=content, tool_call_id=call_id, name=name), ()

    try:
        message = await tool.ainvoke(dict(call))
    except Exception as exc:
        logger.warning("Tool %s failed: %s", name, type(exc).__name__)
        content = TOOL_FAILED.format(tool=name, error=type(exc).__name__)
        return ToolMessage(content=content, tool_call_id=call_id, name=name), ()

    if not isinstance(message, ToolMessage):
        # `ainvoke` with a tool call returns a `ToolMessage`; anything else is a tool that
        # broke the contract, and the loop still owes the model an answer.
        content = TOOL_FAILED.format(tool=name, error=type(message).__name__)
        return ToolMessage(content=content, tool_call_id=call_id, name=name), ()
    return message, _hits_of(message)


def _hits_of(message: ToolMessage) -> tuple[RagHit, ...]:
    """The retrieved passages a tool message carries, or none.

    `content_and_artifact` is what puts a `RagSearchResult` here; `ecertis_evidence_lookup`
    returns a plain dict and so contributes nothing citable, which is correct — an eCertis
    answer is not a passage in anybody's document.
    """
    artifact = message.artifact
    return artifact.hits if isinstance(artifact, RagSearchResult) else ()


def _verdict_ask(spent: int, budget: int) -> str:
    """The closing question, plus a sentence when the budget is what stopped the loop."""
    if spent >= budget:
        return f"{BUDGET_SPENT_ASK}\n\n{VERDICT_ASK}"
    return VERDICT_ASK


# ------------------------------------------------------------------------------ the prompt


def _opening_messages(
    requirement: Requirement, context: CheckContext, ecertis: EcertisEvidence | None
) -> list[BaseMessage]:
    """System prompt, then task, then the requirement as data, then the ask.

    One `DataBlock` holding the verbatim clause, headed with the document and page the
    citation will carry, so the page a reviewer is sent to comes from *us* and never from
    the document's own text (ADR-0009). `DataWrapError` is left to propagate: it means the
    wrapper could not mint a tag this clause does not contain, and `check_requirement`'s
    handler turns it into a row for the reviewer rather than a prompt the clause can forge.
    """
    wrapped = wrap_as_data(
        DataBlock(
            text=requirement.source_text,
            label=requirement.document_name,
            pages=(requirement.page,),
        )
    )
    task = render(
        CHECK_PROMPT_NAME,
        {
            BIDDER_COUNTRY_MARKER: context.bidder.country or UNKNOWN_COUNTRY,
            BIDDER_LANGUAGE_MARKER: context.bidder.language,
            TOOL_BUDGET_MARKER: str(context.max_tool_calls),
        },
    )
    parts = [task, wrapped.text, *_ecertis_note(ecertis), CLOSING_ASK]
    system: list[BaseMessage] = (
        [] if context.system_prompt is None else [SystemMessage(content=context.system_prompt)]
    )
    return [*system, HumanMessage(content="\n\n".join(parts))]


def _ecertis_note(evidence: EcertisEvidence | None) -> tuple[str, ...]:
    """What the register says about this requirement's criterion, or nothing at all.

    The same object the row will carry, looked up once per requirement rather than once for
    the prompt and once for the row: the cache read is cheap, but two lookups are two places
    for the prompt and the matrix to disagree about what eCertis said."""
    if evidence is None:
        return ()
    if not evidence.found:
        note = ECERTIS_EMPTY.format(country=evidence.country, criterion=evidence.criterion_name)
        return (note,)
    documents = "; ".join(evidence.evidence_names)
    return (
        ECERTIS_FOUND.format(
            criterion=evidence.criterion_name, country=evidence.country, documents=documents
        ),
    )


# -------------------------------------------------------------------------------- the row


def _verdict_row(
    requirement: Requirement,
    answer: CheckedRequirement,
    searches: Sequence[Sequence[RagHit]],
    ecertis: EcertisEvidence | None,
) -> MatrixRow:
    """The model's verdict as a row, with the citations resolved against what was retrieved.

    The downgrade is the invariant `MatrixRow` would otherwise raise on, applied here rather
    than caught there: a `supported` the model cannot back with a retrieved passage becomes
    `partially_supported`, which sends it to the reviewer instead of counting towards a `go`.
    """
    evidence = _resolve(answer.evidence, searches)
    status = answer.status
    rationale = _rationale(answer.rationale)
    if status is RowStatus.SUPPORTED and not evidence:
        status = RowStatus.PARTIALLY_SUPPORTED
        rationale = f"{rationale} {UNCITED_SUPPORT}"
    return _row(requirement, status, rationale, ecertis, evidence=evidence)


def _resolve(
    refs: Iterable[EvidenceRef], searches: Sequence[Sequence[RagHit]]
) -> tuple[Evidence, ...]:
    """Each reference as the passage it names, dropping the ones that name nothing.

    Deduplicated in the order first cited: a model that cites the same passage from two
    searches is citing one piece of paper, and the reviewer should see it once.
    """
    found: dict[tuple[str, int, str], Evidence] = {}
    for ref in refs:
        hit = _hit_at(ref, searches)
        if hit is None:
            logger.info(
                "Dropped a citation of search %d passage %d: no such passage",
                ref.search,
                ref.passage,
            )
            continue
        evidence = hit.as_evidence()
        found.setdefault((evidence.document_id, evidence.page, evidence.quote), evidence)
    return tuple(found.values())


def _hit_at(ref: EvidenceRef, searches: Sequence[Sequence[RagHit]]) -> RagHit | None:
    """The passage a reference points at, or `None`. Both indexes are 1-based to the model."""
    if ref.search > len(searches):
        return None
    hits = searches[ref.search - 1]
    if ref.passage > len(hits):
        return None
    return hits[ref.passage - 1]


def _rationale(text: str) -> str:
    """The reviewer's sentence: trimmed, bounded, and never empty. See the module docstring."""
    return text.strip()[:MAX_RATIONALE_CHARS] or NO_RATIONALE


def _row(
    requirement: Requirement,
    status: RowStatus,
    rationale: str,
    ecertis: EcertisEvidence | None,
    *,
    evidence: tuple[Evidence, ...] = (),
) -> MatrixRow:
    """One row, on the deterministic id a resumed run will upsert over."""
    return MatrixRow(
        id=matrix_row_id(requirement.id),
        requirement_id=requirement.id,
        status=status,
        evidence=evidence,
        ecertis_evidence=ecertis,
        agent_rationale=rationale,
    )


def matrix_row_id(requirement_id: str) -> str:
    """A requirement's matrix row id — see `MATRIX_ROW_ID_NAMESPACE`."""
    return str(uuid.uuid5(MATRIX_ROW_ID_NAMESPACE, requirement_id))
