"""S3.5.1 — `POST /bids/{id}/chat`: one question about one bid, answered with citations.

Thin, like every router here. It proves the bid is the caller's, opens the chat agent for
that scope, runs one turn on the bid's own chat thread and answers the turn that was
delivered. No streaming in v1 (`docs/project-plan.md`, integration point 5): the answer
arrives whole or not at all, and the browser shows a spinner rather than a token stream.

**Why the route hangs off a bid.** The bid is the scope, and it is the scope three times
over: the tenant check, the thread the conversation lives on, and the corpus the two RAG
tools are bound to. Putting it in the path means all three come from one lookup and a client
cannot name one bid in a body while the URL says another. `POST /bids/{id}/review` and
`POST /bids/{id}/feedback` are shaped the same way for the same reason.

**A bid that is not the caller's is 404, never 403**, which is `routers/bids.py`'s rule: a
"forbidden" confirms the id exists. The same answer covers a bid that never existed.

**A chat turn is answerable at any stage of the run.** The route deliberately does not
require `awaiting_review`: `tender_rag_search` works the moment the pack is parsed, and a
bidder watching a five-minute run is exactly the person with a question. What the agent
cannot see yet it says it cannot see — `get_matrix` answers "no rows" rather than guessing,
which is the honest shape of "the check has not got there".

**The question never reaches a log line.** It is free text a bidder wrote about their own
tender, so the log records that a question was asked, for which bid, and whether the answer
came back with citations — never what was asked or answered (`routers/feedback.py`'s rule).

Response fields carry a description where the name does not already say it:
`frontend/lib/api.ts` is generated from this schema.
"""

from __future__ import annotations

import logging
import uuid
from typing import Final

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from crossbid.agent.chat_graph import (
    build_chat_graph,
    chat_thread_id,
    openrouter_chat,
    run_chat_turn,
)
from crossbid.auth import CompanyContext, current_company
from crossbid.db import Database
from crossbid.main import get_app_settings, get_database
from crossbid.models.review import MAX_COMMENT_CHARS, ChatTurn
from crossbid.rate_limit import chat_question_limit
from crossbid.readmodel.bids import fetch_bid
from crossbid.settings import Settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bids", tags=["chat"])

NO_SUCH_BID_DETAIL: Final = "No such bid."
"""The same sentence `routers/bids.py` answers with, and deliberately the same: a caller
comparing the two must not be able to tell "not yours" from "not there"."""

ANSWER_FAILED_DETAIL: Final = (
    "The question could not be answered and nothing about the bid has changed. Ask again; if "
    "it keeps failing, the run's log says why."
)
"""Never quotes the failure. A model or a retrieval error is free to carry the text it
choked on, and that text is a tender (ADR-0008). A chat turn is cheap to retry, which is why
this says so rather than the route trying to repair the answer itself."""


class ChatQuestion(BaseModel):
    """What the bidder wants to know about this bid."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    question: str = Field(
        min_length=1,
        max_length=MAX_COMMENT_CHARS,
        description=(
            "The question, in any language. Answered only from this tender's documents, "
            "your own documents and this bid's compliance matrix"
        ),
    )

    @field_validator("question")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        """Whitespace is not a question: it would cost a model call to be told so."""
        if not value.strip():
            raise ValueError("question must not be blank")
        return value


@router.post(
    "/{bid_id}/chat",
    response_model=ChatTurn,
    summary="Ask a question about this bid",
    # S2.3.3's third money-spending route. Settled before the bid, the tools or the model
    # are looked up, so a caller over its limit costs the server one read of a counter.
    dependencies=[Depends(chat_question_limit)],
)
async def ask_about_bid(
    bid_id: uuid.UUID,
    body: ChatQuestion,
    company: CompanyContext = Depends(current_company),
    db: Database = Depends(get_database),
    settings: Settings = Depends(get_app_settings),
) -> ChatTurn:
    """Answer one question about this bid, with a document and a page behind every claim.

    The conversation continues on `bid:{id}:chat`, so a follow-up question reaches an agent
    that remembers the last one; the citations, though, are only ever resolved against the
    searches made for *this* question (`agent/chat_graph.py`).

    An answer that cites nothing comes back with an empty `citations` list and a sentence
    saying it is unverified, rather than as an error — the bidder is told what the agent
    could and could not back up, which is the whole point of the route.
    """
    company_id = company.company_id
    bid = await fetch_bid(db, company_id=company_id, bid_id=str(bid_id))
    if bid is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NO_SUCH_BID_DETAIL)

    try:
        async with openrouter_chat(
            settings,
            db,
            company_id=company_id,
            bid_id=bid.id,
            language=bid.bidder_language,
        ) as context:
            graph = build_chat_graph(context, checkpointer=db.checkpointer)
            turn = await run_chat_turn(
                graph,
                question=body.question.strip(),
                thread_id=chat_thread_id(bid.thread_id),
            )
    except Exception as exc:
        # Deliberately broad and deliberately loud. Everything below this line — a provider
        # that will not answer, a schema violation, a retrieval error — is one event to the
        # bidder ("ask again"), and a defect here is a bug a maintainer has to see.
        logger.exception("Bid %s: a chat question could not be answered", bid.id)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, detail=ANSWER_FAILED_DETAIL
        ) from exc

    logger.info(
        "Bid %s: a chat question was answered with %d citation(s)", bid.id, len(turn.citations)
    )
    return turn
