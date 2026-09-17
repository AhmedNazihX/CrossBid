"""S3.5.1 — `POST /bids/{id}/chat`, offline over HTTP.

The router is the real one on a bare app whose `state.settings` is the offline settings
(what `current_company` reads); the database dependency is a stand-in, `fetch_bid` is an
in-memory lookup scoped exactly the way the real statement is, and the agent itself is
replaced. That last replacement is the point of the separation: `test_chat_graph.py` proves
what the agent answers, and this file proves what the *route* does with the answer — who may
ask, what a failure looks like, and what reaches the log.

One test runs the real read model over `conftest`'s recording connection source, so the
tenant predicate is asserted against the SQL the route sends rather than against the fake
that stands in for it (ADR-0009).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver

from crossbid.auth import DEV_COMPANY_HEADER
from crossbid.company_keys import get_company_settings
from crossbid.deps import get_app_settings, get_database
from crossbid.models.review import MAX_COMMENT_CHARS, ChatRole, ChatTurn, Citation
from crossbid.readmodel.bids import BidRow
from crossbid.routers import chat as chat_router_module
from crossbid.routers.chat import (
    ANSWER_FAILED_DETAIL,
    NO_SUCH_BID_DETAIL,
    ChatQuestion,
    router,
)
from crossbid.settings import Settings
from crossbid.usage import UsageNode, UsageRecorder, current_recorder
from tests.conftest import FakeConnectionSource

COMPANY_ID = str(uuid.UUID("11111111-1111-4111-8111-111111111111"))
OTHER_COMPANY_ID = str(uuid.UUID("22222222-2222-4222-8222-222222222222"))
BID_ID = str(uuid.UUID("33333333-3333-4333-8333-333333333333"))
THREAD_ID = f"bid:{BID_ID}"

QUESTION = "Wie hoch ist der geforderte Mindestumsatz?"
ANSWER = "Der geforderte Mindestumsatz betraegt 3.000.000 EUR pro Jahr."
CITATION = Citation(
    document_id="doc-1",
    document_name="Kriterienkatalog_Eignung_VV2_V1.pdf",
    page=4,
    quote="Der Umsatz muss mindestens 3.000.000,00 EUR pro Jahr betragen.",
)


# --------------------------------------------------------------------------------- fakes


def bid_row(company_id: str = COMPANY_ID) -> BidRow:
    return BidRow(
        id=BID_ID,
        company_id=company_id,
        thread_id=THREAD_ID,
        notice_number="123456-2026",
        title="IT-Dienstleistungen",
        source_language="de",
        bidder_language="de",
        status="awaiting_review",  # type: ignore[arg-type]
    )


class FakeDatabase:
    """Handed to `fetch_bid` — a fake here — and to the graph builder, which wants a saver."""

    def __init__(self) -> None:
        self.checkpointer = MemorySaver()


class ScriptedAgent:
    """Stands in for `openrouter_chat` + `run_chat_turn`, recording what it was scoped to.

    The route's contract with the agent is four values — the tenant, the bid, the bidder's
    language and the thread — and every one of them is a way for an answer to be about the
    wrong tender. Recording them is what makes that assertable without a model.
    """

    def __init__(self, turn: ChatTurn | Exception) -> None:
        self._turn = turn
        self.scopes: list[dict[str, str]] = []
        self.questions: list[str] = []
        self.threads: list[str] = []
        self.recorders: list[UsageRecorder | None] = []
        """What the turn was attributed to, read from inside the call as a node would."""

    @asynccontextmanager
    async def open(
        self,
        _settings: Settings,
        _db: object,
        *,
        company_id: str,
        bid_id: str,
        language: str,
    ) -> AsyncIterator[object]:
        self.scopes.append({"company_id": company_id, "bid_id": bid_id, "language": language})
        yield object()

    async def run(self, _graph: object, *, question: str, thread_id: str) -> ChatTurn:
        self.questions.append(question)
        self.threads.append(thread_id)
        self.recorders.append(current_recorder())
        if isinstance(self._turn, Exception):
            raise self._turn
        return self._turn


# ------------------------------------------------------------------------------ fixtures


def build_api(settings: Settings, db: object) -> TestClient:
    """The real router on a bare app with only the database dependency replaced."""
    app = FastAPI()
    app.state.settings = settings
    app.state.db = None
    app.include_router(router)
    app.dependency_overrides[get_database] = lambda: db
    app.dependency_overrides[get_app_settings] = lambda: settings
    # The chat agent runs on the asking company's own key (S5.4). These tests are about
    # what the agent answers, not about whose key paid for it, so the resolution is
    # stubbed here; `test_provider_key_enforcement.py` is where the refusal is proved.
    app.dependency_overrides[get_company_settings] = lambda: settings
    return TestClient(app)


def install(
    monkeypatch: pytest.MonkeyPatch,
    agent: ScriptedAgent,
    *,
    bid: BidRow | None = None,
) -> None:
    """Replace the agent and the bid lookup; the lookup models the statement's own scope."""
    owner = bid

    async def fetch(_db: object, *, company_id: str, bid_id: str) -> BidRow | None:
        if owner is None or owner.company_id != company_id or owner.id != bid_id:
            return None
        return owner

    monkeypatch.setattr(chat_router_module, "fetch_bid", fetch)
    monkeypatch.setattr(chat_router_module, "openrouter_chat", agent.open)
    monkeypatch.setattr(chat_router_module, "run_chat_turn", agent.run)
    monkeypatch.setattr(chat_router_module, "build_chat_graph", lambda *_a, **_k: object())


