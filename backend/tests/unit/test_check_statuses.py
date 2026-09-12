"""S3.3.2 — one fixture per status branch: the row's shape, and what the branch costs.

The threat this file is written against is narrow and real: **somebody edits
`prompts/check.md` or swaps the model slug, and the matrix quietly changes shape.** Nothing
in `check_loop.py` would raise — a status is a status, a rationale is a string — so the
damage would show up as a column the reviewer reads differently, a citation that stopped
being attached, or a branch that started spending four tool calls where it used to spend
one. Every test below is an assertion that would fail loudly on that day, and each docstring
says which part of production it is guarding.

`test_check_reqs.py` asks what the *loop* does; this file asks what each `RowStatus` is. So
the table below is the point of the story: one scripted route to every member of `RowStatus`
(`test_the_table_covers_every_status_the_matrix_can_hold` keeps it exhaustive), each run
field by field, with and without an ESPD criterion, and each pinned to the tool calls and
model turns it is supposed to make. Two statuses — `unsupported` and `not_applicable` — have
**no code path at all**: they exist only because the model chose them, which is exactly why a
deterministic fixture has to script the verdict rather than hope to provoke it.
`partially_supported` has three routes and they are separate rows in the table, because they
are three different pieces of production: the requirement that never reaches the model, the
verdict the model chose, and the `supported` that lost its citation.

Everything is offline: the scripted model, the scripted `content_and_artifact` tool and the
hand-built requirement all come from `tests/conftest.py`, shared with `test_check_reqs.py`.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import pytest
from langchain_core.messages import AIMessage

from crossbid.agent.nodes import check_reqs as check_reqs_module
from crossbid.agent.nodes.check_loop import (
    CHECK_PROMPT_NAME,
    MAX_RATIONALE_CHARS,
    NOT_COMPANY_PROPERTY,
    UNCITED_SUPPORT,
    UNCITED_SUPPORT_ROOM,
    CheckedRequirement,
    check_requirement,
    matrix_row_id,
)
from crossbid.agent.nodes.check_reqs import RequirementChecker, openrouter_session
from crossbid.agent.prompts import load_prompt
from crossbid.agent.state import BidState
from crossbid.models.matrix import Evidence, MatrixRow, ReviewerStatus, RowStatus
from crossbid.models.requirement import Checkability
from crossbid.settings import Settings
from crossbid.tools.rag import RagSearchResult
from tests.conftest import (
    BID_ID,
    BIDDER,
    COMPANY_ID,
    DOCUMENT_ID,
    EVIDENCE_NAME,
    QUOTE,
    REAL_CRITERION_ID,
    SUBMIT,
    TURNOVER,
    FakeConnectionSource,
    ScriptedModel,
    ScriptedSession,
    answers,
    check_context,
    hit,
    rag_result,
    rag_tool,
    requirement,
    search_call,
    verdict,
)

pytestmark = pytest.mark.anyio

BUDGET = 4
"""The tool budget every branch below is run under. Large enough that no branch's cost is
the budget's doing -- `test_no_status_branch_can_outrun_its_budget` runs the cap separately."""

SHORTFALL = "Der Jahresumsatz 2024 betrug 1.200.000,00 EUR im Bereich IT-Dienstleistungen."
"""Evidence *against* the turnover requirement, which is what `unsupported` means."""

CITED = Evidence(document_id=DOCUMENT_ID, document_name=EVIDENCE_NAME, page=2, quote=QUOTE)
AGAINST = Evidence(
    document_id=DOCUMENT_ID, document_name=EVIDENCE_NAME, page=9, quote=SHORTFALL
)
"""Written out rather than derived from the fake hit: the assertion is that the matrix cell
carries the bytes the *retrieval* returned, and an expectation computed from the same helper
the tool answers with could not tell that apart from a model that retyped them."""

SUPPORTED_SAYS = "Der Jahresabschluss 2025 weist 7,4 Mio. EUR aus."
UNSUPPORTED_SAYS = "Der Jahresabschluss 2024 weist 1,2 Mio. EUR aus, unter der Schwelle."
NOT_APPLICABLE_SAYS = "Die Klausel gilt fuer Bietergemeinschaften; der Bieter bietet allein."
PARTIAL_SAYS = "Kein Nachweis im Datenraum gefunden."


