"""S3.4.3 — the read model agrees with the checkpoint, asserted over a whole bid.

The plan's rule is stark: the read model is a projection of the graph's state, and if the two
disagree the checkpoint is right and the projection has a bug. Every other test in this suite
checks one write in isolation. This one runs a bid from `START` to `complete` — through the
fan-out, the interrupt, a reviewer's edits and the re-score — and then compares **everything
the poller can see** against `aget_state`.

Two things it deliberately does *not* do.

It does not fake the projection's semantics. `ProjectedReadModel` below stores what the real
statements store: the matrix upsert replaces by `id` and never touches a reviewer column, the
reviewer's update writes only those columns, `problems` and `verdict` are replaced whole.
A convenience fake that simply remembered the last list it was handed would agree with the
checkpoint by construction and prove nothing.

It does not reach Postgres. The SQL itself is asserted in `test_bids_readmodel.py` and
`test_graph.py`; what is unproven without this test is whether `graph._project` maps the
*state* onto those writes faithfully, and that is answerable offline. The `live` restart test
covers the Postgres saver.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from crossbid.agent.graph import build_graph, initial_state
from crossbid.agent.nodes.review import ReviewApplier
from crossbid.agent.nodes.score_verdict import VerdictScorer
from crossbid.agent.state import BidState, ExtractionProblem, ExtractionProblemReason
from crossbid.models.company import CompanyProfile, LegalForm, Tone
from crossbid.models.matrix import MatrixRow, ReviewerStatus, RowStatus
from crossbid.models.requirement import Requirement
from crossbid.models.review import ReviewSubmission, RowEdit
from crossbid.models.tender import BidStatus
from crossbid.models.verdict import Decision, Verdict
from crossbid.readmodel.bids import BidRow, thread_id_of
from crossbid.settings import Settings, bid_run_config
from tests.conftest import requirement

pytestmark = pytest.mark.anyio

COMPANY_ID = str(uuid.uuid4())
BID_ID = str(uuid.uuid4())
CONFIG = bid_run_config(BID_ID, thread_id=thread_id_of(BID_ID))

PROFILE = CompanyProfile(
    name="Musterfirma IT-Dienstleistungen GmbH",
    country="de",
    legal_form=LegalForm.GMBH,
    language="de",
    tone=Tone.PLAIN,
)

REQUIREMENTS = [
    requirement("Mindestjahresumsatz 3.000.000 EUR", identifier=str(uuid.uuid4()), page=4),
    requirement("Mindestens 29 Vollzeitäquivalente", identifier=str(uuid.uuid4()), page=7),
    requirement("Eigenerklärung Ausschlussgründe", identifier=str(uuid.uuid4()), page=9),
]

PROBLEM = ExtractionProblem(
    reason=ExtractionProblemReason.UNREADABLE_DOCUMENT,
    document_name="Anlage_7.pdf",
    pages=(1, 2),
)


# ------------------------------------------------------------- the read model, as it stores


class ProjectedReadModel:
    """A `RunProjection` that stores what the real statements store. See the module docstring.

    Deliberately not a recorder: the point is to reproduce the *semantics* of the four
    writers, so that a projection which wrote the wrong rows would disagree with the
    checkpoint here exactly as it would in Frankfurt.
    """

    def __init__(self) -> None:
        self.status: BidStatus | None = None
        self.problems: list[ExtractionProblem] = []
        self.requirements: dict[str, Requirement] = {}
        self.matrix: dict[str, MatrixRow] = {}
        self.verdict: Verdict | None = None
        self.decision: Decision | None = None
        self.reviews: list[dict[str, Any]] = []

    async def set_status(self, *, company_id: str, bid_id: str, status: BidStatus) -> None:
        self.status = status

    async def set_problems(
        self, *, company_id: str, bid_id: str, problems: Sequence[ExtractionProblem]
    ) -> None:
        self.problems = list(problems)

    async def write_requirements(self, *, company_id: str, rows: Sequence[Requirement]) -> int:
        self.requirements.update({row.id: row for row in rows})
        return len(rows)

    async def write_matrix_rows(
        self, *, company_id: str, bid_id: str, rows: Sequence[MatrixRow]
    ) -> int:
        for row in rows:
            # `UPSERT_MATRIX_ROW`: the agent's columns only. A row a human has already
            # dispositioned keeps that disposition however often it is re-checked.
            kept = self.matrix.get(row.id)
            self.matrix[row.id] = (
                row
                if kept is None
                else row.model_copy(
                    update={
                        "reviewer_status": kept.reviewer_status,
                        "override_reason": kept.override_reason,
                        "attached_doc_ids": kept.attached_doc_ids,
                        "reviewed_at": kept.reviewed_at,
                    }
                )
            )
        return len(rows)

    async def write_reviewed_rows(
        self, *, company_id: str, bid_id: str, rows: Sequence[MatrixRow]
    ) -> int:
        for row in rows:
            # `UPDATE_REVIEWED_ROW`: the reviewer's columns, plus the status they may change.
            stored = self.matrix[row.id]
            self.matrix[row.id] = stored.model_copy(
                update={
                    "status": row.status,
                    "reviewer_status": row.reviewer_status,
                    "override_reason": row.override_reason,
                    "attached_doc_ids": row.attached_doc_ids,
                    "reviewed_at": row.reviewed_at,
                }
            )
        return len(rows)

    async def set_verdict(self, *, company_id: str, bid_id: str, verdict: Verdict) -> None:
        self.verdict = verdict

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
        self.decision = decision
        self.reviews.append(
            {
                "decision": decision,
                "agent_verdict": agent_verdict,
                "final_verdict": final_verdict,
                "override_reason": override_reason,
            }
        )


class FakeCompanies:
    async def get(self, *, company_id: uuid.UUID) -> CompanyProfile | None:
        return PROFILE


class FakeDatabase:
    def __init__(self) -> None:
        self.checkpointer = MemorySaver()

    def connection(self) -> Any:  # pragma: no cover -- never borrowed in these tests
        raise AssertionError("the graph must not borrow a connection here")


# ---------------------------------------------------------------------------- fake nodes


async def parse(state: BidState, config: RunnableConfig | None = None) -> Any:
    return {"documents": [], "extraction_problems": [PROBLEM]}


async def extract(state: BidState, config: RunnableConfig | None = None) -> Any:
    return {"requirements": list(REQUIREMENTS), "extraction_problems": []}


async def plan(state: BidState, config: RunnableConfig | None = None) -> Any:
    return {"bidder_country": "de"}


async def check(state: BidState, config: RunnableConfig | None = None) -> Any:
    """One lane. `unsupported` throughout, so the reviewer has something to disagree with."""
    return {
        "matrix_rows": [
            MatrixRow(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"matrix:{row.id}")),
                requirement_id=row.id,
                status=RowStatus.UNSUPPORTED,
                agent_rationale="Kein Nachweis im Bestand gefunden.",
            )
            for row in state.get("requirements", [])
        ]
    }


def bid_row() -> BidRow:
    return BidRow(
        id=BID_ID,
        company_id=COMPANY_ID,
        thread_id=thread_id_of(BID_ID),
        notice_number="614251-2026",
        title="Netztechnik",
        source_language="de",
        bidder_language="de",
        status=BidStatus.QUEUED,
    )


def compiled(settings: Settings, projection: ProjectedReadModel, saver: MemorySaver) -> Any:
    """The real wiring, with the real scorer and the real review nodes over fake lookups."""
    scorer = VerdictScorer(FakeCompanies())
    return build_graph(
        settings,
        FakeDatabase(),  # type: ignore[arg-type]
        parse_docs=parse,
        extract_reqs=extract,
        plan_checks=plan,
        check_reqs=check,
        score_verdict=scorer,
        apply_review=ReviewApplier(scorer),
        projection=projection,
        checkpointer=saver,
    )


# -------------------------------------------------------------------------------- the test


@pytest.fixture
async def finished(offline_settings: Settings) -> tuple[ProjectedReadModel, Any]:
    """One bid run from `START` to `complete`, with a review that changes a row."""
    projection = ProjectedReadModel()
    graph = compiled(offline_settings, projection, MemorySaver())
    await graph.ainvoke(initial_state(bid_row()), CONFIG)

    parked = await graph.aget_state(CONFIG)
    edited = parked.values["matrix_rows"][1]
    review = ReviewSubmission(
        decision=Decision.CONDITIONAL,
        override_reason="Die Referenzen liegen als Anlage 4 vor.",
        row_edits=(
            RowEdit(
                matrix_row_id=edited.id,
                status=RowStatus.NOT_APPLICABLE,
                override_reason="Gilt nur für Bietergemeinschaften.",
            ),
        ),
    )
    await graph.ainvoke(Command(resume=review.model_dump(mode="json")), CONFIG)
    return projection, graph


async def test_the_run_reaches_complete_through_every_stage(
    finished: tuple[ProjectedReadModel, Any],
) -> None:
    projection, graph = finished

    assert projection.status is BidStatus.COMPLETE
    assert (await graph.aget_state(CONFIG)).next == ()


async def test_the_projected_status_is_the_stage_the_checkpoint_names(
    finished: tuple[ProjectedReadModel, Any],
) -> None:
    """The read model runs one step ahead while a node works, but at rest they agree."""
    projection, graph = finished

    assert (await graph.aget_state(CONFIG)).values["status"] is projection.status


async def test_every_requirement_in_the_checkpoint_is_in_the_read_model(
    finished: tuple[ProjectedReadModel, Any],
) -> None:
    projection, graph = finished
    checkpoint = (await graph.aget_state(CONFIG)).values

    assert {row.id for row in checkpoint["requirements"]} == set(projection.requirements)
    assert len(projection.requirements) == len(REQUIREMENTS)


async def test_every_matrix_row_matches_the_checkpoint_field_for_field(
    finished: tuple[ProjectedReadModel, Any],
) -> None:
    """The strongest assertion here: not the ids, the whole row — status, the reviewer's
    disposition, the reason, the timestamp. A projection that dropped the review would pass
    an id comparison and fail this one."""
    projection, graph = finished
    checkpoint = (await graph.aget_state(CONFIG)).values

    assert len(checkpoint["matrix_rows"]) == len(projection.matrix)
    for row in checkpoint["matrix_rows"]:
        assert projection.matrix[row.id] == row


async def test_the_matrix_is_not_doubled_by_the_review(
    finished: tuple[ProjectedReadModel, Any],
) -> None:
    """`apply_review` returns the whole matrix; under an appending channel the checkpoint
    would hold two copies of every row and the re-score would run over both."""
    projection, graph = finished
    checkpoint = (await graph.aget_state(CONFIG)).values

    assert len(checkpoint["matrix_rows"]) == len(REQUIREMENTS)
    assert len(projection.matrix) == len(REQUIREMENTS)


async def test_the_reviewers_disposition_reached_the_read_model(
    finished: tuple[ProjectedReadModel, Any],
) -> None:
    """The gap this story closed: the agent's upsert cannot write these columns, so without
    `write_reviewed_rows` every row would still read `pending` in the database."""
    projection, _graph = finished
    rows = list(projection.matrix.values())

    assert all(row.reviewer_status is not ReviewerStatus.PENDING for row in rows)
    assert all(row.reviewed_at is not None for row in rows)
    overridden = [row for row in rows if row.reviewer_status is ReviewerStatus.OVERRIDDEN]
    assert len(overridden) == 1
    assert overridden[0].status is RowStatus.NOT_APPLICABLE


async def test_the_projected_verdict_is_the_one_in_the_checkpoint(
    finished: tuple[ProjectedReadModel, Any],
) -> None:
    projection, graph = finished
    checkpoint = (await graph.aget_state(CONFIG)).values

    assert projection.verdict == checkpoint["verdict"]


async def test_the_projected_decision_is_the_reviewers_and_not_the_re_score(
    finished: tuple[ProjectedReadModel, Any],
) -> None:
    """Two answers to two questions (ADR-0025), so the read model must carry both."""
    projection, graph = finished
    checkpoint = (await graph.aget_state(CONFIG)).values

    assert projection.decision is Decision.CONDITIONAL
    assert projection.decision is checkpoint["decision"]
    assert projection.verdict is not None
    assert projection.verdict.decision is Decision.NO_GO


async def test_the_audit_record_is_written_once_with_both_verdicts(
    finished: tuple[ProjectedReadModel, Any],
) -> None:
    projection, graph = finished
    checkpoint = (await graph.aget_state(CONFIG)).values

    assert len(projection.reviews) == 1
    record = projection.reviews[0]
    assert record["agent_verdict"] == checkpoint["agent_verdict"]
    assert record["final_verdict"] == checkpoint["verdict"]
    assert record["override_reason"] == "Die Referenzen liegen als Anlage 4 vor."


async def test_the_problem_list_survives_every_later_node(
    finished: tuple[ProjectedReadModel, Any],
) -> None:
    """`extraction_problems` is an appending channel and a lane arriving without it would
    write an empty list over what parsing reported (S3.3.1)."""
    projection, graph = finished
    checkpoint = (await graph.aget_state(CONFIG)).values

    assert projection.problems == checkpoint["extraction_problems"] == [PROBLEM]
