"""S3.3.1 — `plan_checks` and `check_reqs`: the fan-out, and one lane of ReAct loops.

Two nodes, and the split is the whole design. `plan_checks` is deterministic workflow: it
resolves who the bidder is and writes it to the state. `check_reqs` is **the agentic node** —
each requirement it holds runs its own small ReAct loop with a bounded tool budget
(`check_loop.py`). Between them sits a `Send` fan-out, and `graph.py` wires it.

Four decisions.

**1. The fan-out is by lane, not by requirement, and that is what bounds concurrency.**
`lanes_of` deals the requirements round-robin into exactly `min(check_concurrency, n)`
lanes, and the graph emits one `Send` per lane. So "no more than N run concurrently" is a
property of *how many Sends exist* — there is no semaphore, no shared object, and nothing
that has to be re-established when a run resumes from a checkpoint. Two other things follow
from it and neither is incidental. A `Send` per requirement would be 258 LangGraph tasks
each writing a checkpoint, and `AsyncPostgresSaver` serialises every operation on one
`asyncio.Lock` however large the pool is (CLAUDE.md), so the fan-out would spend its
afternoon queueing on that lock; five lanes are five writes. And a lane is a scope with a
beginning and an end, which is where the run's HTTP client can live (decision 2).

Round-robin rather than contiguous slices: requirements arrive in document-and-page order,
and one document's requirements are alike in cost, so contiguous slices would hand one lane
the whole annex of cheap formalities and another the selection criteria.

**2. One `EmbeddingsClient` per lane, injected through the `ToolContext`.** Every retrieval
tool embeds its query, and `build_rag_tool` takes a client rather than making one
(S2.4.2) — but `registry.build_enabled_tools` builds each tool from a `ToolContext` and
passes no `embedder=`, so left to itself each tool would construct its own and each would
open its own `httpx` pool, closed by garbage collection. Three ways out were available: widen
`ToolContext`, add a parameter to `build_enabled_tools`, or accept the default. Widening the
context won because the context *is* the scope object — it already carries the tenant, the
bid and the database for exactly this reason, and the alternative would have put a tool
concern into the registry's signature, where every future tool would have to ignore it. The
field is optional and defaults to `None`, so nothing else that builds a context changes.
The lane opens the client in an `async with` and closes it when the lane ends; a
requirement-scoped client would be 258 pools per run, and a run-scoped one has no close
point once the fan-out has happened.

**3. The bidder's country is state, not a lookup each lane repeats.** `plan_checks` reads
the company profile once, writes `bidder_country`, and the fan-out copies it into every
lane's payload. It is also the field a reviewer needs to understand the answer — "why did it
look up a Freistellungsbescheinigung?" is answered by the checkpoint. A profile that cannot
be read is a blank country rather than a failed run: eCertis then answers `zz` /`not_found`,
which costs the cross-border mapping and nothing else.

**4. A lane never raises.** `check_requirement` is total (see `check_loop.py`), so a lane
returns one row per requirement it was given, whatever happened to any of them. The lane
itself does no database work: the stage wrapper in `graph.py` projects its rows, which is
what makes the matrix appear in the poller lane by lane rather than all at the end.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Final, Optional, Protocol

from langchain_core.runnables import RunnableConfig

from crossbid.agent.nodes.check_loop import (
    Bidder,
    CheckContext,
    CheckedRequirement,
    check_requirement,
    structured_verdict,
    tool_turn,
)
from crossbid.agent.state import (
    BidState,
    CheckPlanUpdate,
    CheckUpdate,
    bidder_language_of,
)
from crossbid.ingestion.embeddings import EmbeddingsClient
from crossbid.llm import chat_model, resilient
from crossbid.models.company import CompanyProfile
from crossbid.models.requirement import Requirement
from crossbid.readmodel.bids import ConnectionSource
from crossbid.readmodel.companies import CompaniesReadModel, CompanyReadModelError
from crossbid.settings import ModelRole, Settings

logger = logging.getLogger(__name__)

UNKNOWN_COUNTRY: Final = ""
"""What `bidder_country` holds when the profile could not be read. `check_loop` turns it
into eCertis's `zz`; an empty string rather than `zz` here so the state says "not known"
rather than asserting a country nobody chose."""

CHECK_MODEL_ROLE: Final = ModelRole.CHEAP
"""The `cheap` slug, and the arithmetic is the argument.

