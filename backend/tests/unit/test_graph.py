"""S3.1.1 — the outer graph: stages, the interrupt, and what a second process sees.

Offline. The real `build_graph` wiring runs over fake nodes, a recording projection in place
of the read model, and a `MemorySaver` in place of Postgres. That is enough to prove the
things the story is about — the status sequence, the pause, the resume — because none of
them depend on what the nodes compute; the `live` restart test covers the Postgres saver.
"""

from __future__ import annotations

import asyncio
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
    CHECK_REQS,
    INTERRUPT_BID_ID,
    INTERRUPT_PROBLEMS,
    INTERRUPT_REQUIREMENTS,
    SCORE_VERDICT,
    ReadModelProjection,
    StageError,
    build_graph,
    fan_out_checks,
    initial_state,
    stage,
)
from crossbid.agent.state import BidState, ExtractionProblem, ExtractionProblemReason
from crossbid.ingestion.storage import StorageError
from crossbid.models.matrix import MatrixRow, RowStatus
from crossbid.models.requirement import (
    Checkability,
    Requirement,
    RequirementCategory,
    RequirementKind,
    RequirementStage,
)
from crossbid.models.tender import BidStatus
from crossbid.models.verdict import Decision, Gap, GapSeverity, Verdict
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


WAIT_TIMEOUT_S = 5.0
"""How long a lane waits for its siblings before the fan-out is declared broken."""

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

    @property
    def written_matrix(self) -> list[Sequence[MatrixRow]]:
        return [value for kind, value in self.events if kind == "matrix"]

    @property
    def written_verdicts(self) -> list[Verdict]:
        return [value for kind, value in self.events if kind == "verdict"]

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

    async def write_matrix_rows(
        self, *, company_id: str, bid_id: str, rows: Sequence[MatrixRow]
    ) -> int:
        assert (company_id, bid_id) == (COMPANY_ID, BID_ID)
        self.events.append(("matrix", list(rows)))
        return len(rows)

    async def set_verdict(self, *, company_id: str, bid_id: str, verdict: Verdict) -> None:
        assert (company_id, bid_id) == (COMPANY_ID, BID_ID)
        self.events.append(("verdict", verdict))


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


def plan_node(country: str = "de") -> Any:
    async def plan_checks(state: BidState, config: RunnableConfig | None = None) -> Any:
        return {"bidder_country": country}

    return plan_checks


def check_node(lanes: list[BidState]) -> Any:
    """A lane, recording the payload it was sent and answering one row per requirement."""

    async def check_reqs(state: BidState, config: RunnableConfig | None = None) -> Any:
        lanes.append(state)
        return {
            "matrix_rows": [
                MatrixRow(
                    id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"matrix:{row.id}")),
                    requirement_id=row.id,
                    status=RowStatus.PARTIALLY_SUPPORTED,
                    agent_rationale="checked by a fake",
                )
                for row in state.get("requirements", [])
            ]
        }

    return check_reqs


class InFlightCounter:
    """A checking lane that records how many lanes were running at the same moment.

    Every lane waits for the last one to start before any of them returns, so the peak is
    the real parallelism and not an artefact of a fast fake finishing first.
    """

    def __init__(self, expected: int) -> None:
        self.lanes = 0
        self.peak = 0
        self.checked = 0
        self._expected = expected
        self._in_flight = 0
        self._all_started = asyncio.Event()

    async def node(self, state: BidState, config: RunnableConfig | None = None) -> Any:
        self.lanes += 1
        self.checked += len(state.get("requirements", []))
        self._in_flight += 1
        self.peak = max(self.peak, self._in_flight)
        if self._in_flight >= self._expected:
            self._all_started.set()
        # A lane that returned before its siblings started would make the peak an artefact
        # of how fast a fake is, so every lane waits until all of them have arrived. It is
        # also the failure mode the assertion needs: a run that opens fewer lanes than
        # `expected` deadlocks here rather than passing quietly.
        await asyncio.wait_for(self._all_started.wait(), timeout=WAIT_TIMEOUT_S)
        self._in_flight -= 1
        return {"matrix_rows": []}


def score_node(decision: Decision = Decision.CONDITIONAL) -> Any:
    """The scorer, faked: S3.4.1's rules are asserted in `test_scoring.py`, and what the
    graph has to prove is only that its output is projected under the `scoring` stage."""

    async def score_verdict(state: BidState, config: RunnableConfig | None = None) -> Any:
        return {
            "verdict": Verdict(
                decision=decision,
                gaps=(Gap(requirement_id="a", severity=GapSeverity.OPEN_ITEM, summary="x"),),
                rationale="scored by a fake",
                mandatory_total=len(state.get("requirements", [])),
                mandatory_supported=0,
                partially_supported_rows=1,
            )
        }

    return score_verdict


async def crashing(state: BidState, config: RunnableConfig | None = None) -> Any:
    raise RuntimeError("Der Bieter muss ... (text quoted from the tender)")


