"""S1.2.1 — `GET /tenders/search`: TED, proxied so the browser never talks to it directly.

**Why a proxy rather than a fetch from the browser.** TED is a public API and the search
would work from the client, but routing it here keeps one boundary rule intact: the browser
talks to FastAPI and to nothing else (docs/project-plan.md → *Frontend ↔ backend boundary*).
That is what lets the expert-query rules, the language resolution and the retry live in one
tested place instead of being reimplemented in TypeScript, and it is what makes the search
reachable by the agent's own tool (`search_ted`, S1.2.2) without a second implementation.

**The results are scoped by the caller's company only in the sense that they are behind
authentication.** Published notices are public; there is no tenant data here, and no
`WHERE company_id` to get wrong. The dependency is still `current_company`, because an
unauthenticated route is a free proxy for anybody who finds it.

**Titles come back in the bidder's own language where TED has one.** That is not a
translation we pay for: TED publishes every notice title in all 24 EU languages, so the
company profile's `language` is passed down and a German bidder reads a French tender's
title in German for nothing. It is the cheapest instance of the cross-border wedge in the
whole product.

**The call runs in a thread, not on the event loop.** The TED client is synchronous, and a
slow answer from TED is the normal case rather than the exception, so awaiting it inline
would make one bidder's search everybody else's latency.

**`TedUnavailableError` becomes 503 and never an empty page.** "Nothing matched your search"
and "TED did not answer" are different facts, and a bidder who is told the first when the
second happened will widen a query that was never the problem.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator
from typing import Annotated, Final

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import StringConstraints

from crossbid.auth import CompanyContext, current_company
from crossbid.models.ted import MAX_RESULTS_PER_PAGE, Cpv, TedSearchPage, TedSearchQuery
from crossbid.reference.ted_client import (
    TED_REQUEST_TIMEOUT_S,
    TedSearchClient,
    TedUnavailableError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenders", tags=["tenders"])

TED_UNAVAILABLE_DETAIL: Final = (
    "TED could not be reached just now. Your search was not run — try again in a moment."
)

CountryParam = Annotated[str, StringConstraints(pattern=r"^[A-Za-z]{2}$")]
"""Either case at the door, lower case inside.

The constraint sits on the *parameter* rather than inside the handler on purpose: FastAPI
validates an annotated query parameter itself and answers 422 naming the field, whereas
building the model in the body turns the same mistake into a 500 with a stack trace. The
model's own `Alpha2` is lower-case only, which is right for the model and wrong for a URL
somebody typed."""


def get_ted_client() -> Iterator[TedSearchClient]:
    """One client per request, **closed when the response is done** (M22).

    A `yield` dependency rather than a plain return: FastAPI runs the rest of the generator
    after the response, which is the only place a per-request client can be closed. Returning
    it left a connection pool and a TLS context to the garbage collector on every search.

    One per request and not one per process: the search is rare, a pooled connection to TED
    buys nothing, and a module-level client would outlive the event loop in tests.
    """
    with httpx.Client(timeout=TED_REQUEST_TIMEOUT_S) as http:
        yield TedSearchClient(http)


@router.get(
    "/search",
    response_model=TedSearchPage,
    summary="Search TED for published contract notices",
)
async def search_tenders(
    cpv: Annotated[list[Cpv], Query(description="CPV codes, full eight digits")] = [],  # noqa: B006
    country: Annotated[list[CountryParam], Query(description="ISO 3166-1 alpha-2")] = [],  # noqa: B006
    keyword: Annotated[str | None, Query(description="Free text across the notice")] = None,
    contract_notices_only: Annotated[bool, Query()] = True,
    limit: Annotated[int, Query(ge=1, le=MAX_RESULTS_PER_PAGE)] = 20,
    page: Annotated[int, Query(ge=1)] = 1,
    language: Annotated[
        str | None, Query(description="Read titles in this language where TED has one")
    ] = None,
    company: CompanyContext = Depends(current_company),
    client: TedSearchClient = Depends(get_ted_client),
) -> TedSearchPage:
    """One page of notices. A malformed CPV is 422 here rather than a 400 from TED."""
    query = TedSearchQuery(
        cpv=tuple(cpv),
        countries=tuple(code.lower() for code in country),
        keyword=keyword,
        contract_notices_only=contract_notices_only,
        limit=limit,
        page=page,
    )
    try:
        # `TedSearchClient` is synchronous (one `httpx.Client`), and this handler is not:
        # calling it inline would park the event loop for up to `TED_REQUEST_TIMEOUT_S` x the
        # client's attempts, stalling every other request in the process -- document polls,
        # a bid run's own callbacks, a chat turn. `routers/documents.py` already hands the
        # synchronous Storage client to a thread for the same reason.
        return await asyncio.to_thread(client.search, query, language=language)
    except TedUnavailableError as error:
        logger.warning("TED search failed for company %s: %s", company.company_id, error)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail=TED_UNAVAILABLE_DETAIL
        ) from error
