# ruff: noqa: RUF001 - the en dash below is TED's own, copied from a live answer
"""S1.2.1 — `GET /tenders/search`, offline and end to end over HTTP.

The real app and the real router; only the TED client is replaced, because it is the one
thing that would open a socket. What is being pinned here is the router's own behaviour —
that filters reach the query, that a malformed CPV is refused before TED ever sees it, and
that an unreachable TED is a 503 rather than an empty result set.

That last one is the point of the module. "Nothing matched your search" and "TED did not
answer" are different facts, and a bidder told the first when the second happened will widen
a query that was never the problem.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from crossbid.auth import DEV_COMPANY_HEADER
from crossbid.main import create_app
from crossbid.models.ted import TedNotice, TedSearchPage, TedSearchQuery
from crossbid.reference.ted_client import TedUnavailableError
from crossbid.routers.tenders import TED_UNAVAILABLE_DETAIL, get_ted_client, router
from crossbid.settings import Settings

COMPANY = "11111111-1111-4111-8111-111111111111"
AS_COMPANY = {DEV_COMPANY_HEADER: COMPANY}

NOTICE = TedNotice(
    publication_number="629621-2026",
    title="France – Systems consultancy services",
    buyer="SPL EAU DU BASSIN RENNAIS",
    description=None,
    deadline=None,
    deadline_utc_offset_minutes=None,
    official_languages=("FRA",),
    submission_languages=("FRA",),
    cpv=("72246000",),
    notice_pdf_url="https://ted.europa.eu/fr/notice/629621-2026/pdf",
    documents_url="https://marches.megalis.bretagne.bzh/entreprise",
)


class FakeTed:
    """Records what the router asked for, and answers with whatever it was given."""

    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[tuple[TedSearchQuery, str | None]] = []
        self.threads: list[str] = []
        self._error = error

    def search(self, query: TedSearchQuery, *, language: str | None = None) -> TedSearchPage:
        self.calls.append((query, language))
        self.threads.append(threading.current_thread().name)
        if self._error is not None:
            raise self._error
        return TedSearchPage(
            notices=(NOTICE,), total=1, page=query.page, limit=query.limit, reachable_total=1
        )


def api(settings: Settings, ted: FakeTed) -> TestClient:
    app = create_app(settings)
    app.include_router(router)
    app.dependency_overrides[get_ted_client] = lambda: ted
    return TestClient(app)


@pytest.fixture
def ted() -> FakeTed:
    return FakeTed()


@pytest.fixture
def client(offline_settings: Settings, ted: FakeTed) -> Iterator[TestClient]:
    with api(offline_settings, ted) as test_client:
        yield test_client


def test_a_search_returns_the_notices_ted_answered_with(client: TestClient) -> None:
    response = client.get("/tenders/search", params={"cpv": "72000000"}, headers=AS_COMPANY)

    assert response.status_code == 200
    assert response.json()["notices"][0]["publication_number"] == "629621-2026"


def test_every_filter_reaches_the_query(client: TestClient, ted: FakeTed) -> None:
    client.get(
        "/tenders/search",
        params={
            "cpv": ["72000000", "79000000"],
            "country": ["FR", "de"],
            "keyword": "cyber",
            "limit": 5,
            "page": 2,
            "language": "de",
        },
        headers=AS_COMPANY,
    )
    query, language = ted.calls[0]

    assert query.cpv == ("72000000", "79000000")
    assert query.countries == ("fr", "de"), "upper case is normalised at the door"
    assert query.keyword == "cyber"
    assert (query.limit, query.page) == (5, 2)
    assert language == "de"


def test_contract_notices_only_is_the_default(client: TestClient, ted: FakeTed) -> None:
    client.get("/tenders/search", headers=AS_COMPANY)

    assert ted.calls[0][0].contract_notices_only is True


@pytest.mark.parametrize("cpv", ["72", "720000000", "72abcdef", ""])
def test_a_cpv_that_is_not_eight_digits_is_refused_before_ted_sees_it(
    client: TestClient, ted: FakeTed, cpv: str
) -> None:
    """`IN (72)` is a 400 from TED; the bidder gets a named field instead."""
    response = client.get("/tenders/search", params={"cpv": cpv}, headers=AS_COMPANY)

    assert response.status_code == 422
    assert ted.calls == []


def test_a_country_that_is_not_two_letters_is_refused(client: TestClient) -> None:
    response = client.get("/tenders/search", params={"country": "FRA"}, headers=AS_COMPANY)

    assert response.status_code == 422


def test_a_limit_beyond_the_page_size_is_refused(client: TestClient) -> None:
    response = client.get("/tenders/search", params={"limit": 500}, headers=AS_COMPANY)

    assert response.status_code == 422


def test_an_unreachable_ted_is_503_and_never_an_empty_page(
    offline_settings: Settings,
) -> None:
    """The distinction the whole route turns on: no answer is not no results."""
    down = FakeTed(TedUnavailableError("no route to host"))

    with api(offline_settings, down) as client:
        response = client.get("/tenders/search", headers=AS_COMPANY)

    assert response.status_code == 503
    assert response.json()["detail"] == TED_UNAVAILABLE_DETAIL


def test_the_failure_never_quotes_ted_s_own_error_to_the_caller(
    offline_settings: Settings,
) -> None:
    """The cause goes to the log; a bidder gets a sentence they can act on."""
    down = FakeTed(TedUnavailableError("no route to host: 10.0.0.1:443"))

    with api(offline_settings, down) as client:
        detail = client.get("/tenders/search", headers=AS_COMPANY).json()["detail"]

    assert "10.0.0.1" not in detail


def test_the_route_is_behind_authentication(client: TestClient) -> None:
    """Notices are public; an unauthenticated route here is a free proxy for anybody."""
    assert client.get("/tenders/search").status_code == 401


def test_the_default_dependency_builds_a_real_client() -> None:
    """Every test above overrides it, so this is the one place the wiring is exercised."""
    from crossbid.reference.ted_client import TedSearchClient

    assert isinstance(get_ted_client(), TedSearchClient)


def test_the_search_runs_off_the_event_loop(client: TestClient, ted: FakeTed) -> None:
    """`TedSearchClient` is synchronous and TED is slow; the handler is not allowed to be.

    Awaiting it inline parked the loop for up to the client's whole budget — twenty seconds
    times two attempts — and every other request in the process waited: document polls, a
    running bid's callbacks, a chat turn. The thread name is the evidence, because a handler
    that regressed to a direct call would run here on the loop's own thread.
    """
    response = client.get("/tenders/search", headers=AS_COMPANY)

    assert response.status_code == 200
    assert ted.threads and all(name != threading.main_thread().name for name in ted.threads)