The DE pack yields 258 requirements (ADR-0012) against a $2.50 run budget of which
extraction already spends $1.38. Even at one loop per checkable requirement and a few
thousand tokens of German per turn, `extract`'s slug at $2/1M input would spend the
remainder several times over, where `cheap` at $0.20/1M leaves room for the re-reads a ReAct
loop makes. Checking reads short passages and picks one of four words; it is not the task
the expensive slug is there for. Recorded here rather than assumed: if a `check` role is
ever added to `settings.default.yaml`, this constant is the one line to change.
"""

FALLBACK_MODEL_ROLE: Final = ModelRole.FALLBACK
"""Where a timed-out call goes after one retry (S3.4.4). A different vendor on purpose —
see `llm.RETRYABLE` and the `fallback` entry in `settings.default.yaml`."""

NODE_NAME: Final = "check_reqs"
"""What the registry calls this node in a log line about its tools."""

CHECK_TOOLS: Final = frozenset(
    {
        "company_rag_search",
        "tender_rag_search",
        "ecertis_evidence_lookup",
        "currency_convert",
    }
)
"""The tools a *check* is made of, which is not the same as the tools this deployment allows.

One question is being answered in this loop: does the bidder's evidence satisfy this
requirement? Each of these four is a step in answering it -- find the bidder's evidence,
re-read the clause it has to satisfy, translate a foreign certificate into the national
paper that stands for it, and compare a threshold stated in another currency.

**`search_ted` is the one deliberately absent**, and it is why this constant exists rather
than the node binding everything enabled. It searches for *other tenders*; no answer it can
give bears on whether this company meets this requirement. It was bound here only because
`enabled_tools` listed it and this node took the whole list, which put a live network call
inside a loop that runs once per requirement on a run that has already spent a euro
(ADR-0045, which recorded the problem and left the fix to a graph change -- this is it).