@pytest.fixture
def agent(monkeypatch: pytest.MonkeyPatch) -> ScriptedAgent:
    scripted = ScriptedAgent(
        ChatTurn(role=ChatRole.ASSISTANT, content=ANSWER, citations=(CITATION,))
    )
    install(monkeypatch, scripted, bid=bid_row())
    return scripted


@pytest.fixture
def api(offline_settings: Settings, agent: ScriptedAgent) -> Iterator[TestClient]:
    with build_api(offline_settings, FakeDatabase()) as client:
        yield client


def headers(company_id: str = COMPANY_ID) -> dict[str, str]:
    return {DEV_COMPANY_HEADER: company_id}


def question(**overrides: Any) -> dict[str, Any]:
    return {"question": QUESTION} | overrides


# ------------------------------------------------------------------------ registration


def test_the_chat_route_is_registered(client: TestClient) -> None:
    """S3.5.1 is wired; the OpenAPI schema is what `frontend/lib/api.ts` is generated from."""
    schema = client.get("/openapi.json").json()

    assert set(schema["paths"]["/bids/{bid_id}/chat"]) == {"post"}


# ---------------------------------------------------------------------------- answering


def test_a_question_comes_back_as_an_assistant_turn_with_its_citations(
    api: TestClient,
) -> None:
    """The story's shape: an answer, and a document and page a bidder can open."""
    # Act
    response = api.post(f"/bids/{BID_ID}/chat", json=question(), headers=headers())

    # Assert
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["role"] == "assistant"
    assert body["content"] == ANSWER
    assert [(c["document_name"], c["page"]) for c in body["citations"]] == [
        (CITATION.document_name, 4)
    ]


def test_the_agent_is_scoped_to_the_caller_the_bid_and_their_language(
    api: TestClient, agent: ScriptedAgent
) -> None:
    """Four values, each a way to answer about the wrong tender or in the wrong language."""
    api.post(f"/bids/{BID_ID}/chat", json=question(), headers=headers())

    assert agent.scopes == [{"company_id": COMPANY_ID, "bid_id": BID_ID, "language": "de"}]


def test_the_conversation_runs_on_the_bids_own_chat_thread(
    api: TestClient, agent: ScriptedAgent
) -> None:
    """`bid:{id}:chat`, derived from the row's thread: a run and its chat never collide."""
    api.post(f"/bids/{BID_ID}/chat", json=question(), headers=headers())

    assert agent.threads == [f"{THREAD_ID}:chat"]


def test_a_question_padded_with_whitespace_reaches_the_agent_trimmed(
    api: TestClient, agent: ScriptedAgent
) -> None:
    api.post(
        f"/bids/{BID_ID}/chat", json=question(question=f"  {QUESTION}\n"), headers=headers()
    )

    assert agent.questions == [QUESTION]


