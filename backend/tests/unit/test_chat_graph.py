"""S3.5.1 — "ask the tender": the loop, the budget, and the citations that cannot be invented.

Fully offline. There is no model and no socket: `ChatContext` is two async callables and a
tuple of tools, so every branch below is driven by a script, and the checkpointer is
`MemorySaver`. That is the same design `check_loop.py` proved out for the checking loop, and
it is what lets the two hardest assertions in this file be made on real bytes:

> a citation is the **tool artifact**, never the model's retelling of it

`test_a_citation_carries_the_retrieved_quote_and_not_the_models_words` is that one: the fake
tool returns a passage saying one thing while the model's prose says another, and the
delivered citation has to be the tool's bytes. Its sibling,
`test_a_citation_of_a_passage_nobody_retrieved_is_dropped`, is the other half.

> a reference can only ever resolve against a search made for **this** question

`test_a_passage_retrieved_on_an_earlier_turn_cannot_be_cited_now` is that one, and it is the
property the checkpointer hands us rather than one this module enforces: an artifact comes
back from a checkpoint as a plain `dict`, so `retrieved_from` recognises nothing on an
earlier turn's tool message. The test pins the behaviour so that a future serialiser which
*did* restore the model could not silently widen what a citation may point at.

The fakes are local to this module rather than in `conftest.py` because nothing else drives
them: `test_chat_router.py` replaces the agent wholesale, which is the point of it being a
router test. `conftest` holds what two modules share, and a fake that only one module uses
belongs where it is used.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import pytest
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel

from crossbid.agent import chat_graph as chat_module
from crossbid.agent.chat_graph import (
    ANSWER_ASK,
    BUDGET_SPENT,
    CHAT_MODEL_ROLE,
    CHAT_TOOLS,
    MAX_ANSWER_CHARS,
    NO_ANSWER,
    NOTHING_FOUND,
    TOOL_FAILED,
    UNCITED_ANSWER,
    ChatAnswer,
    ChatContext,
    ChatError,
    PassageRef,
    build_chat_graph,
    chat_thread_id,
    openrouter_chat,
    preamble_for,
    retrieved_from,
    run_chat_turn,
    structured_answer,
)
from crossbid.guards.wrap import DATA_BLOCK_POSTAMBLE, DATA_BLOCK_PREAMBLE
from crossbid.ingestion.embeddings import EmbeddingsClient
from crossbid.models.matrix import ReviewerStatus, RowStatus
from crossbid.models.review import ChatRole, ChatTurn
from crossbid.settings import ModelRole, Settings
from crossbid.tools import rag as rag_module
from crossbid.tools.get_matrix import MatrixDigest, MatrixLine
from crossbid.tools.rag import RagHit, RagSearchResult
from tests.conftest import BID_ID, COMPANY_ID, DOCUMENT_ID, FakeConnectionSource

pytestmark = pytest.mark.anyio

THREAD = "bid:33333333-3333-4333-8333-333333333333:chat"
QUESTION = "Wie hoch ist der geforderte Mindestumsatz?"
FOLLOW_UP = "Und bis wann muss ich das nachweisen?"

TENDER_QUOTE = "Der Umsatz muss mindestens 3.000.000,00 EUR pro Jahr betragen."
COMPANY_QUOTE = "Der Jahresumsatz 2025 betrug 7.400.000,00 EUR."
TENDER_DOCUMENT = "Kriterienkatalog_Eignung_VV2_V1.pdf"

TENDER_SEARCH = "tender_rag_search"
COMPANY_SEARCH = "company_rag_search"


# --------------------------------------------------------------------------------- fakes


def hit(quote: str = TENDER_QUOTE, *, page: int = 4, name: str = TENDER_DOCUMENT) -> RagHit:
    return RagHit(
        document_id=DOCUMENT_ID,
        document_name=name,
        page=page,
        pages=(page,),
        quote=quote,
        score=0.81,
    )


def result(*hits: RagHit, query: str = "Mindestumsatz") -> RagSearchResult:
    return RagSearchResult(query=query, corpus="this bid's tender pack", hits=hits)


def search_tool(
    *results: RagSearchResult | Exception, name: str = TENDER_SEARCH
) -> tuple[BaseTool, list[str]]:
    """A `content_and_artifact` tool exactly like the real ones, answering from a script.

    Returns the tool and the queries it was asked, which is what a budget assertion counts:
    the routing's own arithmetic and the tool's record have to agree.
    """
    seen: list[str] = []

    class Args(BaseModel):
        query: str

    async def run(query: str) -> tuple[str, RagSearchResult]:
        seen.append(query)
        answer = results[min(len(seen) - 1, len(results) - 1)]
        if isinstance(answer, Exception):
            raise answer
        return answer.render(), answer

    tool = StructuredTool.from_function(
        coroutine=run,
        name=name,
        description="search",
        args_schema=Args,
        response_format="content_and_artifact",
    )
    return tool, seen


def calls(*names_and_queries: tuple[str, str]) -> AIMessage:
    """A turn that asks for tools. A fresh message every time, and that matters: `add_messages`
    stamps an id onto the object it is handed, so re-returning one scripted instance on a
    later turn would *replace* the earlier message rather than append a new one."""
    return AIMessage(
        content="",
        tool_calls=[
            {"name": name, "args": {"query": query}, "id": f"call-{index}", "type": "tool_call"}
            for index, (name, query) in enumerate(names_and_queries, start=1)
        ],
    )


def stop(text: str = "Ich habe genug gelesen.") -> AIMessage:
    """A turn with no tool calls: the model is ready to answer."""
    return AIMessage(content=text)


def answered(
    text: str = "Der geforderte Mindestumsatz betraegt 3.000.000 EUR pro Jahr.",
    *,
    citations: Sequence[tuple[int, int]] = ((1, 1),),
) -> ChatAnswer:
    return ChatAnswer(
        answer=text,
        citations=[PassageRef(search=search, passage=passage) for search, passage in citations],
    )


class ScriptedChat:
    """A `ChatContext`'s two seams, scripted, recording every prompt it was handed.

    The recording is what makes the data-block and preamble assertions possible at all: both
    are promises about the bytes the model receives, and nothing short of holding those bytes
    checks them. Each entry may be a callable, so a turn can be built fresh per call.
    """

    def __init__(
        self,
        turns: Sequence[AIMessage | Exception],
        answer: ChatAnswer | Exception | Sequence[ChatAnswer | Exception] = (),
    ) -> None:
        self._turns = list(turns)
        self._answers: list[ChatAnswer | Exception] = (
            list(answer)
            if isinstance(answer, Sequence) and not isinstance(answer, str)
            else [answer]
        ) or [answered()]
        self.prompts: list[list[BaseMessage]] = []
        self.answer_prompts: list[list[BaseMessage]] = []

    async def turn(self, messages: Sequence[BaseMessage]) -> AIMessage:
        self.prompts.append(list(messages))
        scripted = self._turns[min(len(self.prompts) - 1, len(self._turns) - 1)]
        if isinstance(scripted, Exception):
            raise scripted
        # Copied rather than returned as-is: see `calls`.
        return scripted.model_copy(update={"id": None})

    async def answer(self, messages: Sequence[BaseMessage]) -> ChatAnswer:
        self.answer_prompts.append(list(messages))
        scripted = self._answers[min(len(self.answer_prompts) - 1, len(self._answers) - 1)]
        if isinstance(scripted, Exception):
            raise scripted
        return scripted

    @property
    def turns_taken(self) -> int:
        return len(self.prompts)

    @property
    def answers_asked(self) -> int:
        return len(self.answer_prompts)


def context(
    model: ScriptedChat,
    *,
    tools: Sequence[BaseTool] = (),
    max_tool_calls: int = 4,
    preamble: Sequence[BaseMessage] = (),
) -> ChatContext:
    return ChatContext(
        turn=model.turn,
        answer=model.answer,
        tools=tuple(tools),
        max_tool_calls=max_tool_calls,
        preamble=tuple(preamble),
    )


async def ask(
    model: ScriptedChat,
    *,
    tools: Sequence[BaseTool] = (),
    max_tool_calls: int = 4,
    preamble: Sequence[BaseMessage] = (),
    question: str = QUESTION,
    thread: str = THREAD,
    graph: Any = None,
) -> ChatTurn:
    """One question through the real graph on an in-memory checkpointer."""
    compiled = (
        graph
        if graph is not None
        else build_chat_graph(
            context(model, tools=tools, max_tool_calls=max_tool_calls, preamble=preamble),
            checkpointer=MemorySaver(),
        )
    )
    return await run_chat_turn(compiled, question=question, thread_id=thread)


def joined(messages: Sequence[BaseMessage]) -> str:
    return "\n".join(str(message.content) for message in messages)


# --------------------------------------------------------------- the story's two criteria


async def test_an_answer_cites_the_document_and_page_it_was_retrieved_from() -> None:
    """The story's first criterion: given a question, the answer cites document and page."""
    # Arrange
    tool, _ = search_tool(result(hit()))
    model = ScriptedChat([calls((TENDER_SEARCH, "Mindestumsatz")), stop()], answered())

    # Act
    turn = await ask(model, tools=[tool])

    # Assert
    assert turn.role is ChatRole.ASSISTANT
    assert [(c.document_name, c.page) for c in turn.citations] == [(TENDER_DOCUMENT, 4)]
    assert UNCITED_ANSWER not in turn.content