Not a manifest field: which tools a node needs is a fact about the *node's job*, and
`tools/manifest.py` describes tools to an operator. A tool should not have to know the graph
to be added to it.
"""


class CompanyLookup(Protocol):
    """The slice of `CompaniesReadModel` `plan_checks` uses."""

    async def get(self, *, company_id: uuid.UUID) -> CompanyProfile | None: ...


SessionBuilder = Callable[[str, str, Bidder], AbstractAsyncContextManager[CheckContext]]
"""Opens everything a lane needs — the model bindings, the tools, the HTTP client — and
closes it when the lane ends. The seam every unit test replaces: a scripted `CheckContext`
needs no provider, no database and no sockets."""


# ------------------------------------------------------------------------- the fan-out


def lanes_of(
    requirements: Sequence[Requirement], concurrency: int
) -> tuple[tuple[Requirement, ...], ...]:
    """`requirements` dealt round-robin into at most `concurrency` lanes, none of them empty.

    The count *is* the concurrency bound (decision 1), so it is never larger than asked for
    and never larger than there is work for: ten requirements over five lanes is five Sends,
    three requirements over five lanes is three.
    """
    if concurrency < 1:
        raise ValueError(f"concurrency must be at least 1, got {concurrency}")
    lanes = min(concurrency, len(requirements))
    return tuple(tuple(requirements[start::lanes]) for start in range(lanes))


def lane_state(state: BidState, lane: Sequence[Requirement]) -> BidState:
    """One lane's `Send` payload: this lane's requirements, and the run's identity.

    `extraction_problems` travels with it although checking adds none. The stage wrapper
    projects the *accumulated* list on every node's exit, so a lane that arrived without it
    would write an empty problem list over the one extraction reported — the poller would
    watch thirteen problems vanish the moment checking started.
    """
    return {
        "bid_id": state.get("bid_id", ""),
        "company_id": state.get("company_id", ""),
        "bidder_language": bidder_language_of(state),
        "bidder_country": state.get("bidder_country", UNKNOWN_COUNTRY),
        "requirements": list(lane),
        "extraction_problems": list(state.get("extraction_problems", [])),
    }


# ------------------------------------------------------------------------- plan_checks


class CheckPlanner:
    """The `plan_checks` node: who is bidding, resolved once and written to the state."""

    def __init__(self, companies: CompanyLookup) -> None:
        self._companies = companies

    async def __call__(
        self,
        state: BidState,
        # `Optional[...]`, not `RunnableConfig | None`: LangGraph matches this annotation as
        # a *string* under postponed annotations and the modern spelling is silently never
        # injected (CLAUDE.md).
        config: Optional[RunnableConfig] = None,  # noqa: UP045
    ) -> CheckPlanUpdate:
        """The bidder's country, or a blank one and a line in the log saying why.

        Only two failures are caught, and both are ones a *run* should survive: a `profile`
        jsonb that no longer validates, and a company id that is not a UUID. A database that
        is down is neither, and raises — the stage wrapper reports it as `checking failed`
        rather than checking a few hundred requirements against a bidder from nowhere.
        """
        return {"bidder_country": await self._country(state.get("company_id", ""))}

    async def _country(self, company_id: str) -> str:
        try:
            profile = await self._companies.get(company_id=uuid.UUID(company_id))
        except (CompanyReadModelError, ValueError) as exc:
            logger.warning(
                "No bidder country for company %s (%s): eCertis evidence will be unmapped",
                company_id,
                type(exc).__name__,
            )
            return UNKNOWN_COUNTRY
        if profile is None:
            logger.warning(
                "Company %s has no profile row; the bidder country is unknown", company_id
            )
            return UNKNOWN_COUNTRY
        return profile.country


def build_plan_checks(db: ConnectionSource) -> CheckPlanner:
    """The node as the graph wires it: the real companies read model over the pool."""
    return CheckPlanner(CompaniesReadModel(db))


# -------------------------------------------------------------------------- check_reqs


class RequirementChecker:
    """The `check_reqs` node: one lane of requirements, each through its own ReAct loop.

    A callable object for the same reason `RequirementExtractor` is one — the seam has to
    come from somewhere and the graph calls `(state, config)`. Holds no per-run state, so
    one instance serves every lane of every concurrent bid.
    """

    def __init__(self, build_session: SessionBuilder) -> None:
        self._build_session = build_session

    async def __call__(
        self,
        state: BidState,
        config: Optional[RunnableConfig] = None,  # noqa: UP045
    ) -> CheckUpdate:
        """One matrix row per requirement in this lane, in the order they were given.

        Sequential inside the lane: the lanes *are* the concurrency (decision 1), and a
        second level of parallelism here would multiply the bound the story fixes.
        """
        requirements = state.get("requirements", [])
        if not requirements:
            return {"matrix_rows": []}

        bid_id, company_id = _identity_of(state)
        bidder = Bidder(
            country=state.get("bidder_country", UNKNOWN_COUNTRY),
            language=bidder_language_of(state),
        )
        async with self._build_session(company_id, bid_id, bidder) as context:
            rows = [await check_requirement(row, context) for row in requirements]
        logger.info("Bid %s: a lane of %d requirement(s) checked", bid_id, len(rows))
        return {"matrix_rows": rows}


def _identity_of(state: BidState) -> tuple[str, str]:
    """`bid_id` and `company_id`, or a `ValueError` naming the gap.

    Restated rather than imported from `graph.py`: this module may not depend on the graph
    that wires it. A lane without a tenant could only search everybody's documents.
    """
    bid_id = state.get("bid_id", "").strip()
    company_id = state.get("company_id", "").strip()
    missing = [
        name for name, value in (("bid_id", bid_id), ("company_id", company_id)) if not value
    ]
    if missing:
        raise ValueError(f"a checking lane needs {', '.join(missing)}")
    return bid_id, company_id


def openrouter_session(settings: Settings, db: ConnectionSource) -> SessionBuilder:
    """The production session: one embeddings client, the enabled tools, two bindings.

    The two bindings are the same slug twice — tools bound for the loop's turns, the verdict
    schema bound for its answer. One `ChatOpenAI` is built and bound twice rather than built
    twice, so a settings change cannot give the loop and the answer different models.

    S3.4.4 adds a second model alongside it and binds it the same two ways: each seam is
    wrapped in `resilient`, so a timed-out turn *or* a timed-out verdict call is retried once
    and then asked of the fallback slug. The wrapping is per binding because the two
    bindings are different runnables; the pair still comes from one `chat_model` call each,
    so neither seam can drift onto a different slug from the other.
    """

    @asynccontextmanager
    async def build(
        company_id: str, bid_id: str, bidder: Bidder
    ) -> AsyncIterator[CheckContext]:
        # Imported here rather than at module scope: `registry` walks and imports every tool
        # module, and a node that dragged the whole tool package into its import graph would
        # make `agent/` depend on `tools/` at import time as well as at run time.
        from crossbid.tools.manifest import ToolContext
        from crossbid.tools.registry import build_enabled_tools

        async with EmbeddingsClient(settings) as embedder:
            context = ToolContext(
                settings=settings,
                company_id=company_id,
                bid_id=bid_id,
                db=db,
                embedder=embedder,
            )
            tools = build_enabled_tools(context, settings, needed=CHECK_TOOLS, caller=NODE_NAME)
            model = chat_model(CHECK_MODEL_ROLE, settings)
            spare = chat_model(FALLBACK_MODEL_ROLE, settings)
            yield CheckContext(
                turn=tool_turn(resilient(model.bind_tools(tools), spare.bind_tools(tools))),
                verdict=structured_verdict(
                    resilient(
                        model.with_structured_output(CheckedRequirement),
                        spare.with_structured_output(CheckedRequirement),
                    )
                ),
                tools={tool.name: tool for tool in tools},
                max_tool_calls=settings.runtime.agent.max_tool_calls_per_requirement,
                bidder=bidder,
                system_prompt=settings.runtime.system_prompt,
            )

    return build


def build_check_reqs(settings: Settings, db: ConnectionSource) -> RequirementChecker:
    """The node as the graph wires it (S3.1.1), configured from settings."""
    return RequirementChecker(openrouter_session(settings, db))
