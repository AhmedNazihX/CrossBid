"""S3.1.1's budget criterion: the DE pack reaches the interrupt in time and on budget.

Marked `live`: it calls OpenRouter on the default models for every section of the 28-file,
191-page pack (ADR-0001), which costs real money and minutes. It is **not** run by
`make test`; `make test-live` runs it, and it skips rather than fails on a machine with no
`OPENROUTER_API_KEY`.

What is real here and what is not, stated so the number means something. Real: the
extraction node built from the committed settings, the model calls, the graph wiring, the
interrupt. Not real: Storage, Postgres, and **checking**. The pack is read from the fixture
directory through the node's fetcher seam, the read model is a recorder and the checkpointer
a `MemorySaver` -- the Postgres saver has its own `live` restart test and would only add its
own latency to a measurement that is about the model. `plan_checks` and `check_reqs` are
stubbed out, so this test keeps measuring exactly what it measured on 2026-09-11 (ADR-0012)
and stays comparable with that recorded figure; S3.3.1's own live test
(`test_check_reqs_live.py`) measures the agentic loop, whose retrieval tools need a database
this test deliberately does not open. Cost is what OpenRouter *reports*
(`usage.cost`, requested by `llm.USAGE_ACCOUNTING_EXTRA_BODY`), summed over every call by a
callback handler, so a run that reported no cost at all fails rather than passing at $0.

The run also *writes* what it extracted, to `tests/fixtures/extractions/de.live.json`
(S3.2.3). Recall is measured from that file afterwards by `uv run scripts/recall.py`, offline
and for free; without it every recall number would cost another $1.38 and five minutes.

Both limits come from `RunBudget.from_settings`: the settings keys once the parent adds
them (`agent.run_budget_seconds`, `agent.run_budget_usd`), the story's constants until then.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langgraph.checkpoint.memory import MemorySaver

from crossbid.agent.graph import AWAIT_REVIEW, build_graph, initial_state
from crossbid.agent.nodes.parse_docs import DocumentParser
from crossbid.agent.runner import RunBudget
from crossbid.agent.state import ExtractionProblem
from crossbid.eval.extraction import (
    ExtractionMeta,
    ExtractionResult,
    ExtractionSource,
    dump_extraction,
)
from crossbid.models.requirement import Requirement
from crossbid.models.tender import BidStatus, DocumentKind
from crossbid.readmodel.bids import BidDocumentRow, BidRow, thread_id_of
from crossbid.readmodel.documents import DocumentStatus
from crossbid.settings import Settings, SettingsError, bid_run_config, load_settings

pytestmark = pytest.mark.live

DE_DOCUMENTS = Path(__file__).resolve().parents[1] / "fixtures" / "tenders" / "de" / "documents"
"""The 28 procurement documents, not the notice one level up (CLAUDE.md on the two counts)."""

EXPECTED_DOCUMENT_COUNT = 28
FIXTURE_DIR = "tests/fixtures/tenders/de"
RESULT_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "extractions" / "de.live.json"
"""Where this run leaves its rows for `scripts/recall.py` (S3.2.3).

