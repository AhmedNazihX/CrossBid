"""S1.2.1 against the real TED API. Marked `live`: excluded from `make test`, run by
`make test-live`.

It costs nothing — TED is public, needs no key and charges nothing — but it is the only
thing that can fail when TED changes its syntax or its field names, which is a thing it has
done. The unit tests pin the mapping against a recorded answer; this pins that the recording
is still what TED sends.

Every assertion here is one of the facts `CLAUDE.md` records from the 2026-09-14 probe. If
one of them starts failing, that section is what needs correcting, not this file.
"""

from __future__ import annotations

import httpx
import pytest

from crossbid.models.ted import TedSearchQuery
from crossbid.reference.ted_client import REQUEST_TIMEOUT_S, TedSearchClient

pytestmark = pytest.mark.live


@pytest.fixture
def client() -> TedSearchClient:
    return TedSearchClient(httpx.Client(timeout=REQUEST_TIMEOUT_S))


def test_a_cpv_and_country_search_returns_usable_notices(client: TedSearchClient) -> None:
    """The story's first criterion, against the live service."""
    page = client.search(
        TedSearchQuery(cpv=("72000000",), countries=("fr",), limit=5), language="de"
    )

    assert page.notices, "CPV 72 in France has never been empty"
    assert page.total > 0
    for notice in page.notices:
        assert notice.publication_number
        assert notice.title
        assert notice.notice_pdf_url, "every notice is published as a PDF"


def test_titles_come_back_in_the_bidders_language_without_a_model_call(
    client: TedSearchClient,
) -> None:
    """TED translates every notice title into all 24 EU languages. The same French notice
    read in German and in French must differ, or the resolution is not doing anything."""
    query = TedSearchQuery(cpv=("72000000",), countries=("fr",), limit=3)
    german = client.search(query, language="de")
    french = client.search(query, language="fr")

    pairs = list(zip(german.notices, french.notices, strict=True))
    assert any(a.title != b.title for a, b in pairs)


def test_deadlines_are_dates_with_an_offset_and_never_an_hour(client: TedSearchClient) -> None:
    """Zero of 58 sampled lot deadlines carried a time of day. If this ever fails, the
    dashboard countdown can stop asking the bidder for the hour (S4.4.1)."""
    page = client.search(TedSearchQuery(cpv=("72000000",), limit=20))
    with_deadlines = [n for n in page.notices if n.deadline is not None]

    assert with_deadlines, "cn-standard notices carry a deadline 84 % of the time"
    for notice in with_deadlines:
        assert notice.deadline_utc_offset_minutes is not None


def test_paging_past_what_ted_serves_is_reported_rather_than_attempted(
    client: TedSearchClient,
) -> None:
    """`limit=100, page=7` is HTTP 400 however many matched, so the page caps itself."""
    page = client.search(TedSearchQuery(cpv=("72000000",), limit=100, page=1))

    assert page.total > page.reachable_total
    assert page.reachable_total == 600