# ------------------------------------------------------------------------ the branch table


@dataclass(frozen=True)
class Branch:
    """One scripted route to one status, and everything it is supposed to cost.

    `tool_calls` and `model_turns` are part of the fixture rather than an afterthought: a
    prompt that starts telling the model to search before answering `not_applicable` is a
    real change to the run's bill (258 requirements against a $2.50 budget, ADR-0012) and it
    would otherwise land silently.
    """

    name: str
    status: RowStatus
    answer: CheckedRequirement
    rationale: str
    source_text: str = TURNOVER
    checkable: Checkability = Checkability.COMPANY_PROPERTY
    script: Sequence[AIMessage] = (answers(),)
    searches: Sequence[RagSearchResult] = ()
    evidence: Sequence[Evidence] = ()
    tool_calls: int = 0
    model_turns: int = 1

    @property
    def reaches_the_model(self) -> bool:
        return self.checkable is Checkability.COMPANY_PROPERTY


BRANCHES = (
    Branch(
        name="supported",
        status=RowStatus.SUPPORTED,
        script=(search_call(), answers()),
        searches=(rag_result(hit()),),
        answer=verdict(RowStatus.SUPPORTED, rationale=SUPPORTED_SAYS, evidence=((1, 1),)),
        rationale=SUPPORTED_SAYS,
        evidence=(CITED,),
        tool_calls=1,
        model_turns=2,
    ),
    Branch(
        name="unsupported",
        status=RowStatus.UNSUPPORTED,
        script=(search_call(), answers()),
        searches=(rag_result(hit(quote=SHORTFALL, page=9)),),
        answer=verdict(RowStatus.UNSUPPORTED, rationale=UNSUPPORTED_SAYS, evidence=((1, 1),)),
        rationale=UNSUPPORTED_SAYS,
        evidence=(AGAINST,),
        tool_calls=1,
        model_turns=2,
    ),
    Branch(
        name="not_applicable",
        status=RowStatus.NOT_APPLICABLE,
        answer=verdict(RowStatus.NOT_APPLICABLE, rationale=NOT_APPLICABLE_SAYS, evidence=()),
        rationale=NOT_APPLICABLE_SAYS,
    ),
    Branch(
        name="partially_supported: the model's own answer",
        status=RowStatus.PARTIALLY_SUPPORTED,
        answer=verdict(RowStatus.PARTIALLY_SUPPORTED, rationale=PARTIAL_SAYS, evidence=()),
        rationale=PARTIAL_SAYS,
    ),
    Branch(
        name="partially_supported: never reached the model",
        status=RowStatus.PARTIALLY_SUPPORTED,
        source_text=SUBMIT,
        checkable=Checkability.DOCUMENT_SUBMISSION,
        # Scripted to answer `supported` on the first question it is asked, so that a loop
        # that started asking about form-submission duties again (ADR-0003 measured what
        # that costs) could not produce this branch's row by accident.
        answer=verdict(RowStatus.SUPPORTED, rationale=SUPPORTED_SAYS, evidence=((1, 1),)),
        rationale=NOT_COMPANY_PROPERTY,
        model_turns=0,
    ),
    Branch(
        name="partially_supported: downgraded, the citation resolved to nothing",
        status=RowStatus.PARTIALLY_SUPPORTED,
        script=(search_call(), answers()),
        searches=(rag_result(),),
        answer=verdict(RowStatus.SUPPORTED, rationale=PARTIAL_SAYS, evidence=((1, 1),)),
        rationale=f"{PARTIAL_SAYS} {UNCITED_SUPPORT}",
        tool_calls=1,
        model_turns=2,
    ),
)

BRANCH_IDS = [branch.name for branch in BRANCHES]


@dataclass(frozen=True)
class Run:
    """One branch, run: the row it produced, and the two records of what it spent."""

    row: MatrixRow
    model: ScriptedModel
    queries: Sequence[str]