async def test_a_question_nothing_answers_says_so_instead_of_guessing() -> None:
    """The story's second criterion, and the model is never even asked for prose.

    An empty search is the moment a model is most willing to be helpful, so the answer is
    ours: there is no branch on which four empty searches become a paragraph about a tender.
    """
    # Arrange
    tool, _ = search_tool(result())
    model = ScriptedChat([calls((TENDER_SEARCH, "Mindestumsatz")), stop()], answered())

    # Act
    turn = await ask(model, tools=[tool])

    # Assert
    assert turn.content == NOTHING_FOUND
    assert turn.citations == ()
    assert model.answers_asked == 0, "an unanswerable question costs no closing call"


async def test_a_question_the_model_never_searched_for_is_not_answered_either() -> None:
    """ "It did not look" and "it looked and found nothing" are the same answer to a bidder:
    neither produces a claim, because neither produced a passage."""
    model = ScriptedChat([stop()], answered())

    turn = await ask(model)

    assert turn.content == NOTHING_FOUND
    assert model.answers_asked == 0


# --------------------------------------------------------------------------- the citations


async def test_a_citation_carries_the_retrieved_quote_and_not_the_models_words() -> None:
    """The product's central promise, at the one place it could be lost.

    The tool's passage and the model's prose deliberately disagree; the citation is the
    tool's bytes, so a model that retypes a quote changes nothing a bidder is shown.
    """
    # Arrange
    tool, _ = search_tool(result(hit()))
    model = ScriptedChat(
        [calls((TENDER_SEARCH, "Umsatz")), stop()],
        answered("Der Mindestumsatz betraegt 30.000.000 EUR."),
    )

    # Act
    turn = await ask(model, tools=[tool])

    # Assert
    assert turn.citations[0].quote == TENDER_QUOTE
    assert "30.000.000" in turn.content, "the model's prose is shown as written"


