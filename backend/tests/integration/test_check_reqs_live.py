"""S3.3.1's agentic loop against a real model, on real DE requirements. Marked `live`.

**Not run by `make test`, and not run casually.** It makes real OpenRouter calls on the
`cheap` slug for a handful of requirements out of the German fixture's golden file, and it
skips rather than fails on a machine with no `OPENROUTER_API_KEY`. The whole-pack run is
`test_bid_run_live.py`; this one is deliberately small, because what it proves does not get
truer with 258 requirements and the run budget is $2.50.

What is real and what is not, stated so a green run means something.

**Real:** the chat model built from the committed settings and bound with tools exactly as
`openrouter_session` binds it; the ReAct loop, its budget, and its closing structured call;
`ecertis_evidence_lookup` against the committed cache; the requirements, quoted verbatim out
of `tests/fixtures/tenders/de/golden.yaml`, including one carrying a real ESPD criterion id.

**Not real:** the database, and therefore the retrieval. `company_rag_search` here is a
fixture-backed tool that returns passages of the demo company's own pack (S6.3) as a
`RagSearchResult`, which is the *same object* the real tool returns — that is what the
assertions turn on, so the substitution does not weaken them. Opening Postgres would make
this test a test of pgvector; the retrieval path has its own coverage in `test_rag_tools.py`
and in the embeddings live test.

The assertions are properties, not judgements. A model is free to answer `supported`,
`partially_supported`, `unsupported` or `not_applicable` for any of these rows and the test
still passes; what it may not do is produce a row without a rationale, a `supported` without
a citation, a citation of a quote the fixture never returned, or more tool calls than the
budget. Asserting the *verdict* would be asserting the model, which changes underneath us;
these four are what the story promises whatever the model says.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

import pytest
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from crossbid.agent.nodes.check_loop import (
    Bidder,
    CheckContext,
    CheckedRequirement,
    check_requirement,
    structured_verdict,
    tool_turn,
)
from crossbid.agent.nodes.check_reqs import CHECK_MODEL_ROLE
from crossbid.llm import chat_model
from crossbid.models.golden import GoldenRequirement, load_golden
from crossbid.models.matrix import RowStatus
from crossbid.models.requirement import Checkability, Requirement
from crossbid.settings import Settings, SettingsError, load_settings
from crossbid.tools import company_rag_search, ecertis_evidence, tender_rag_search
from crossbid.tools.manifest import ToolContext
from crossbid.tools.rag import RagHit, RagSearchResult

pytestmark = pytest.mark.live

GOLDEN = Path(__file__).resolve().parents[1] / "fixtures" / "tenders" / "de" / "golden.yaml"

COMPANY_ID: Final = str(uuid.uuid4())
BID_ID: Final = str(uuid.uuid4())
BIDDER: Final = Bidder(country="de", language="de")

CHECKED_REQUIREMENTS: Final = 4
"""How many golden rows this test spends money on. Four is enough to cover the branches
that cost a model call — one with a criterion id, three without — and small enough that a
run is cents rather than dollars."""

COST_CEILING_USD: Final = 0.25
"""A tenth of the run budget for four requirements. Not the story's limit (that is the whole
pack, in `test_bid_run_live.py`); a tripwire, so a slug change that makes checking twenty
times more expensive fails here rather than in a bid."""


def resolve_settings() -> Settings | None:
    try:
        return load_settings()
    except SettingsError:
        return None


SETTINGS = resolve_settings()
skip_without_key = pytest.mark.skipif(SETTINGS is None, reason="OPENROUTER_API_KEY is not set")


# ------------------------------------------------------------- the company's own evidence

COMPANY_PASSAGES: Final = (
    (
        "Jahresabschluss_2025.pdf",
        2,
        "Der Umsatz im Geschaeftsbereich IT-Dienstleistungen betrug im Geschaeftsjahr 2025 "
        "7.400.000,00 EUR.",
    ),
    (
        "Personalbestand_2026.pdf",
        1,
        "Zum 01.01.2026 beschaeftigt die Gesellschaft 48,0 Vollzeitaequivalente, davon 31,5 "
        "im Geschaeftsbereich Netz- und Informationstechnik.",
    ),
    (
        "Zertifikat_ISO_27001.pdf",
        1,
        "Die Zertifizierung nach ISO/IEC 27001:2022 ist gueltig bis zum 01.05.2026 und "
        "umfasst den Betrieb von Rechenzentren.",
    ),
)
"""Three passages of the demo company's pack (S6.3), written out rather than embedded.