async def run_branch(
    branch: Branch,
    *,
    criterion_id: str | None = None,
    answer: CheckedRequirement | None = None,
    script: Sequence[AIMessage] | None = None,
    max_tool_calls: int = BUDGET,
) -> Run:
    """`check_requirement` over this branch's script. The overrides are for the sweeps."""
    tool, queries = rag_tool(*(branch.searches or (rag_result(),)))
    model = ScriptedModel(
        list(branch.script if script is None else script),
        branch.answer if answer is None else answer,
    )
    row = await check_requirement(
        requirement(branch.source_text, checkable=branch.checkable, criterion_id=criterion_id),
        check_context(model, tools={"company_rag_search": tool}, max_tool_calls=max_tool_calls),
    )
    return Run(row=row, model=model, queries=queries)


def test_the_table_covers_every_status_the_matrix_can_hold() -> None:
    """A fifth `RowStatus` with no fixture is a status no test above says anything about.

    It is not hypothetical: the plan's story text for S3.3.2 still says five statuses, and
    ADR-0013 settled on four. Whichever way that is ever reopened, this fails first.
    """
    # Assert
    assert {branch.status for branch in BRANCHES} == set(RowStatus)
    assert len(BRANCH_IDS) == len(set(BRANCH_IDS))


# ============================================================================ the row shape


@pytest.mark.parametrize("branch", BRANCHES, ids=BRANCH_IDS)
@pytest.mark.parametrize(
    "criterion_id", [None, REAL_CRITERION_ID], ids=["no criterion", "espd criterion"]
)
async def test_each_status_branch_produces_the_row_the_read_model_will_upsert(
    branch: Branch, criterion_id: str | None
) -> None:
    """Every field of the matrix cell, per branch. This is the story's acceptance criterion.

    What breaks in production if it fails: the reviewer's table. A changed status word, a
    citation that stopped being attached to the branch that had one, an eCertis mapping that
    appeared on a requirement with no criterion (or vanished from one with it), a rationale
    that outgrew its column, a `reviewer_status` that no longer starts at `pending` — and the
    id, which is what `matrix_rows` upserts on, so a drifting one writes a second row for the
    same requirement on the next resumed run instead of updating the first.
    """
    # Act
    run = await run_branch(branch, criterion_id=criterion_id)
    row = run.row

    # Assert -- the verdict
    assert row.status is branch.status
    assert row.agent_rationale == branch.rationale
    assert 0 < len(row.agent_rationale) <= MAX_RATIONALE_CHARS

    # Assert -- the citations are the retrieved bytes, quote and page included
    assert row.evidence == tuple(branch.evidence)
    for cited, expected in zip(row.evidence, branch.evidence, strict=True):
        assert cited.quote == expected.quote
        assert cited.page == expected.page
        assert cited.document_id == expected.document_id
        assert cited.document_name == expected.document_name

    # Assert -- eCertis exactly when the requirement carries a criterion
    assert (row.ecertis_evidence is not None) is (criterion_id is not None)
    if row.ecertis_evidence is not None:
        assert row.ecertis_evidence.criterion_id == REAL_CRITERION_ID
        assert row.ecertis_evidence.country == BIDDER.country

    # Assert -- the identity, and the reviewer's half of the row untouched
    expected_requirement = requirement(branch.source_text, checkable=branch.checkable)
    assert row.requirement_id == expected_requirement.id
    assert row.id == matrix_row_id(expected_requirement.id)
    assert uuid.UUID(row.id).version == 5
    assert row.reviewer_status is ReviewerStatus.PENDING
    assert row.override_reason is None
    assert row.attached_doc_ids == ()
    assert row.reviewed_at is None


@pytest.mark.parametrize("branch", BRANCHES, ids=BRANCH_IDS)
async def test_a_supported_row_is_the_only_one_that_must_carry_a_citation(
    branch: Branch,
) -> None:
    """The product's central promise, read off the table rather than off one case.

    `MatrixRow` refuses an uncited `supported`, so this failing means the loop is building a
    row the model would raise on — or, worse, that a branch stopped attaching the evidence it
    retrieved and now reaches the reviewer as an opinion.
    """
    # Act
    run = await run_branch(branch)

    # Assert
    assert run.row.status is not RowStatus.SUPPORTED or run.row.evidence
    assert bool(run.row.evidence) == bool(branch.evidence)