Written rather than printed because extraction costs $1.38 and five minutes: the one
artefact that can be scored offline afterwards is the reason to pay it twice rather than
every time somebody wants a recall number. Committed only if the run is worth keeping --
`de.json` beside it is the synthetic stand-in, and the two are told apart by `meta.source`.
"""
COMPANY_ID = str(uuid.uuid4())
BID_ID = str(uuid.uuid4())


def resolve_settings() -> Settings | None:
    try:
        return load_settings()
    except SettingsError:
        return None


SETTINGS = resolve_settings()
skip_without_key = pytest.mark.skipif(SETTINGS is None, reason="OPENROUTER_API_KEY is not set")


# --------------------------------------------------------------------------------- fakes


class RecordingProjection:
    def __init__(self) -> None:
        self.statuses: list[BidStatus] = []
        self.problems: list[ExtractionProblem] = []
        self.rows: list[Requirement] = []

    async def set_status(self, *, company_id: str, bid_id: str, status: BidStatus) -> None:
        self.statuses.append(status)

    async def set_problems(
        self, *, company_id: str, bid_id: str, problems: Sequence[ExtractionProblem]
    ) -> None:
        self.problems = list(problems)

    async def write_requirements(self, *, company_id: str, rows: Sequence[Requirement]) -> int:
        self.rows.extend(rows)
        return len(rows)

    async def write_matrix_rows(
        self, *, company_id: str, bid_id: str, rows: Sequence[Any]
    ) -> int:
        return len(rows)


class FakeDatabase:
    checkpointer = MemorySaver()

    def connection(self) -> Any:
        raise AssertionError("the live run must not touch Postgres")


class CostRecorder(BaseCallbackHandler):
    """Sums the cost OpenRouter reports on every chat completion."""

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


def fixture_rows() -> list[BidDocumentRow]:
    return [
        BidDocumentRow(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, path.name)),
            name=path.name,
            storage_path=f"{COMPANY_ID}/{path.stem}/{path.name}",
            kind=DocumentKind.TENDER_DOCUMENT,
            status=DocumentStatus.READY,
            bid_id=BID_ID,
            pages=0,
        )
        for path in sorted(DE_DOCUMENTS.glob("*.pdf"))
    ]


async def skip_planning(state: Any, config: Any = None) -> Any:
    """Stands in for `plan_checks`, which would read the companies table."""
    return {"bidder_country": "de"}


async def skip_checking(state: Any, config: Any = None) -> Any:
    """Stands in for `check_reqs`. Never reached -- with requirements present the fan-out
    does send to it, so it is a real stub and not a decoration."""
    return {"matrix_rows": []}


def fixture_parser() -> DocumentParser:
    rows = fixture_rows()

    async def load(company_id: str, bid_id: str) -> Sequence[BidDocumentRow]:
        return rows

    async def fetch(company_id: str, document: BidDocumentRow) -> bytes:
        return (DE_DOCUMENTS / document.name).read_bytes()

    return DocumentParser(load_documents=load, fetch=fetch)


def write_result(projection: RecordingProjection, *, cost: float, elapsed: float) -> None:
    """Keep the rows this run paid for, so S3.2.3 can score them without paying again.

    Called before the budget assertions on purpose: a run that overshoots the time or cost
    limit still extracted requirements, and throwing them away would mean paying $1.38 twice
    to find out what recall the overshooting run had.
    """
    assert SETTINGS is not None
    dump_extraction(
        ExtractionResult(
            meta=ExtractionMeta(
                fixture_dir=FIXTURE_DIR,
                source=ExtractionSource.LIVE_RUN,
                produced_on=date.today(),
                method=(
                    "The committed graph over the 28-file DE pack on the configured models, "
                    "run by tests/integration/test_bid_run_live.py."
                ),
                models=dict(SETTINGS.runtime.models.model_dump()),
                cost_usd=cost,
                elapsed_seconds=elapsed,
            ),
            requirements=tuple(projection.rows),
            problems=tuple(projection.problems),
        ),
        RESULT_PATH,
    )


# ---------------------------------------------------------------------------------- test


@skip_without_key
@pytest.mark.anyio
async def test_the_de_pack_reaches_awaiting_review_within_the_time_and_cost_budget() -> None:
    assert SETTINGS is not None
    assert len(fixture_rows()) == EXPECTED_DOCUMENT_COUNT, "the DE fixture changed shape"
    budget = RunBudget.from_settings(SETTINGS)
    projection = RecordingProjection()
    recorder = CostRecorder()
    graph = build_graph(
        SETTINGS,
        FakeDatabase(),  # type: ignore[arg-type]
        parse_docs=fixture_parser(),
        plan_checks=skip_planning,
        check_reqs=skip_checking,
        projection=projection,
        checkpointer=MemorySaver(),
    )
    bid = BidRow(
        id=BID_ID,
        company_id=COMPANY_ID,
        thread_id=thread_id_of(BID_ID),
        notice_number="614251-2026",
        title="BMI Netztechnik (DE fixture)",
        source_language="de",
        bidder_language="de",
        status=BidStatus.QUEUED,
    )
    config = bid_run_config(BID_ID, thread_id=bid.thread_id, run_name="bid_run_live")
    config["callbacks"] = [recorder]

    # Act
    started = time.monotonic()
    await graph.ainvoke(initial_state(bid), config)
    elapsed = time.monotonic() - started
    snapshot = await graph.aget_state(config)
    total_cost = sum(recorder.costs)
    write_result(projection, cost=total_cost, elapsed=elapsed)

    # Assert -- parked for a human, with rows, inside both limits
    assert snapshot.next == (AWAIT_REVIEW,)
    assert projection.statuses[:2] == [BidStatus.PARSING, BidStatus.EXTRACTING]
    assert projection.statuses[-1] is BidStatus.AWAITING_REVIEW
    assert set(projection.statuses[2:-1]) == {BidStatus.CHECKING}
    assert projection.rows, "extraction wrote no requirements"
    assert elapsed < budget.seconds, (
        f"{elapsed:.0f}s to awaiting_review, budget {budget.seconds}s"
    )
    assert recorder.calls > 0, "no model call was observed; the callback is not wired"
    assert recorder.costs, "OpenRouter reported no cost: check USAGE_ACCOUNTING_EXTRA_BODY"
    assert total_cost < budget.usd, f"${total_cost:.2f} for the run, budget ${budget.usd:.2f}"
    print(
        f"\nDE pack: {len(projection.rows)} requirements, {len(projection.problems)} problems, "
        f"{recorder.calls} model calls, {elapsed:.0f}s, ${total_cost:.2f}"
        f"\nExtraction result written to {RESULT_PATH}; score it with "
        f"`uv run scripts/recall.py {RESULT_PATH}` (S3.2.3)."
    )