async def test_a_citation_of_a_passage_nobody_retrieved_is_dropped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A reference into a search that never happened cites nothing at all."""
    # Arrange
    tool, _ = search_tool(result(hit()))
    model = ScriptedChat(
        [calls((TENDER_SEARCH, "Umsatz")), stop()], answered(citations=((9, 1), (1, 9)))
    )

    # Act
    with caplog.at_level(logging.INFO):
        turn = await ask(model, tools=[tool])

    # Assert
    assert turn.citations == ()
    assert UNCITED_ANSWER in turn.content
    assert caplog.text.count("Dropped a chat citation") == 2


async def test_one_passage_cited_from_two_searches_is_shown_once() -> None:
    """A model citing the same paper twice is citing one paper; the bidder is sent once."""
    # Arrange
    tool, _ = search_tool(result(hit()), result(hit()))
    model = ScriptedChat(
        [calls((TENDER_SEARCH, "Umsatz")), calls((TENDER_SEARCH, "Umsatz")), stop()],
        answered(citations=((1, 1), (2, 1))),
    )

    # Act
    turn = await ask(model, tools=[tool])

    # Assert
    assert len(turn.citations) == 1


async def test_an_answer_that_cites_nothing_says_so_rather_than_looking_backed() -> None:
    """Decision 4: the prose stays — it may be right — and the reader is told it is
    unverified."""
    # Arrange
    tool, _ = search_tool(result(hit()))
    model = ScriptedChat([calls((TENDER_SEARCH, "Umsatz")), stop()], answered(citations=()))

    # Act
    turn = await ask(model, tools=[tool])

    # Assert
    assert turn.content.endswith(UNCITED_ANSWER)
    assert turn.citations == ()


async def test_an_uncited_answer_and_its_notice_together_stay_inside_the_bubble() -> None:
    """The notice never gives way to the prose: it is the reason the answer has no citations."""
    # Arrange
    tool, _ = search_tool(result(hit()))
    model = ScriptedChat(
        [calls((TENDER_SEARCH, "Umsatz")), stop()], answered("x" * 5_000, citations=())
    )

    # Act
    turn = await ask(model, tools=[tool])

    # Assert
    assert len(turn.content) <= MAX_ANSWER_CHARS
    assert turn.content.endswith(UNCITED_ANSWER)


async def test_a_long_cited_answer_is_trimmed_to_the_bubble() -> None:
    tool, _ = search_tool(result(hit()))
    model = ScriptedChat([calls((TENDER_SEARCH, "Umsatz")), stop()], answered("y" * 5_000))

    turn = await ask(model, tools=[tool])

    assert len(turn.content) == MAX_ANSWER_CHARS


async def test_an_empty_answer_is_replaced_rather_than_shown_as_a_blank_bubble() -> None:
    """A model that answers with whitespace has said nothing; saying so beats showing it."""
    tool, _ = search_tool(result(hit()))
    model = ScriptedChat([calls((TENDER_SEARCH, "Umsatz")), stop()], answered("   \n"))

    turn = await ask(model, tools=[tool])

    assert turn.content == NO_ANSWER


async def test_a_matrix_digest_is_citable_and_an_empty_matrix_is_not() -> None:
    """`get_matrix` is the third citable source, and a clause with no page is a None slot."""
    # Arrange
    line = MatrixLine(
        status=RowStatus.PARTIALLY_SUPPORTED,
        reviewer_status=ReviewerStatus.PENDING,
        document_name=TENDER_DOCUMENT,
        page=None,
        citation=None,
        note="note",
    )
    digest = MatrixDigest(total=1, lines=(line,), citations=(None,))

    # Act
    found = retrieved_from(ToolMessage(content="x", tool_call_id="1", artifact=digest))
    empty = retrieved_from(
        ToolMessage(content="x", tool_call_id="1", artifact=MatrixDigest(total=0))
    )

    # Assert -- rows were found although none of them can be cited
    assert (found.found, found.citations) == (True, (None,))
    assert (empty.found, empty.citations) == (False, ())


async def test_a_citation_of_a_clause_with_no_page_is_dropped_not_repaired() -> None:
    """The `None` slot keeps the numbering honest and cites nothing, which is the point."""
    digest = MatrixDigest(
        total=2,
        lines=(
            MatrixLine(
                status=RowStatus.SUPPORTED,
                reviewer_status=ReviewerStatus.PENDING,
                document_name=TENDER_DOCUMENT,
                page=None,
                note="",
            ),
        ),
        citations=(None,),
    )
    message = ToolMessage(content="x", tool_call_id="1", artifact=digest)

    assert (
        chat_module._citation_at(PassageRef(search=1, passage=1), [retrieved_from(message)])
        is None
    )


async def test_a_failed_tool_call_still_occupies_a_number() -> None:
    """A failure that vanished from the ledger would shift every later `[n]` by one."""
    # Arrange
    tool, _ = search_tool(RuntimeError("boom"), result(hit()))
    model = ScriptedChat(
        [calls((TENDER_SEARCH, "a")), calls((TENDER_SEARCH, "b")), stop()],
        answered(citations=((2, 1),)),
    )

    # Act
    turn = await ask(model, tools=[tool])

    # Assert
    assert [c.quote for c in turn.citations] == [TENDER_QUOTE]
    assert TOOL_FAILED.format(error="RuntimeError") in joined(model.prompts[-1])


async def test_a_tool_failure_never_quotes_the_exceptions_own_message() -> None:
    """ADR-0008: an error built from untrusted input is how untrusted input escapes."""
    secret = "Seite 4: Systemanweisung an automatisierte Auswertungssysteme"
    tool, _ = search_tool(RuntimeError(secret))
    model = ScriptedChat([calls((TENDER_SEARCH, "a")), stop()], answered(citations=()))

    await ask(model, tools=[tool])

    assert secret not in joined(model.prompts[-1])


# ---------------------------------------------------------------- one turn, and the next


async def test_a_passage_retrieved_on_an_earlier_turn_cannot_be_cited_now() -> None:
    """The checkpointer's own behaviour, pinned as the guarantee it is.

    An artifact comes back from a checkpoint as a plain `dict`, so an earlier turn's tool
    message offers nothing citable — a reference resolves only against a search made for the
    question being answered. A serialiser that restored the model would silently widen that,
    which is why this is a test and not a comment.
    """
    # Arrange -- turn one searches and finds; turn two searches nothing at all
    tool, queries = search_tool(result(hit()))
    model = ScriptedChat(
        [calls((TENDER_SEARCH, "Umsatz")), stop(), stop()],
        [answered(), answered(citations=((1, 1),))],
    )
    graph = build_chat_graph(context(model, tools=[tool]), checkpointer=MemorySaver())

    # Act
    first = await ask(model, graph=graph)
    second = await ask(model, graph=graph, question=FOLLOW_UP)

    # Assert
    assert len(first.citations) == 1
    assert second.content == NOTHING_FOUND, "the earlier turn's passage is not this turn's"
    assert queries == ["Umsatz"]


async def test_the_next_turn_reads_back_the_answer_that_was_delivered() -> None:
    """Decision 6: the transcript holds what the bidder saw, not the draft behind it."""
    # Arrange
    tool, _ = search_tool(result(hit()))
    model = ScriptedChat(
        [calls((TENDER_SEARCH, "Umsatz")), stop("ein Entwurf"), stop()],
        [answered("Die gelieferte Antwort."), answered(citations=())],
    )
    graph = build_chat_graph(context(model, tools=[tool]), checkpointer=MemorySaver())

    # Act
    await ask(model, graph=graph)
    await ask(model, graph=graph, question=FOLLOW_UP)

    # Assert -- the second turn's prompt carries the delivered sentence and not the draft
    history = joined(model.prompts[-1])
    assert "Die gelieferte Antwort." in history
    assert "ein Entwurf" not in history


# ------------------------------------------------------------------------- the tool budget


async def test_the_budget_is_spent_and_never_exceeded() -> None:
    """A model that keeps searching is stopped by the graph, not by its own restraint."""
    # Arrange
    tool, queries = search_tool(result(hit()))
    model = ScriptedChat([calls((TENDER_SEARCH, "immer wieder"))], answered())

    # Act
    turn = await ask(model, tools=[tool], max_tool_calls=2)

    # Assert
    assert len(queries) == 2
    assert turn.citations != ()


async def test_a_batch_that_would_not_fit_is_refused_whole() -> None:
    """`ToolNode` runs a batch or none of it, so the overshoot is refused rather than run."""
    # Arrange
    tool, queries = search_tool(result(hit()))
    model = ScriptedChat(
        [
            calls((TENDER_SEARCH, "eins")),
            calls((TENDER_SEARCH, "zwei"), (TENDER_SEARCH, "drei")),
            stop(),
        ],
        answered(),
    )

    # Act
    turn = await ask(model, tools=[tool], max_tool_calls=2)

    # Assert -- the first call ran; the batch of two would have made three. The refusal is
    # read off the closing call's prompt because `budget` routes straight to `answer`: the
    # model is never asked again, which is what "refused whole" costs and saves.
    assert queries == ["eins"]
    assert BUDGET_SPENT in joined(model.answer_prompts[-1])
    assert turn.citations != ()


async def test_every_refused_call_is_answered_so_the_conversation_can_continue() -> None:
    """A provider rejects the next request when a tool call is left dangling.

    Asserted against the transcript rather than against a prompt, because on this path there
    is no prompt to assert against: nothing ran, so nothing was found, so the closing call is
    skipped entirely. The refusals still have to be *written*, or the next question on this
    thread would send the provider an assistant turn whose tool calls were never answered.
    """
    # Arrange
    tool, _ = search_tool(result(hit()))
    model = ScriptedChat([calls((TENDER_SEARCH, "a"), (TENDER_SEARCH, "b"))], answered())
    graph = build_chat_graph(
        context(model, tools=[tool], max_tool_calls=1), checkpointer=MemorySaver()
    )

    # Act
    turn = await ask(model, graph=graph)
    state = await graph.aget_state({"configurable": {"thread_id": THREAD}})

    # Assert
    refusals = [
        message
        for message in state.values["messages"]
        if isinstance(message, ToolMessage) and message.content == BUDGET_SPENT
    ]
    assert len(refusals) == 2
    assert turn.content == NOTHING_FOUND
    assert model.answers_asked == 0


async def test_a_budget_of_zero_answers_without_searching() -> None:
    """The degenerate configuration still produces a turn rather than a dangling call."""
    tool, queries = search_tool(result(hit()))
    model = ScriptedChat([calls((TENDER_SEARCH, "a"))], answered())

    turn = await ask(model, tools=[tool], max_tool_calls=0)

    assert queries == []
    assert turn.content == NOTHING_FOUND


def test_a_negative_budget_is_refused_where_it_is_configured() -> None:
    """A context that cannot be satisfied fails at the call that built it, not in a request."""
    with pytest.raises(ValueError, match="cannot be negative"):
        ChatContext(turn=_never, answer=_never, tools=(), max_tool_calls=-1)


async def _never(_messages: Sequence[BaseMessage]) -> Any:  # pragma: no cover - never called
    raise AssertionError("the scripted seam was called")


# ------------------------------------------------------------------------------ the prompt


async def test_a_retrieved_passage_reaches_the_model_inside_a_data_block() -> None:
    """S2.3.2: retrieved tender text is untrusted, and the tool wraps it before we see it."""
    # Arrange
    tool, _ = search_tool(result(hit()))
    model = ScriptedChat([calls((TENDER_SEARCH, "Umsatz")), stop()], answered())

    # Act
    await ask(model, tools=[tool])

    # Assert
    text = joined(model.prompts[-1])
    assert DATA_BLOCK_PREAMBLE.split("{nonce}")[0] in text
    assert DATA_BLOCK_POSTAMBLE.split("{nonce}")[0] in text
    assert TENDER_QUOTE in text


async def test_the_closing_ask_comes_after_the_whole_conversation() -> None:
    """Models weight recency: the operative instruction is the last thing said."""
    # Arrange
    tool, _ = search_tool(result(hit()))
    model = ScriptedChat([calls((TENDER_SEARCH, "Umsatz")), stop()], answered())

    # Act
    await ask(model, tools=[tool])

    # Assert
    asked = model.answer_prompts[0]
    assert isinstance(asked[-1], HumanMessage)
    assert asked[-1].content == ANSWER_ASK


async def test_the_preamble_is_sent_every_turn_and_stored_on_none_of_them() -> None:
    """The standing instructions are ours and identical each turn; checkpointing them would
    pin a thread to the prompt version that started it."""
    # Arrange
    standing = SystemMessage(content="Du bist Crossbid.")
    tool, _ = search_tool(result(hit()))
    model = ScriptedChat([calls((TENDER_SEARCH, "Umsatz")), stop()], answered())
    graph = build_chat_graph(
        context(model, tools=[tool], preamble=[standing]), checkpointer=MemorySaver()
    )

    # Act
    await ask(model, graph=graph)
    state = await graph.aget_state({"configurable": {"thread_id": THREAD}})

    # Assert
    assert model.prompts[0][0] is standing
    assert model.answer_prompts[0][0] is standing
    assert not [m for m in state.values["messages"] if isinstance(m, SystemMessage)]


def test_the_chat_prompt_names_the_bidders_language_and_the_budget(
    offline_settings: Settings,
) -> None:
    """The story says German; the rule is the bidder's own configured language."""
    # Act
    preamble = preamble_for(offline_settings, bidder_language="de")

    # Assert
    task = str(preamble[-1].content)
    assert "Write the answer in de" in task
    assert str(offline_settings.runtime.agent.max_tool_calls_per_requirement) in task