@pytest.mark.parametrize("branch", BRANCHES, ids=BRANCH_IDS)
async def test_no_branch_reaches_supported_on_a_citation_that_resolves_to_nothing(
    branch: Branch,
) -> None:
    """The invariant through the loop, on every branch, and not through `MatrixRow` alone.

    Each branch's own script is kept and only the verdict is replaced by a `supported` citing
    a passage nobody retrieved — the shape of a model that has been told, by a prompt edit,
    to cite more confidently. Production must answer with the downgrade every time: the row
    goes to the reviewer instead of counting towards a `go`. `test_check_reqs.py` asserts the
    downgrade once; what this adds is that no *route* to a row skips it.
    """
    # Act
    run = await run_branch(branch, answer=verdict(RowStatus.SUPPORTED, evidence=((7, 3),)))

    # Assert
    assert run.row.status is RowStatus.PARTIALLY_SUPPORTED
    assert run.row.evidence == ()
    assert run.row.agent_rationale.endswith(UNCITED_SUPPORT) or not branch.reaches_the_model


async def test_a_downgraded_rationale_keeps_the_whole_notice_and_still_fits_the_cell() -> None:
    """The model's sentence gives way to the notice, and the cap is the cell's, not a half's.

    Trimming the model's rationale to the cap and *then* appending the notice put a
    732-character string in a column sized for two sentences; a reviewer would see the notice
    that explains the downgrade cut in half by whatever renders it.
    """
    # Arrange -- a model that pads its rationale past the cap and cites nothing resolvable
    branch = BRANCHES[0]

    # Act
    run = await run_branch(
        branch, answer=verdict(RowStatus.SUPPORTED, rationale="x" * 5_000, evidence=((7, 3),))
    )

    # Assert
    assert len(run.row.agent_rationale) == MAX_RATIONALE_CHARS
    assert run.row.agent_rationale == f"{'x' * UNCITED_SUPPORT_ROOM} {UNCITED_SUPPORT}"


# =========================================================================== what it costs


@pytest.mark.parametrize("branch", BRANCHES, ids=BRANCH_IDS)
async def test_each_status_branch_spends_the_tool_calls_and_turns_it_is_written_for(
    branch: Branch,
) -> None:
    """Per branch, not once globally: a prompt edit moves one branch's cost, not all of them.

    A `not_applicable` that starts searching first, or a `supported` that stops searching at
    all, is a change to the run's bill and to what the citation column can contain — and
    neither would fail any assertion about statuses. The zero-turn branch is the sharpest of
    them: it is the one that keeps 'a duty to submit Formblatt 124' from being priced like a
    company property (ADR-0003).
    """
    # Act
    run = await run_branch(branch)

    # Assert
    assert len(run.queries) == branch.tool_calls
    assert run.model.turns_taken == branch.model_turns
    assert len(run.queries) <= BUDGET
    assert (run.model.turns_taken > 0) is branch.reaches_the_model


@pytest.mark.parametrize("branch", BRANCHES, ids=BRANCH_IDS)
async def test_no_status_branch_can_outrun_its_budget(branch: Branch) -> None:
    """Each branch against a model that never stops searching, under a cap of two.

    The bound the story fixes is a property of the loop's counter rather than of the model's
    restraint, and it has to hold on the way to *every* status — including the branch that is
    supposed to spend nothing, where a regression would mean 258 requirements each paying for
    two searches nobody can use.
    """
    # Arrange
    cap = 2

    # Act
    run = await run_branch(branch, script=(search_call(),), max_tool_calls=cap)

    # Assert
    assert len(run.queries) == (cap if branch.reaches_the_model else 0)
    assert isinstance(run.row, MatrixRow)