Hand-written here for the same reason the unit tests hand-build their fixtures: the point of
this test is the loop's behaviour on a real model, and a retrieval that answers the same
three passages every time is what makes a failure the model's rather than the index's."""


class CompanySearchArgs(BaseModel):
    query: str = Field(description="What to look for in the company's documents")


def fixture_company_search() -> tuple[BaseTool, list[str]]:
    """`company_rag_search`'s name, description, schema and artifact — fixture passages.

    The manifest is the real one, so the model reads exactly the description it reads in
    production, and the artifact is a real `RagSearchResult`, so `RagHit.as_evidence()` is
    the same code path that produces a citation in a bid.
    """
    asked: list[str] = []
    hits = tuple(
        RagHit(
            document_id=str(uuid.uuid5(uuid.NAMESPACE_URL, name)),
            document_name=name,
            page=page,
            pages=(page,),
            quote=quote,
            score=0.8,
        )
        for name, page, quote in COMPANY_PASSAGES
    )

    async def run(query: str) -> tuple[str, RagSearchResult]:
        asked.append(query)
        result = RagSearchResult(query=query, corpus=company_rag_search.CORPUS, hits=hits)
        return result.render(), result

    tool = StructuredTool.from_function(
        coroutine=run,
        name=company_rag_search.MANIFEST.name,
        description=company_rag_search.MANIFEST.description,
        args_schema=CompanySearchArgs,
        response_format="content_and_artifact",
    )
    return tool, asked


def empty_tender_search() -> BaseTool:
    """`tender_rag_search` with nothing in the index: a real answer, not an error."""

    async def run(query: str) -> tuple[str, RagSearchResult]:
        result = RagSearchResult(query=query, corpus=tender_rag_search.CORPUS, hits=())
        return result.render(), result

    return StructuredTool.from_function(
        coroutine=run,
        name=tender_rag_search.MANIFEST.name,
        description=tender_rag_search.MANIFEST.description,
        args_schema=CompanySearchArgs,
        response_format="content_and_artifact",
    )


class CostRecorder(BaseCallbackHandler):
    """Sums the cost OpenRouter reports on every chat completion, as S3.1.1's test does."""

    def __init__(self) -> None:
        super().__init__()
        self.calls = 0
        self.costs: list[float] = []

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        self.calls += 1
        usage = (response.llm_output or {}).get("token_usage") or {}
        if not usage and response.generations and response.generations[0]:
            message = getattr(response.generations[0][0], "message", None)
            usage = (getattr(message, "response_metadata", None) or {}).get("token_usage") or {}
        cost = usage.get("cost")
        if cost is not None:
            self.costs.append(float(cost))


# ------------------------------------------------------------------- the requirements


def golden_requirements() -> tuple[Requirement, ...]:
    """Four checkable DE rows, one of them carrying a real ESPD criterion id.

    Taken from the golden file rather than written here so the model reads clauses a German
    buyer actually published, `<br>` markers and all.
    """
    entries = load_golden(GOLDEN).requirements
    checkable = [entry for entry in entries if entry.checkable is Checkability.COMPANY_PROPERTY]
    mapped = [entry for entry in checkable if entry.ecertis_criterion_id is not None]
    assert mapped, "the DE golden file no longer maps any checkable row to a criterion"
    chosen = [
        mapped[0],
        *[e for e in checkable if e is not mapped[0]][: CHECKED_REQUIREMENTS - 1],
    ]
    return tuple(_as_requirement(entry) for entry in chosen)