def test_the_system_prompt_is_omitted_when_a_deployment_has_none(
    offline_settings: Settings,
) -> None:
    """`app_settings.system_prompt` is nullable; a `None` must not become the string 'None'."""
    runtime = offline_settings.runtime.model_copy(update={"system_prompt": None})
    settings = Settings(env=offline_settings.env, runtime=runtime)

    assert len(preamble_for(settings, bidder_language="de")) == 1


# ------------------------------------------------------------------------------- the wiring


def test_the_chat_agent_is_made_of_the_three_tools_the_plan_names() -> None:
    """ADR-0052's per-node set. The three absentees are the point of the constant."""
    assert set(CHAT_TOOLS) == {"tender_rag_search", "company_rag_search", "get_matrix"}
    assert "search_ted" not in CHAT_TOOLS
    assert "currency_convert" not in CHAT_TOOLS
    assert "ecertis_evidence_lookup" not in CHAT_TOOLS


def test_chat_runs_on_the_cheap_slug(offline_settings: Settings) -> None:
    """`settings.default.yaml` names `cheap` "classification, chat, injection guard"."""
    assert CHAT_MODEL_ROLE is ModelRole.CHEAP
    assert offline_settings.runtime.models.for_role(CHAT_MODEL_ROLE) != (
        offline_settings.runtime.models.for_role(ModelRole.EXTRACT)
    )


