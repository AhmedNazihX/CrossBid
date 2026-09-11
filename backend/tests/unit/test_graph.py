"""S3.1.1 — the outer graph: stages, the interrupt, and what a second process sees.

Offline. The real `build_graph` wiring runs over fake nodes, a recording projection in place
of the read model, and a `MemorySaver` in place of Postgres. That is enough to prove the
things the story is about — the status sequence, the pause, the resume — because none of
them depend on what the nodes compute; the `live` restart test covers the Postgres saver.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from crossbid.agent import graph as graph_module
from crossbid.agent.graph import (
    AWAIT_REVIEW,
    INTERRUPT_BID_ID,
    INTERRUPT_PROBLEMS,
    INTERRUPT_REQUIREMENTS,
    ReadModelProjection,
    StageError,
    build_graph,
    initial_state,
    stage,
)
from crossbid.agent.state import BidState, ExtractionProblem, ExtractionProblemReason
from crossbid.ingestion.storage import StorageError
from crossbid.models.requirement import (
    Checkability,
    Requirement,
    RequirementCategory,
    RequirementKind,
    RequirementStage,
)
from crossbid.models.tender import BidStatus
from crossbid.readmodel.bids import BidRow, thread_id_of
from crossbid.settings import Settings, bid_run_config

pytestmark = pytest.mark.anyio

COMPANY_ID = str(uuid.uuid4())
BID_ID = str(uuid.uuid4())
DOCUMENT = "Bewerbungsbedingungen.pdf"


# ------------------------------------------------------------------------ hand-built input


def bid_row(**overrides: Any) -> BidRow:
    values: dict[str, Any] = {
        "id": BID_ID,
        "company_id": COMPANY_ID,
        "thread_id": thread_id_of(BID_ID),
        "notice_number": "614251-2026",
        "title": "Netztechnik",
        "source_language": "de",
        "bidder_language": "de",
        "status": BidStatus.QUEUED,
    }
    return BidRow(**(values | overrides))


def requirement(text: str, page: int = 1) -> Requirement:
    return Requirement(
        id=str(uuid.uuid5(uuid.NAMESPACE_URL, text)),
        bid_id=BID_ID,
        category=RequirementCategory.ECONOMIC_FINANCIAL,
        kind=RequirementKind.MANDATORY,
        stage=RequirementStage.BID_ELIGIBILITY,
        checkable=Checkability.COMPANY_PROPERTY,
        source_text=text,
        source_lang="de",
        document_name=DOCUMENT,
        page=page,
    )


def problem(reason: ExtractionProblemReason) -> ExtractionProblem:
    return ExtractionProblem(reason=reason, document_name=DOCUMENT)


PARSE_PROBLEM = problem(ExtractionProblemReason.UNPARSEABLE_DOCUMENT)
EXTRACT_PROBLEM = problem(ExtractionProblemReason.NO_VERBATIM_QUOTE)
ROWS = (requirement("Umsatz mindestens 3.000.000 EUR"), requirement("29 VZAE", page=2))


# --------------------------------------------------------------------------------- fakes


class RecordingProjection:
    """Stands in for the read model; keeps every write in the order it was made."""

    def __init__(self, *, fail_on_status: bool = False) -> None:
        self.events: list[tuple[str, Any]] = []
        self._fail_on_status = fail_on_status

    @property
    def statuses(self) -> list[BidStatus]:
        return [value for kind, value in self.events if kind == "status"]

    @property
    def problem_counts(self) -> list[int]:
        return [len(value) for kind, value in self.events if kind == "problems"]

    @property
    def written_rows(self) -> list[Sequence[Requirement]]:
        return [value for kind, value in self.events if kind == "requirements"]

    async def set_status(self, *, company_id: str, bid_id: str, status: BidStatus) -> None:
        assert (company_id, bid_id) == (COMPANY_ID, BID_ID)
        if self._fail_on_status:
            raise OSError("database unreachable")
        self.events.append(("status", status))

    async def set_problems(
        self, *, company_id: str, bid_id: str, problems: Sequence[ExtractionProblem]
    ) -> None:
        assert (company_id, bid_id) == (COMPANY_ID, BID_ID)
        self.events.append(("problems", list(problems)))

    async def write_requirements(self, *, company_id: str, rows: Sequence[Requirement]) -> int:
        assert company_id == COMPANY_ID
        self.events.append(("requirements", list(rows)))
        return len(rows)


class FakeDatabase:
    """What `build_graph` reads from a `Database` when no seams are passed."""

    def __init__(self) -> None:
        self.checkpointer = MemorySaver()

    def connection(self) -> Any:  # pragma: no cover -- never borrowed in these tests
        raise AssertionError("the graph must not borrow a connection here")


def parse_node(*, problems: Sequence[ExtractionProblem] = ()) -> Any:
    async def parse_docs(state: BidState, config: RunnableConfig | None = None) -> Any:
        assert config is not None, "LangGraph must inject the run config"
        assert config["metadata"]["bid_id"] == BID_ID
        return {"documents": [], "extraction_problems": list(problems)}

    return parse_docs


def extract_node(
    rows: Sequence[Requirement], *, problems: Sequence[ExtractionProblem] = ()
) -> Any:
    async def extract_reqs(state: BidState, config: RunnableConfig | None = None) -> Any:
        return {"requirements": list(rows), "extraction_problems": list(problems)}

    return extract_reqs


async def crashing(state: BidState, config: RunnableConfig | None = None) -> Any:
    raise RuntimeError("Der Bieter muss ... (text quoted from the tender)")


def compile_graph(
    settings: Settings,
    *,
    saver: MemorySaver,
    projection: RecordingProjection,
    parse: Any | None = None,
    extract: Any | None = None,
) -> Any:
    return build_graph(
        settings,
        FakeDatabase(),  # type: ignore[arg-type]
        parse_docs=parse if parse is not None else parse_node(problems=[PARSE_PROBLEM]),
        extract_reqs=(
            extract if extract is not None else extract_node(ROWS, problems=[EXTRACT_PROBLEM])
        ),
        projection=projection,
        checkpointer=saver,
    )


CONFIG = bid_run_config(BID_ID, thread_id=thread_id_of(BID_ID))


# -------------------------------------------------------------------- the status sequence


async def test_the_status_sequence_is_written_to_the_read_model_in_order(
    offline_settings: Settings,
) -> None:
    # Arrange
    projection = RecordingProjection()
    graph = compile_graph(offline_settings, saver=MemorySaver(), projection=projection)

    # Act
    await graph.ainvoke(initial_state(bid_row()), CONFIG)

    # Assert
    assert projection.statuses == [
        BidStatus.PARSING,
        BidStatus.EXTRACTING,
        BidStatus.AWAITING_REVIEW,
    ]


async def test_problems_are_projected_cumulatively_after_every_node(
    offline_settings: Settings,
) -> None:
    """The poller reads the whole list, so each write carries everything so far."""
    projection = RecordingProjection()
    graph = compile_graph(offline_settings, saver=MemorySaver(), projection=projection)

    await graph.ainvoke(initial_state(bid_row()), CONFIG)

    # After parse: its one problem. After extract: both. The interrupt node writes nothing
    # on its first pass -- `interrupt()` raises before the stage reaches its exit projection.
    assert projection.problem_counts == [1, 2]


async def test_requirements_are_written_once_when_extraction_finishes(
    offline_settings: Settings,
) -> None:
    projection = RecordingProjection()
    graph = compile_graph(offline_settings, saver=MemorySaver(), projection=projection)

    await graph.ainvoke(initial_state(bid_row()), CONFIG)

    # Act / Assert -- exactly one write, between `extracting` and `awaiting_review`
    assert projection.written_rows == [list(ROWS)]
    kinds = [kind for kind, _ in projection.events]
    extracting = projection.events.index(("status", BidStatus.EXTRACTING))
    awaiting = projection.events.index(("status", BidStatus.AWAITING_REVIEW))
    assert extracting < kinds.index("requirements") < awaiting


async def test_a_parse_node_that_reports_nothing_still_writes_the_empty_list(
    offline_settings: Settings,
) -> None:
    """`set_problems` runs whether or not there is anything in it, and no rows means no
    `write_requirements` call -- the empty-list branch of `_project`."""
    projection = RecordingProjection()
    graph = compile_graph(
        offline_settings,
        saver=MemorySaver(),
        projection=projection,
        parse=parse_node(),
        extract=extract_node([]),
    )

    await graph.ainvoke(initial_state(bid_row()), CONFIG)

    assert projection.problem_counts == [0, 0]
    assert projection.written_rows == []


# --------------------------------------------------------------------------- the interrupt


async def test_the_graph_parks_at_the_interrupt_with_awaiting_review(
    offline_settings: Settings,
) -> None:
    projection = RecordingProjection()
    graph = compile_graph(offline_settings, saver=MemorySaver(), projection=projection)

    await graph.ainvoke(initial_state(bid_row()), CONFIG)
    snapshot = await graph.aget_state(CONFIG)

    # Parked, not finished: the next node is named and the payload says what is waited for.
    assert snapshot.next == (AWAIT_REVIEW,)
    assert len(snapshot.interrupts) == 1
    assert snapshot.interrupts[0].value == {
        INTERRUPT_BID_ID: BID_ID,
        INTERRUPT_REQUIREMENTS: 2,
        INTERRUPT_PROBLEMS: 2,
    }
    assert projection.statuses[-1] is BidStatus.AWAITING_REVIEW
    # The checkpoint holds extraction's output; its `status` names the stage that produced it.
    assert snapshot.values["status"] is BidStatus.EXTRACTING
    assert [row.id for row in snapshot.values["requirements"]] == [row.id for row in ROWS]


async def test_a_second_graph_on_the_same_thread_sees_the_parked_state(
    offline_settings: Settings,
) -> None:
    """A restart builds a new graph object; the checkpointer is what carries the state."""
    saver = MemorySaver()
    first = compile_graph(offline_settings, saver=saver, projection=RecordingProjection())
    await first.ainvoke(initial_state(bid_row()), CONFIG)

    # Act -- nothing survives but the saver
    second = compile_graph(offline_settings, saver=saver, projection=RecordingProjection())
    snapshot = await second.aget_state(CONFIG)

    # Assert
    assert snapshot.next == (AWAIT_REVIEW,)
    assert len(snapshot.values["requirements"]) == 2
    assert snapshot.values["company_id"] == COMPANY_ID


async def test_resuming_the_parked_graph_runs_it_to_the_end(offline_settings: Settings) -> None:
    """`Command(resume=...)` is how S3.4.2 will hand the review in; today nothing follows."""
    saver = MemorySaver()
    projection = RecordingProjection()
    graph = compile_graph(offline_settings, saver=saver, projection=projection)
    await graph.ainvoke(initial_state(bid_row()), CONFIG)

    # Act
    await graph.ainvoke(Command(resume={"decision": "go"}), CONFIG)
    snapshot = await graph.aget_state(CONFIG)

    # Assert
    assert snapshot.next == ()
    assert snapshot.interrupts == ()
    assert snapshot.values["status"] is BidStatus.AWAITING_REVIEW
    # The documented caveat: the interrupt node re-runs on resume, so its status is written
    # twice with the same value.
    assert projection.statuses.count(BidStatus.AWAITING_REVIEW) == 2


# ------------------------------------------------------------------------------- failures


async def test_a_crashing_node_raises_a_stage_error_naming_stage_and_type_only(
    offline_settings: Settings,
) -> None:
    projection = RecordingProjection()
    graph = compile_graph(
        offline_settings, saver=MemorySaver(), projection=projection, extract=crashing
    )

    with pytest.raises(StageError) as caught:
        await graph.ainvoke(initial_state(bid_row()), CONFIG)

    assert str(caught.value) == "extracting failed: RuntimeError"
    assert caught.value.stage is BidStatus.EXTRACTING
    assert isinstance(caught.value.__cause__, RuntimeError)
    assert "Bieter" not in str(caught.value), "the node's message quotes the tender"
    assert projection.statuses == [BidStatus.PARSING, BidStatus.EXTRACTING]


async def test_a_failing_read_model_write_is_reported_under_its_stage(
    offline_settings: Settings,
) -> None:
    graph = compile_graph(
        offline_settings,
        saver=MemorySaver(),
        projection=RecordingProjection(fail_on_status=True),
    )

    with pytest.raises(StageError, match="parsing failed: OSError"):
        await graph.ainvoke(initial_state(bid_row()), CONFIG)


async def test_a_state_without_its_identity_fails_before_any_write(
    offline_settings: Settings,
) -> None:
    projection = RecordingProjection()
    graph = compile_graph(offline_settings, saver=MemorySaver(), projection=projection)

    with pytest.raises(StageError) as caught:
        await graph.ainvoke({"bid_id": BID_ID, "company_id": "  "}, CONFIG)

    assert isinstance(caught.value.__cause__, ValueError)
    assert "company_id" in str(caught.value.__cause__)
    assert projection.events == []


async def test_the_checkpoint_after_a_crash_resumes_at_the_failed_node(
    offline_settings: Settings,
) -> None:
    """The offline restart proof: parse is not re-run, extraction is, and the run parks."""
    saver = MemorySaver()
    broken = compile_graph(
        offline_settings, saver=saver, projection=RecordingProjection(), extract=crashing
    )
    with pytest.raises(StageError):
        await broken.ainvoke(initial_state(bid_row()), CONFIG)

    # Act -- "after the restart": a new graph, the same saver, no input
    projection = RecordingProjection()
    repaired = compile_graph(offline_settings, saver=saver, projection=projection)
    await repaired.ainvoke(None, CONFIG)

    # Assert
    assert projection.statuses == [BidStatus.EXTRACTING, BidStatus.AWAITING_REVIEW]
    assert (await repaired.aget_state(CONFIG)).next == (AWAIT_REVIEW,)


# ---------------------------------------------------------------------- stage, in isolation


async def test_stage_carries_the_stage_name_for_traces(offline_settings: Settings) -> None:
    wrapped = stage(BidStatus.PARSING, parse_node(), RecordingProjection())
    assert wrapped.__name__ == "parsing_stage"


# --------------------------------------------------------------------- building for real


def test_build_graph_uses_the_database_checkpointer_by_default(
    offline_settings: Settings,
) -> None:
    """Only `parse_docs` is injected: the real extractor is built from settings (no network
    at construction) and the checkpointer comes from the `Database`."""
    db = FakeDatabase()

    graph = build_graph(offline_settings, db, parse_docs=parse_node())  # type: ignore[arg-type]

    assert graph.checkpointer is db.checkpointer


def test_build_graph_without_storage_refuses_to_build_the_real_parse_node(
    offline_settings: Settings,
) -> None:
    """`build_parse_docs` needs Storage; the offline settings have none, so it says so."""
    with pytest.raises(StorageError, match="SUPABASE_URL"):
        build_graph(offline_settings, FakeDatabase())  # type: ignore[arg-type]


async def test_read_model_projection_delegates_every_write_scoped_by_company(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    async def set_bid_status(db: Any, **kwargs: Any) -> None:
        calls.append(("status", kwargs))

    async def set_bid_problems(db: Any, **kwargs: Any) -> None:
        calls.append(("problems", kwargs))

    async def write_requirements(db: Any, **kwargs: Any) -> int:
        calls.append(("requirements", kwargs))
        return len(kwargs["rows"])

    monkeypatch.setattr(graph_module, "set_bid_status", set_bid_status)
    monkeypatch.setattr(graph_module, "set_bid_problems", set_bid_problems)
    monkeypatch.setattr(graph_module, "write_requirements", write_requirements)
    projection = ReadModelProjection(FakeDatabase())

    # Act
    await projection.set_status(company_id=COMPANY_ID, bid_id=BID_ID, status=BidStatus.PARSING)
    await projection.set_problems(
        company_id=COMPANY_ID, bid_id=BID_ID, problems=[PARSE_PROBLEM]
    )
    written = await projection.write_requirements(company_id=COMPANY_ID, rows=list(ROWS))

    # Assert -- every call carries the tenant, and problems go out as plain JSON
    assert written == 2
    assert all(kwargs["company_id"] == COMPANY_ID for _, kwargs in calls)
    assert calls[0][1]["status"] is BidStatus.PARSING
    assert calls[1][1]["problems"] == [PARSE_PROBLEM.model_dump(mode="json")]
    assert calls[1][1]["problems"][0]["reason"] == "unparseable_document"


# ---------------------------------------------------------------------------- the state


def test_initial_state_fills_every_channel_from_the_row() -> None:
    state = initial_state(bid_row())

    assert state == {
        "bid_id": BID_ID,
        "company_id": COMPANY_ID,
        "notice_number": "614251-2026",
        "source_language": "de",
        "bidder_language": "de",
        "status": BidStatus.QUEUED,
        "documents": [],
        "requirements": [],
        "extraction_problems": [],
    }


def test_initial_state_turns_null_columns_into_empty_strings() -> None:
    """`parse_docs` refuses a blank language with a message naming it; `None` would not."""
    state = initial_state(bid_row(notice_number=None, source_language=None))

    assert state["notice_number"] == ""
    assert state["source_language"] == ""


def test_the_module_describes_the_workflow_versus_agentic_split() -> None:
    """A CLAUDE.md convention: the outer graph is a workflow, `check_reqs` is the agent."""
    assert graph_module.__doc__ is not None
    assert "deterministic workflow" in graph_module.__doc__
    assert "check_reqs" in graph_module.__doc__
    assert "interrupt" in graph_module.__doc__