@pytest.mark.parametrize("branch", BRANCHES, ids=BRANCH_IDS)
async def test_a_lane_checks_one_requirement_at_a_time_whatever_the_branch(
    branch: Branch,
) -> None:
    """The concurrency bound is the number of lanes, so a lane itself must stay sequential.

    Asserted per branch because the fan-out's arithmetic depends on it: `lanes_of` promises
    at most `check_concurrency` requirements in flight, and a branch that started running its
    requirements concurrently inside the lane would multiply that silently -- against the
    provider's rate limit, not against a test. `peak_in_flight` is the only place it shows.
    """
    # Arrange
    tool, _ = rag_tool(*(branch.searches or (rag_result(),)))
    model = ScriptedModel(list(branch.script), branch.answer)
    session = ScriptedSession(model, tools={"company_rag_search": tool})
    rows = [
        requirement(f"{branch.source_text} ({index})", checkable=branch.checkable)
        for index in range(3)
    ]
    state: BidState = {"bid_id": BID_ID, "company_id": COMPANY_ID, "requirements": rows}

    # Act
    update = await RequirementChecker(session)(state)

    # Assert -- one session, one requirement in flight, and a row for each of them
    assert model.peak_in_flight <= 1
    assert len(update["matrix_rows"]) == 3
    assert session.closed == 1


# ==================================================== the prompt and the schema it asks for


def test_the_check_prompt_documents_every_status_the_schema_offers() -> None:
    """A status the model may answer with but the prompt never defines is a coin toss.

    The failure this catches is the likeliest one in the whole story: `RowStatus` gains or
    loses a member and `prompts/check.md` is not touched, so the model keeps choosing from
    the four words it was told about while the matrix renders a fifth.
    """
    # Act
    text = load_prompt(CHECK_PROMPT_NAME)

    # Assert
    for status in RowStatus:
        assert f"`{status.value}`" in text, status.value


def test_the_verdict_schema_offers_exactly_the_statuses_the_matrix_holds() -> None:
    """The other half: the enum the structured call constrains the model to.

    `CheckedRequirement` is deliberately looser than `MatrixRow` about rationales and
    references, but not about the status word -- a verdict outside `RowStatus` could not
    become a row at all, so the schema and the matrix have to name the same four.
    """
    # Act
    schema: dict[str, Any] = CheckedRequirement.model_json_schema()

    # Assert
    assert schema["$defs"]["RowStatus"]["enum"] == [status.value for status in RowStatus]
    assert set(schema["properties"]) == {"status", "rationale", "evidence"}


class RecordingModel:
    """A chat model that records what it was bound with and answers one fixed verdict."""

    def __init__(self) -> None:
        self.tool_names: list[list[str]] = []
        self.schemas: list[Any] = []

    def bind_tools(self, tools: Sequence[Any]) -> RecordingModel:
        self.tool_names.append(sorted(tool.name for tool in tools))
        return self

    def with_structured_output(self, schema: Any) -> RecordingModel:
        self.schemas.append(schema)
        return self

    async def ainvoke(self, messages: Any, /) -> Any:
        return {"status": "unsupported", "rationale": "Kein Nachweis.", "evidence": []}


async def test_the_schema_the_model_is_asked_for_is_the_one_the_loop_parses(
    offline_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The production binding, end to end, without a provider.

    Two ways this breaks quietly. The session could be changed to ask the model for some
    other schema — a dict, a wider model, the row itself — while `structured_verdict` goes on
    validating `CheckedRequirement`, and every verdict would then fail validation at run time
    and land as a reviewer row with `ValidationError` in it: 258 of them, all plausible. Or
    the two bindings could stop coming from one `ChatOpenAI`, which is how the loop's turns
    and the closing answer end up on different slugs after a settings edit.
    """
    # Arrange
    recorder = RecordingModel()
    monkeypatch.setattr(check_reqs_module, "chat_model", lambda role, settings: recorder)

    # Act
    session = openrouter_session(offline_settings, FakeConnectionSource())
    async with session(COMPANY_ID, BID_ID, BIDDER) as ctx:
        answer = await ctx.verdict([])
        bound = sorted(ctx.tools)

    # Assert -- one model, bound twice, and the answer comes back as the loop's own type
    assert recorder.schemas == [CheckedRequirement]
    assert recorder.tool_names == [bound]
    assert isinstance(answer, CheckedRequirement)
    assert answer.status is RowStatus.UNSUPPORTED