def _as_requirement(entry: GoldenRequirement) -> Requirement:
    return Requirement(
        id=str(uuid.uuid5(uuid.NAMESPACE_URL, entry.id)),
        bid_id=BID_ID,
        category=entry.category,
        kind=entry.kind,
        stage=entry.stage,
        checkable=entry.checkable,
        source_text=entry.quote,
        source_lang="de",
        document_name=entry.doc,
        page=entry.page,
        ecertis_criterion_id=entry.ecertis_criterion_id,
        threshold=entry.threshold,
    )


def live_context(
    settings: Settings, tools: Sequence[BaseTool], recorder: CostRecorder
) -> CheckContext:
    """The production bindings: one model, tools bound for the loop, a schema for the answer.

    The recorder is attached to the model rather than passed per call, because
    `check_requirement` takes no run config — the loop's seams are two bare callables, which
    is what keeps the unit tests free of LangChain. Cost is therefore collected the way the
    model itself reports it.
    """
    model = chat_model(CHECK_MODEL_ROLE, settings)
    model.callbacks = [recorder]
    return CheckContext(
        turn=tool_turn(model.bind_tools(list(tools))),
        verdict=structured_verdict(model.with_structured_output(CheckedRequirement)),
        tools={tool.name: tool for tool in tools},
        max_tool_calls=settings.runtime.agent.max_tool_calls_per_requirement,
        bidder=BIDDER,
        system_prompt=settings.runtime.system_prompt,
    )


# ------------------------------------------------------------------------------- the test


@skip_without_key
@pytest.mark.anyio
async def test_real_requirements_yield_cited_rows_within_the_tool_budget() -> None:
    assert SETTINGS is not None
    requirements = golden_requirements()
    assert len(requirements) == CHECKED_REQUIREMENTS
    company_tool, asked = fixture_company_search()
    ecertis_tool = ecertis_evidence.build_tool(
        ToolContext(settings=SETTINGS, company_id=COMPANY_ID, bid_id=BID_ID)
    )
    tools = (company_tool, empty_tender_search(), ecertis_tool)
    recorder = CostRecorder()
    context = live_context(SETTINGS, tools, recorder)
    quotes = {quote for _, _, quote in COMPANY_PASSAGES}
    budget = SETTINGS.runtime.agent.max_tool_calls_per_requirement

    # Act
    rows = []
    for row in requirements:
        before = recorder.calls
        rows.append(await check_requirement(row, context))
        # Every loop is one turn per tool call plus the closing verdict, so the number of
        # model calls bounds the number of tool calls from above.
        assert recorder.calls - before <= budget + 2, row.id

    # Assert -- the story's promises, none of which is a judgement about the answer
    assert len(rows) == len(requirements)
    for row in rows:
        assert row.agent_rationale.strip(), row.requirement_id
        if row.status is RowStatus.SUPPORTED:
            assert row.evidence, "a supported row without a citation"
        for cited in row.evidence:
            assert cited.quote in quotes, "a citation the retrieval never returned"
    assert rows[0].ecertis_evidence is not None, "the mapped requirement lost its criterion"
    assert rows[0].ecertis_evidence.country == "de"
    assert asked, "the model never searched the company's documents"

    total = sum(recorder.costs)
    assert recorder.costs, "OpenRouter reported no cost: check USAGE_ACCOUNTING_EXTRA_BODY"
    assert total < COST_CEILING_USD, f"${total:.3f} for {len(rows)} requirements"
    statuses = ", ".join(row.status.value for row in rows)
    print(
        f"\n{len(rows)} requirements checked: {statuses}; "
        f"{recorder.calls} model calls, ${total:.3f}"
    )