def compile_graph(
    settings: Settings,
    *,
    saver: MemorySaver,
    projection: RecordingProjection,
    parse: Any | None = None,
    extract: Any | None = None,
    plan: Any | None = None,
    check: Any | None = None,
    score: Any | None = None,
) -> Any:
    return build_graph(
        settings,
        FakeDatabase(),  # type: ignore[arg-type]
        parse_docs=parse if parse is not None else parse_node(problems=[PARSE_PROBLEM]),
        extract_reqs=(
            extract if extract is not None else extract_node(ROWS, problems=[EXTRACT_PROBLEM])
        ),
        plan_checks=plan if plan is not None else plan_node(),
        check_reqs=check if check is not None else check_node([]),
        score_verdict=score if score is not None else score_node(),
        projection=projection,
        checkpointer=saver,
    )


CONFIG = bid_run_config(BID_ID, thread_id=thread_id_of(BID_ID))


# -------------------------------------------------------------------- the status sequence


async def test_the_status_sequence_is_written_to_the_read_model_in_order(
    offline_settings: Settings,
) -> None:
    """`checking` appears once per stage entered, so once for the plan and once per lane —
    two rows over five lanes is two. The poller reads the same word either way."""
    # Arrange
    projection = RecordingProjection()
    graph = compile_graph(offline_settings, saver=MemorySaver(), projection=projection)

    # Act
    await graph.ainvoke(initial_state(bid_row()), CONFIG)

    # Assert
    assert projection.statuses == [
        BidStatus.PARSING,
        BidStatus.EXTRACTING,
        BidStatus.CHECKING,
        BidStatus.CHECKING,
        BidStatus.CHECKING,
        BidStatus.SCORING,
        BidStatus.AWAITING_REVIEW,
    ]


async def test_problems_are_projected_cumulatively_after_every_node(
    offline_settings: Settings,
) -> None:
    """The poller reads the whole list, so each write carries everything so far."""
    projection = RecordingProjection()
    graph = compile_graph(offline_settings, saver=MemorySaver(), projection=projection)

    await graph.ainvoke(initial_state(bid_row()), CONFIG)

    # After parse: its one problem. After extract: both. Then `plan_checks` and each lane
    # write the same accumulated two, which is why a lane's `Send` payload carries the list
    # (`check_reqs.lane_state`): arriving without it would write an empty one over them. The
    # interrupt node writes nothing on its first pass -- `interrupt()` raises before the
    # stage reaches its exit projection.
    assert projection.problem_counts == [1, 2, 2, 2, 2, 2]


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
    `write_requirements` call -- the empty-list branch of `_project`. No requirements also
    means no lane: the third write is `plan_checks`, and the fan-out goes straight to
    `score_verdict`, which is the fourth -- a bid that found nothing still owes its
    reviewer a verdict (S3.4.1)."""
    projection = RecordingProjection()
    graph = compile_graph(
        offline_settings,
        saver=MemorySaver(),
        projection=projection,
        parse=parse_node(),
        extract=extract_node([]),
    )

    await graph.ainvoke(initial_state(bid_row()), CONFIG)

    assert projection.problem_counts == [0, 0, 0, 0]
    assert projection.written_rows == []
    assert len(projection.written_verdicts) == 1


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
    # The checkpoint holds scoring's output; its `status` names the stage that produced it.
    assert snapshot.values["status"] is BidStatus.SCORING
    assert snapshot.values["verdict"].decision is Decision.CONDITIONAL
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


# ----------------------------------------------------------------------- the checking fan-out


async def test_every_requirement_is_checked_and_the_matrix_is_projected_lane_by_lane(
    offline_settings: Settings,
) -> None:
    """Each lane's stage writes its own share, so the poller watches the matrix fill in."""
    # Arrange
    lanes: list[BidState] = []
    projection = RecordingProjection()
    graph = compile_graph(
        offline_settings, saver=MemorySaver(), projection=projection, check=check_node(lanes)
    )

    # Act
    await graph.ainvoke(initial_state(bid_row()), CONFIG)

    # Assert -- two requirements, two lanes, one row each, written separately
    assert len(lanes) == 2
    assert [len(written) for written in projection.written_matrix] == [1, 1]
    checked = {row.requirement_id for written in projection.written_matrix for row in written}
    assert checked == {row.id for row in ROWS}


async def test_no_more_lanes_run_at_once_than_the_settings_allow(
    offline_settings: Settings,
) -> None:
    """The story's concurrency limit. It is the number of `Send`s, so counting the lanes in
    flight counts exactly the thing the setting bounds."""
    # Arrange -- more requirements than lanes, each lane held until every lane has started
    limit = offline_settings.runtime.agent.check_concurrency
    rows = [requirement(f"Klausel {index}", page=index + 1) for index in range(limit * 3)]
    projection = RecordingProjection()
    counter = InFlightCounter(limit)
    graph = compile_graph(
        offline_settings,
        saver=MemorySaver(),
        projection=projection,
        extract=extract_node(rows),
        check=counter.node,
    )

    # Act
    await graph.ainvoke(initial_state(bid_row()), CONFIG)

    # Assert
    assert counter.lanes == limit
    assert counter.peak == limit
    assert counter.checked == len(rows)


