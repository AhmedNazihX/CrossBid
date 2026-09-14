"""S1.2.2 — `search_ted`, the one tool that opens a socket to a service we do not control.

Offline: the client underneath is exercised in `test_ted_client.py` against
`httpx.MockTransport`, so what is pinned here is the *tool* — its manifest, its argument
schema, and the shape of what the model gets back.

The important property is totality. `check_reqs` calls tools inside a per-requirement ReAct
loop that has already cost money by the time it runs, and S3.3.1's rule is that a tool may
not end a run by raising. TED being unreachable is the likeliest way that could happen here,
so it comes back as a status the model can read rather than as an exception.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from crossbid.models.ted import TedNotice, TedSearchPage
from crossbid.reference.ted_client import TedUnavailableError
from crossbid.tools.search_ted import MANIFEST, SearchTedArgs, build_tool

NOTICE = TedNotice(
    publication_number="629621-2026",
    title="Frankreich - Systemberatung",
    buyer="SPL EAU DU BASSIN RENNAIS",
    description="La Direction des Systemes d'information...",
    deadline=None,
    deadline_utc_offset_minutes=None,
    official_languages=("FRA",),
    submission_languages=("FRA",),
    cpv=("72246000",),
    notice_pdf_url="https://ted.europa.eu/fr/notice/629621-2026/pdf",
    documents_url="https://marches.megalis.bretagne.bzh/entreprise",
)


def run_tool(**kwargs: Any) -> dict[str, Any]:
    """The bound tool, invoked as the model would, with the client patched out."""
    tool = build_tool(context=None)  # type: ignore[arg-type]  - unused, see the module
    result: dict[str, Any] = tool.invoke(kwargs)
    return result


def answering(page: TedSearchPage) -> Any:
    class Fake:
        def search(self, *_: Any, **__: Any) -> TedSearchPage:
            return page

    return lambda *_, **__: Fake()


def raising(error: Exception) -> Any:
    class Fake:
        def search(self, *_: Any, **__: Any) -> TedSearchPage:
            raise error

    return lambda *_, **__: Fake()


PAGE = TedSearchPage(notices=(NOTICE,), total=19_238, page=1, limit=10, reachable_total=600)


# ------------------------------------------------------------------------------ manifest


def test_the_manifest_says_the_tool_leaves_the_process() -> None:
    """The one flag an operator needs: this is the only tool that can stall on a third party."""
    assert MANIFEST.name == "search_ted"
    assert MANIFEST.external is True


def test_the_description_tells_the_model_what_it_cannot_do() -> None:
    """The likeliest wrong belief is that this fetches the pack. It does not — the buyer's
    platform holds those and the bidder uploads them (the no-scraping rule)."""
    assert "eight digits" in MANIFEST.description
    assert "does NOT download" in MANIFEST.description


# ------------------------------------------------------------------------ argument schema


def test_a_cpv_that_is_not_eight_digits_is_refused_by_the_schema() -> None:
    """Bound into the tool schema, so an invented code is rejected before any request."""
    with pytest.raises(ValidationError):
        SearchTedArgs(cpv=("72",))


def test_a_country_that_is_not_two_letters_is_refused() -> None:
    with pytest.raises(ValidationError):
        SearchTedArgs(countries=("FRA",))


def test_a_limit_beyond_the_page_size_is_refused() -> None:
    with pytest.raises(ValidationError):
        SearchTedArgs(limit=500)


def test_everything_is_optional_so_the_model_may_search_broadly() -> None:
    assert SearchTedArgs().limit > 0


# ----------------------------------------------------------------------------- behaviour


def test_a_search_returns_the_notices_trimmed_to_what_a_model_can_use() -> None:
    with patch("crossbid.tools.search_ted.TedSearchClient", answering(PAGE)):
        result = run_tool(cpv=("72000000",), countries=("fr",))

    assert result["status"] == "ok"
    assert result["total"] == 19_238
    assert result["notices"][0] == {
        "publication_number": "629621-2026",
        "title": "Frankreich - Systemberatung",
        "buyer": "SPL EAU DU BASSIN RENNAIS",
        "deadline": None,
        "official_languages": ["FRA"],
        "submission_languages": ["FRA"],
        "notice_url": "https://ted.europa.eu/fr/notice/629621-2026/pdf",
        "documents_url": "https://marches.megalis.bretagne.bzh/entreprise",
    }


def test_the_answer_carries_no_link_sets_or_cpv_lists() -> None:
    """Twenty-four PDF URLs per notice would spend tokens to say nothing."""
    with patch("crossbid.tools.search_ted.TedSearchClient", answering(PAGE)):
        notice = run_tool()["notices"][0]

    assert "links" not in notice
    assert "cpv" not in notice


def test_a_deadline_is_sent_as_a_plain_date() -> None:
    from datetime import date

    dated = TedSearchPage(
        notices=(NOTICE.model_copy(update={"deadline": date(2026, 10, 7)}),),
        total=1,
        page=1,
        limit=10,
        reachable_total=1,
    )
    with patch("crossbid.tools.search_ted.TedSearchClient", answering(dated)):
        assert run_tool()["notices"][0]["deadline"] == "2026-10-07"


def test_an_unreachable_ted_is_a_status_and_never_an_exception() -> None:
    """S3.3.1's rule: a tool may not end a run that has already cost money."""
    with patch(
        "crossbid.tools.search_ted.TedSearchClient", raising(TedUnavailableError("no route"))
    ):
        result = run_tool(cpv=("72000000",))

    assert result["status"] == "unavailable"
    assert result["notices"] == []
    assert "no route" in result["detail"]


def test_a_country_is_lower_cased_before_it_reaches_the_client() -> None:
    """`place-of-performance` wants alpha-3 and the client maps from lower-case alpha-2."""
    seen: list[Any] = []

    class Recording:
        def search(self, query: Any, **_: Any) -> TedSearchPage:
            seen.append(query)
            return PAGE

    with patch("crossbid.tools.search_ted.TedSearchClient", lambda *_, **__: Recording()):
        run_tool(countries=("FR", "De"))

    assert seen[0].countries == ("fr", "de")