def test_the_chat_thread_is_the_bids_own_thread_with_a_suffix() -> None:
    """A run and its chat must never collide: the bid's checkpoint holds an interrupt."""
    assert chat_thread_id("bid:abc") == "bid:abc:chat"
    assert chat_thread_id("bid:abc") != "bid:abc"


async def test_the_production_context_builds_the_enabled_tools_and_closes_its_client(
    offline_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bound set is `CHAT_TOOLS` ∩ `enabled_tools`, and no tool opens a pool of its own.

    `search_ted` is enabled in the settings and still absent, which is what this asserts: an
    interactive route must not carry a live third-party call (ADR-0045).
    """

    # Arrange
    def refuse(*_args: Any, **_kwargs: Any) -> Any:  # pragma: no cover -- must not be called
        raise AssertionError("a tool built its own EmbeddingsClient")

    monkeypatch.setattr(rag_module, "EmbeddingsClient", refuse)
    closed: list[str] = []
    monkeypatch.setattr(EmbeddingsClient, "aclose", lambda self: _record_close(closed))

    # Act
    async with openrouter_chat(
        offline_settings,
        FakeConnectionSource(),
        company_id=COMPANY_ID,
        bid_id=BID_ID,
        language="de",
    ) as built:
        names = sorted(tool.name for tool in built.tools)
        budget = built.max_tool_calls

    # Assert
    assert names == ["company_rag_search", "get_matrix", "tender_rag_search"]
    assert "search_ted" in offline_settings.runtime.enabled_tools, (
        "the settings must still enable it, or this test proves nothing"
    )
    assert budget == offline_settings.runtime.agent.max_tool_calls_per_requirement
    assert closed == ["closed"]


async def _record_close(closed: list[str]) -> None:
    closed.append("closed")


# ------------------------------------------------------------------------------- the seams


async def test_the_answer_seam_revalidates_what_the_model_returned() -> None:
    """`with_structured_output` may hand back a dict; a model's output is never trusted raw."""

    class Model:
        async def ainvoke(self, _messages: Any, /) -> Any:
            return {"answer": "kurz", "citations": [{"search": 1, "passage": 1}]}

    answer = await structured_answer(Model())([])

    assert answer.citations[0].search == 1


async def test_a_graph_that_finished_without_an_answer_is_a_loud_failure() -> None:
    """Unreachable through the real nodes, and a silent `None` here would reach a bidder."""

    class Empty:
        async def ainvoke(self, *_args: Any, **_kwargs: Any) -> Any:
            return {"messages": [HumanMessage(content="x")], "answer": None}

    with pytest.raises(ChatError):
        await run_chat_turn(Empty(), question=QUESTION, thread_id=THREAD)


async def test_a_thread_with_no_question_still_has_a_turn_to_read() -> None:
    """`this_turn` falls back to the whole transcript rather than indexing off the end."""
    assert chat_module.this_turn([AIMessage(content="x")]) == (AIMessage(content="x"),)


async def test_a_tool_message_carrying_nothing_citable_contributes_a_numbered_slot() -> None:
    """The `dict` case, the failure case and the unknown-artifact case are one behaviour."""
    assert retrieved_from(ToolMessage(content="x", tool_call_id="1")) is chat_module.NOTHING
    assert (
        retrieved_from(ToolMessage(content="x", tool_call_id="1", artifact={"hits": []}))
        is chat_module.NOTHING
    )


async def test_the_company_corpus_is_citable_too() -> None:
    """Both retrieval tools feed the same ledger; the evidence side is not a second case."""
    # Arrange
    tool, _ = search_tool(
        result(hit(COMPANY_QUOTE, page=2, name="Jahresabschluss_2025.pdf")),
        name=COMPANY_SEARCH,
    )
    model = ScriptedChat([calls((COMPANY_SEARCH, "Jahresumsatz")), stop()], answered())

    # Act
    turn = await ask(model, tools=[tool])

    # Assert
    assert turn.citations[0].quote == COMPANY_QUOTE