async def test_a_bid_with_no_requirements_parks_without_checking_anything(
    offline_settings: Settings,
) -> None:
    """An empty fan-out returns a node name, not an empty list of `Send`s: an empty list
    leaves the superstep with no successor and the run would finish unreviewed."""
    # Arrange
    lanes: list[BidState] = []
    projection = RecordingProjection()
    graph = compile_graph(
        offline_settings,
        saver=MemorySaver(),
        projection=projection,
        extract=extract_node([]),
        check=check_node(lanes),
    )

    # Act
    await graph.ainvoke(initial_state(bid_row()), CONFIG)
    snapshot = await graph.aget_state(CONFIG)

    # Assert
    assert lanes == []
    assert projection.written_matrix == []
    assert snapshot.next == (AWAIT_REVIEW,)


def test_the_fan_out_sends_to_the_checking_node_and_carries_the_bidder(
    offline_settings: Settings,
) -> None:
    # Arrange
    state: BidState = {
        "bid_id": BID_ID,
        "company_id": COMPANY_ID,
        "bidder_country": "de",
        "requirements": list(ROWS),
        "extraction_problems": [EXTRACT_PROBLEM],
    }

    # Act
    sends = fan_out_checks(state, concurrency=5)

    # Assert
    assert isinstance(sends, list)
    assert {send.node for send in sends} == {CHECK_REQS}
    assert all(send.arg["bidder_country"] == "de" for send in sends)
    assert all(send.arg["extraction_problems"] == [EXTRACT_PROBLEM] for send in sends)


def test_the_fan_out_names_the_scorer_when_there_is_nothing_to_check() -> None:
    """Not the interrupt: an unscored bid would park with no answer for its reviewer."""
    assert fan_out_checks({"requirements": []}, concurrency=5) == SCORE_VERDICT


async def test_every_lane_is_sent_the_country_the_planner_resolved(
    offline_settings: Settings,
) -> None:
    lanes: list[BidState] = []
    graph = compile_graph(
        offline_settings,
        saver=MemorySaver(),
        projection=RecordingProjection(),
        plan=plan_node("fr"),
        check=check_node(lanes),
    )

    await graph.ainvoke(initial_state(bid_row()), CONFIG)

    assert [lane["bidder_country"] for lane in lanes] == ["fr", "fr"]


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
    assert projection.statuses == [
        BidStatus.EXTRACTING,
        BidStatus.CHECKING,
        BidStatus.CHECKING,
        BidStatus.CHECKING,
        BidStatus.SCORING,
        BidStatus.AWAITING_REVIEW,
    ]
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

    async def write_matrix_rows(db: Any, **kwargs: Any) -> int:
        calls.append(("matrix", kwargs))
        return len(kwargs["rows"])

    monkeypatch.setattr(graph_module, "set_bid_status", set_bid_status)
    monkeypatch.setattr(graph_module, "set_bid_problems", set_bid_problems)
    monkeypatch.setattr(graph_module, "write_requirements", write_requirements)

    async def set_bid_verdict(db: Any, **kwargs: Any) -> None:
        calls.append(("verdict", kwargs))

    monkeypatch.setattr(graph_module, "write_matrix_rows", write_matrix_rows)
    monkeypatch.setattr(graph_module, "set_bid_verdict", set_bid_verdict)
    projection = ReadModelProjection(FakeDatabase())

    # Act
    await projection.set_status(company_id=COMPANY_ID, bid_id=BID_ID, status=BidStatus.PARSING)
    await projection.set_problems(
        company_id=COMPANY_ID, bid_id=BID_ID, problems=[PARSE_PROBLEM]
    )
    written = await projection.write_requirements(company_id=COMPANY_ID, rows=list(ROWS))
    matrix = [
        MatrixRow(
            id=str(uuid.uuid4()),
            requirement_id=ROWS[0].id,
            status=RowStatus.PARTIALLY_SUPPORTED,
            agent_rationale="Kein Nachweis gefunden.",
        )
    ]
    checked = await projection.write_matrix_rows(
        company_id=COMPANY_ID, bid_id=BID_ID, rows=matrix
    )

    verdict = Verdict(
        decision=Decision.NO_GO,
        gaps=(Gap(requirement_id=ROWS[0].id, severity=GapSeverity.BLOCKING, summary="x"),),
        rationale="Dieses Angebot wird nicht empfohlen.",
        mandatory_total=2,
        mandatory_supported=1,
        partially_supported_rows=0,
    )
    await projection.set_verdict(company_id=COMPANY_ID, bid_id=BID_ID, verdict=verdict)

    # Assert -- every call carries the tenant, and problems go out as plain JSON
    assert written == 2
    assert checked == 1
    # The verdict is dumped to JSON here, not in the read model: that module never imports
    # from `models/verdict`, the same rule that keeps `problems` raw on the way through.
    assert calls[-1] == (
        "verdict",
        {
            "company_id": COMPANY_ID,
            "bid_id": BID_ID,
            "verdict": verdict.model_dump(mode="json"),
        },
    )
    assert calls[-2] == ("matrix", {"company_id": COMPANY_ID, "bid_id": BID_ID, "rows": matrix})
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
        "bidder_country": "",
        "matrix_rows": [],
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