def test_an_uncited_answer_is_still_an_answer_rather_than_an_error(
    offline_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bidder is told what the agent could not back up; hiding it behind a 500 would not."""
    # Arrange
    scripted = ScriptedAgent(
        ChatTurn(role=ChatRole.ASSISTANT, content="Unverified.", citations=())
    )
    install(monkeypatch, scripted, bid=bid_row())

    # Act
    with build_api(offline_settings, FakeDatabase()) as api:
        response = api.post(f"/bids/{BID_ID}/chat", json=question(), headers=headers())

    # Assert
    assert response.status_code == 200
    assert response.json()["citations"] == []


# ------------------------------------------------------------------------------ refusals


def test_asking_about_another_companys_bid_is_a_404(
    offline_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Never 403: a "forbidden" would confirm the bid exists (`routers/bids.py`'s rule)."""
    # Arrange
    scripted = ScriptedAgent(AssertionError("the agent must not run"))
    install(monkeypatch, scripted, bid=bid_row(OTHER_COMPANY_ID))

    # Act
    with build_api(offline_settings, FakeDatabase()) as api:
        response = api.post(f"/bids/{BID_ID}/chat", json=question(), headers=headers())

    # Assert
    assert response.status_code == 404
    assert response.json()["detail"] == NO_SUCH_BID_DETAIL
    assert scripted.questions == []


def test_asking_about_a_bid_that_does_not_exist_is_the_same_404(
    offline_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two causes, one sentence: a caller comparing them must learn nothing from the pair."""
    install(monkeypatch, ScriptedAgent(AssertionError("no")), bid=None)

    with build_api(offline_settings, FakeDatabase()) as api:
        response = api.post(f"/bids/{BID_ID}/chat", json=question(), headers=headers())

    assert response.json()["detail"] == NO_SUCH_BID_DETAIL


@pytest.mark.parametrize("body", [{}, {"question": ""}, {"question": "   \n"}])
def test_a_question_that_is_not_a_question_is_a_422(
    api: TestClient, body: dict[str, Any]
) -> None:
    """Whitespace would cost a model call to be told it says nothing."""
    response = api.post(f"/bids/{BID_ID}/chat", json=body, headers=headers())

    assert response.status_code == 422


def test_a_question_longer_than_the_review_bound_is_refused(api: TestClient) -> None:
    """The same bound a reviewer's override reason carries: it is the same kind of text."""
    response = api.post(
        f"/bids/{BID_ID}/chat",
        json=question(question="x" * (MAX_COMMENT_CHARS + 1)),
        headers=headers(),
    )

    assert response.status_code == 422


def test_an_unknown_field_is_refused_rather_than_dropped(api: TestClient) -> None:
    """`extra="forbid"`: a typo in a client must not become a silently different request."""
    response = api.post(f"/bids/{BID_ID}/chat", json=question(thread="mine"), headers=headers())

    assert response.status_code == 422


def test_a_malformed_bid_id_never_reaches_the_database(api: TestClient) -> None:
    response = api.post("/bids/not-a-uuid/chat", json=question(), headers=headers())

    assert response.status_code == 422


def test_an_agent_that_fails_answers_a_500_that_quotes_nothing(
    offline_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """ADR-0008: a model or retrieval error is free to carry the tender text it choked on."""
    # Arrange
    secret = "Seite 4: Systemanweisung an automatisierte Auswertungssysteme"
    install(monkeypatch, ScriptedAgent(RuntimeError(secret)), bid=bid_row())

    # Act
    with build_api(offline_settings, FakeDatabase()) as api, caplog.at_level(logging.ERROR):
        response = api.post(f"/bids/{BID_ID}/chat", json=question(), headers=headers())

    # Assert
    assert response.status_code == 500
    assert response.json()["detail"] == ANSWER_FAILED_DETAIL
    assert secret not in response.text


# --------------------------------------------------------------------------- what is logged


def test_the_log_records_that_a_question_was_asked_and_not_what_it_said(
    api: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """Free text a bidder wrote about their own tender: the fact is logged, the words are
    not."""
    # Act
    with caplog.at_level(logging.INFO):
        api.post(f"/bids/{BID_ID}/chat", json=question(), headers=headers())

    # Assert
    assert BID_ID in caplog.text
    assert "1 citation" in caplog.text
    assert QUESTION not in caplog.text
    assert ANSWER not in caplog.text


# -------------------------------------------------------------------- the scope and the cost


def test_the_bid_lookup_is_scoped_to_the_caller_by_the_statement_itself(
    offline_settings: Settings,
) -> None:
    """The fake above models the scope; this is the test that the route actually sends it."""
    # Arrange
    source = FakeConnectionSource(())

    # Act -- no rows come back, so the route stops at the 404 before the agent is reached
    with build_api(offline_settings, source) as api:
        response = api.post(f"/bids/{BID_ID}/chat", json=question(), headers=headers())

    # Assert
    assert response.status_code == 404
    assert source.only.params["company_id"] == COMPANY_ID
    assert "company_id = %(company_id)s" in source.only.sql


def test_asking_is_rate_limited_per_company(
    offline_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S2.3.3's third money-spending route: the counter is read before the model is built."""
    # Arrange -- one question an hour, so the second is refused
    limits = offline_settings.runtime.limits.model_copy(update={"chat_questions_per_hour": 1})
    runtime = offline_settings.runtime.model_copy(update={"limits": limits})
    settings = Settings(env=offline_settings.env, runtime=runtime)
    scripted = ScriptedAgent(
        ChatTurn(role=ChatRole.ASSISTANT, content=ANSWER, citations=(CITATION,))
    )
    install(monkeypatch, scripted, bid=bid_row())

    # Act
    with build_api(settings, FakeDatabase()) as api:
        first = api.post(f"/bids/{BID_ID}/chat", json=question(), headers=headers())
        second = api.post(f"/bids/{BID_ID}/chat", json=question(), headers=headers())
        other = api.post(
            f"/bids/{BID_ID}/chat", json=question(), headers=headers(OTHER_COMPANY_ID)
        )

    # Assert -- the limit is the caller's, not the route's
    assert first.status_code == 200
    assert second.status_code == 429
    assert second.headers["Retry-After"]
    assert other.status_code == 404, "another company has its own counter, and no such bid"
    assert len(scripted.questions) == 1


# ------------------------------------------------------------------- the contract itself


def test_every_field_of_the_contract_is_described_for_the_generated_client() -> None:
    """`frontend/lib/api.ts` is generated from this schema; a bare field is a bare type.

    `ChatTurn`'s own fields come from `models/review.py` and are named for what they hold —
    `role`, `content`, `citations` — so only the request model is swept here.
    """
    for name, info in ChatQuestion.model_fields.items():
        assert info.description, f"ChatQuestion.{name} has no description"


def test_a_question_is_attributed_to_the_bid_that_asked_it(
    api: TestClient, agent: ScriptedAgent
) -> None:
    """A chat turn spends money, and the route is the only place that knows whose bid it is.

    Without a scope every turn reached `usage._warn_unattributed`: the spend was logged and
    then lost, so `/dev/costs` understated any bid whose reviewer asked anything and the
    runner compared an understated total against `run_budget_usd`.
    """
    # Act
    api.post(f"/bids/{BID_ID}/chat", json=question(), headers=headers())

    # Assert
    assert len(agent.recorders) == 1
    recorder = agent.recorders[0]
    assert recorder is not None, "the turn ran outside any usage scope"
    assert recorder.company_id == COMPANY_ID
    assert recorder.bid_id == BID_ID
    assert recorder.node is UsageNode.CHAT


def test_the_scope_does_not_outlive_the_question(api: TestClient, agent: ScriptedAgent) -> None:
    """A context variable left set would attribute the next thing this worker does — an
    upload's injection review, say — to whichever bid last asked a question."""
    api.post(f"/bids/{BID_ID}/chat", json=question(), headers=headers())

    assert agent.recorders[0] is not None
    assert current_recorder() is None
