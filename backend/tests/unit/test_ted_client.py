# ruff: noqa: RUF001 - the en dashes below are TED's own, copied from a live answer
"""S1.2.1 — the TED search client, driven entirely by `httpx.MockTransport`.

No network and no new dependency: `MockTransport` ships with httpx, so these exercise the
real `TedSearchClient` against responses shaped like the live ones. The payloads below are
copied from an actual answer (probed 2026-09-14, publication 629621-2026), including the
parts that look like mistakes and are not — `classification-cpv` repeating a code once per
lot, `buyer-name` mapping a language to a *list*, and a deadline carrying an offset and no
hour.

The query tests are the story's second criterion stated directly: **no `OR` inside
`IN (...)`, ever.** TED rejects it outright, so a query that contained one would fail as a
400 a bidder had no way to see coming.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx
import pytest

from crossbid.models.ted import TedSearchQuery
from crossbid.reference.ted_client import (
    SORT_CLAUSE,
    TedSearchClient,
    TedUnavailableError,
    build_query,
)

NOTICE: dict[str, Any] = {
    "publication-number": "629621-2026",
    "notice-title": {
        "fra": "France – Services de conseil en systèmes – DSI-2026-20-RSSI",
        "deu": "Frankreich – Systemberatung – DSI-2026-20-RSSI",
        "eng": "France – Systems consultancy services – DSI-2026-20-RSSI",
    },
    "title-proc": {"fra": "DSI-2026-20-RSSI"},
    "description-proc": {"fra": "La Direction des Systèmes d'information souhaite…"},
    "buyer-name": {"fra": ["SPL EAU DU BASSIN RENNAIS"]},
    "deadline-receipt-tender-date-lot": ["2026-11-20+01:00", "2026-10-07+02:00"],
    "official-language": ["FRA"],
    "submission-language": ["FRA"],
    "classification-cpv": ["72246000", "72246000"],
    "document-url-lot": ["https://marches.megalis.bretagne.bzh/entreprise"],
    "links": {
        "pdf": {
            "FRA": "https://ted.europa.eu/fr/notice/629621-2026/pdf",
            "ENG": "https://ted.europa.eu/en/notice/629621-2026/pdf",
        },
        "xml": {"MUL": "https://ted.europa.eu/en/notice/629621-2026/xml"},
    },
    "publication-date": "2026-09-14+02:00",
}

BODY: dict[str, Any] = {"notices": [NOTICE], "totalNoticeCount": 164_660}


def client_for(handler: Any, *, max_attempts: int = 2) -> TedSearchClient:
    return TedSearchClient(
        httpx.Client(transport=httpx.MockTransport(handler)), max_attempts=max_attempts
    )


def answering(body: Any, status: int = 200) -> Any:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body)

    return handler


# ------------------------------------------------------------------------ query building


def test_a_cpv_and_a_country_become_two_in_clauses() -> None:
    query = build_query(TedSearchQuery(cpv=("72000000",), countries=("fr",)))

    assert "classification-cpv IN (72000000)" in query
    assert "place-of-performance IN (FRA)" in query


def test_several_values_are_separated_by_spaces_and_never_by_or() -> None:
    """The story's criterion. TED rejects `OR` inside the parentheses outright."""
    query = build_query(TedSearchQuery(cpv=("72000000", "79000000"), countries=("fr", "de")))

    assert "classification-cpv IN (72000000 79000000)" in query
    assert "place-of-performance IN (FRA DEU)" in query
    assert " OR " not in query


def test_the_country_is_translated_to_the_three_letter_code_ted_speaks() -> None:
    """Everything else in the app says `de`; `place-of-performance` says `DEU`."""
    assert "place-of-performance IN (DEU)" in build_query(TedSearchQuery(countries=("de",)))


def test_an_unknown_country_is_dropped_rather_than_sent() -> None:
    """A code outside the EU-27 has no alpha-3 here, and a half-built clause is a 400."""
    query = build_query(TedSearchQuery(countries=("zz",)))

    assert "place-of-performance" not in query


def test_contract_notices_are_the_default_filter() -> None:
    """84 % of `cn-standard` notices carry a deadline; award notices carry none by nature."""
    assert "notice-type IN (cn-standard)" in build_query(TedSearchQuery())


def test_the_notice_type_filter_can_be_lifted() -> None:
    assert "notice-type" not in build_query(TedSearchQuery(contract_notices_only=False))


def test_a_keyword_becomes_a_quoted_full_text_clause() -> None:
    query = build_query(TedSearchQuery(keyword="cyber security"))

    assert 'FT ~ ("cyber security")' in query


def test_a_quote_in_a_keyword_cannot_break_out_of_the_clause() -> None:
    """There is no documented escape, so the quote goes rather than the query breaking.

    The surviving `OR` is deliberate and harmless: it stays *inside* the quoted phrase, where
    TED reads it as text to search for. What must never happen is the phrase ending early and
    the rest becoming query syntax — which is what the quote count pins.
    """
    query = build_query(TedSearchQuery(keyword='cyber" OR notice-type IN (can-standard'))

    assert query.count('"') == 2
    assert query.index('FT ~ ("') < query.index(" OR ") < query.rindex('"')


def test_a_blank_keyword_adds_no_clause() -> None:
    assert "FT ~" not in build_query(TedSearchQuery(keyword="   "))


def test_every_query_sorts_newest_first_inside_the_query_string() -> None:
    """A JSON `sort` field is rejected outright, and `ASC` is a 400 — this is the only order."""
    assert build_query(TedSearchQuery()).endswith(SORT_CLAUSE)


def test_the_sort_is_appended_and_never_joined_with_and() -> None:
    """`... AND SORT BY publication-date DESC` is `QUERY_SYNTAX_ERROR: mismatched input
    'SORT'`. It is a suffix, not a clause — and it took the live test to find that, because
    every assertion above is just as happy with the broken form."""
    query = build_query(TedSearchQuery(cpv=("72000000",)))

    assert f" AND {SORT_CLAUSE}" not in query
    assert query.endswith(f") {SORT_CLAUSE}")


def test_an_empty_search_is_still_a_valid_query() -> None:
    assert build_query(TedSearchQuery(contract_notices_only=False)) == SORT_CLAUSE


# -------------------------------------------------------------------------- the response


def test_a_notice_is_mapped_onto_the_fields_a_screen_shows() -> None:
    page = client_for(answering(BODY)).search(TedSearchQuery(), language="fr")
    notice = page.notices[0]

    assert notice.publication_number == "629621-2026"
    assert notice.buyer == "SPL EAU DU BASSIN RENNAIS"
    assert notice.official_languages == ("FRA",)
    assert notice.submission_languages == ("FRA",)
    assert notice.documents_url == "https://marches.megalis.bretagne.bzh/entreprise"
    assert notice.published_on == date(2026, 9, 14)


def test_the_title_is_read_in_the_bidders_own_language() -> None:
    """The cross-border wedge for free: TED translates the title into all 24 languages."""
    page = client_for(answering(BODY)).search(TedSearchQuery(), language="de")

    assert page.notices[0].title.startswith("Frankreich")


def test_the_title_falls_back_to_the_notices_own_language() -> None:
    page = client_for(answering(BODY)).search(TedSearchQuery(), language="pl")

    assert page.notices[0].title.startswith("France –")


def test_an_unkeyed_string_field_is_passed_through() -> None:
    body = {**BODY, "notices": [{**NOTICE, "notice-title": "A plain title"}]}

    assert (
        client_for(answering(body)).search(TedSearchQuery()).notices[0].title == "A plain title"
    )


def test_a_notice_with_no_title_at_all_still_loads() -> None:
    """A row that cannot be titled must not take the whole page down with it."""
    body = {**BODY, "notices": [{**NOTICE, "notice-title": None, "title-proc": None}]}

    assert client_for(answering(body)).search(TedSearchQuery()).notices[0].title


def test_the_earliest_lot_deadline_is_the_one_reported() -> None:
    """One entry per lot; the bidder is held to the first of them."""
    page = client_for(answering(BODY)).search(TedSearchQuery())

    assert page.notices[0].deadline == date(2026, 10, 7)
    assert page.notices[0].deadline_utc_offset_minutes == 120


def test_a_deadline_carries_no_time_of_day_because_ted_publishes_none() -> None:
    """Zero of 58 sampled lot deadlines had an hour; inventing midnight would be a lie on a
    dashboard countdown (S4.4.1 takes the hour from the bidder)."""
    deadline = client_for(answering(BODY)).search(TedSearchQuery()).notices[0].deadline

    assert isinstance(deadline, date)


def test_a_zulu_offset_is_zero_and_not_missing() -> None:
    body = {
        **BODY,
        "notices": [{**NOTICE, "deadline-receipt-tender-date-lot": ["2026-10-07Z"]}],
    }

    assert (
        client_for(answering(body))
        .search(TedSearchQuery())
        .notices[0]
        .deadline_utc_offset_minutes
        == 0
    )


def test_a_notice_with_no_deadline_reports_none_rather_than_guessing() -> None:
    body = {**BODY, "notices": [{**NOTICE, "deadline-receipt-tender-date-lot": []}]}
    notice = client_for(answering(body)).search(TedSearchQuery()).notices[0]

    assert notice.deadline is None
    assert notice.deadline_utc_offset_minutes is None


def test_an_unreadable_deadline_is_skipped_not_fatal() -> None:
    body = {**BODY, "notices": [{**NOTICE, "deadline-receipt-tender-date-lot": ["soon"]}]}

    assert client_for(answering(body)).search(TedSearchQuery()).notices[0].deadline is None


def test_a_cpv_repeated_once_per_lot_is_reported_once() -> None:
    assert client_for(answering(BODY)).search(TedSearchQuery()).notices[0].cpv == ("72246000",)


def test_the_notice_pdf_is_offered_in_the_language_the_buyer_wrote() -> None:
    """A translation is not offered where the original exists (S1.2.2 opens this)."""
    url = client_for(answering(BODY)).search(TedSearchQuery()).notices[0].notice_pdf_url

    assert url == "https://ted.europa.eu/fr/notice/629621-2026/pdf"


def test_a_notice_with_no_pdf_links_reports_none() -> None:
    body = {**BODY, "notices": [{**NOTICE, "links": {"xml": {"MUL": "…"}}}]}

    assert (
        client_for(answering(body)).search(TedSearchQuery()).notices[0].notice_pdf_url is None
    )


def test_paging_is_capped_at_what_ted_will_actually_serve() -> None:
    """`limit=100, page=7` is a 400 even at 164 660 matches, so the page says so."""
    page = client_for(answering(BODY)).search(TedSearchQuery())

    assert page.total == 164_660
    assert page.reachable_total == 600


def test_a_small_result_set_is_reachable_in_full() -> None:
    page = client_for(answering({**BODY, "totalNoticeCount": 12})).search(TedSearchQuery())

    assert page.reachable_total == 12


def test_a_body_with_no_notices_is_an_empty_page_and_not_an_error() -> None:
    page = client_for(answering({"totalNoticeCount": 0})).search(TedSearchQuery())

    assert page.notices == ()
    assert page.total == 0


def test_the_limit_and_page_asked_for_reach_ted() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen.append(json.loads(request.content))
        return httpx.Response(200, json=BODY)

    client_for(handler).search(TedSearchQuery(limit=50, page=3))

    assert seen[0]["limit"] == 50
    assert seen[0]["page"] == 3


# ---------------------------------------------------------------------------- failures


def test_a_transport_failure_is_retried_once_then_typed(no_ted_sleep: None) -> None:
    """The story's third criterion. 'TED is down' and 'nothing matched' are different
    answers, so this may never come back as an empty page."""
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("no route to host")

    with pytest.raises(TedUnavailableError, match="2 attempts"):
        client_for(handler).search(TedSearchQuery())
    assert attempts == 2


def test_a_failure_that_clears_on_the_retry_succeeds() -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ReadTimeout("slow")
        return httpx.Response(200, json=BODY)

    page = client_for(handler).search(TedSearchQuery())

    assert page.notices[0].publication_number == "629621-2026"
    assert attempts == 2


def test_a_400_is_retried_and_then_typed() -> None:
    with pytest.raises(TedUnavailableError):
        client_for(answering({"message": "bad query"}, status=400)).search(TedSearchQuery())


def test_a_body_that_is_not_json_is_typed_immediately() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>gateway</html>")

    with pytest.raises(TedUnavailableError, match="not JSON"):
        client_for(handler).search(TedSearchQuery())


def test_a_body_that_is_not_an_object_is_typed() -> None:
    with pytest.raises(TedUnavailableError, match="not an object"):
        client_for(answering([1, 2, 3])).search(TedSearchQuery())


@pytest.fixture
def no_ted_sleep() -> None:
    """The client does not sleep between attempts; this fixture documents that it need not."""
    return None


# ------------------------------------------------------- the shapes TED sends more rarely


def test_a_field_whose_languages_are_all_blank_reports_nothing() -> None:
    """A mapping with keys and no usable text is not a buyer name."""
    body = {**BODY, "notices": [{**NOTICE, "buyer-name": {"fra": [""], "eng": ["  "]}}]}

    assert client_for(answering(body)).search(TedSearchQuery()).notices[0].buyer is None


def test_a_deadline_with_no_offset_at_all_keeps_the_date() -> None:
    """The offset is what the buyer's wall clock needs; its absence is not the date's."""
    body = {**BODY, "notices": [{**NOTICE, "deadline-receipt-tender-date-lot": ["2026-10-07"]}]}
    notice = client_for(answering(body)).search(TedSearchQuery()).notices[0]

    assert notice.deadline == date(2026, 10, 7)
    assert notice.deadline_utc_offset_minutes is None


def test_a_deadline_that_does_carry_a_time_is_read_rather_than_refused() -> None:
    """TED has never sent one. If it starts, the date and offset still arrive and the hour
    is dropped — the model is a date, and S4.4.1 takes the hour from the bidder."""
    body = {
        **BODY,
        "notices": [{**NOTICE, "deadline-receipt-tender-date-lot": ["2026-10-07T14:30+02:00"]}],
    }
    notice = client_for(answering(body)).search(TedSearchQuery()).notices[0]

    assert notice.deadline == date(2026, 10, 7)
    assert notice.deadline_utc_offset_minutes == 120


def test_a_negative_offset_keeps_its_sign() -> None:
    """`fromisoformat` would have read `-03:00` as part of the date; the regex does not."""
    body = {
        **BODY,
        "notices": [{**NOTICE, "deadline-receipt-tender-date-lot": ["2026-10-07-03:00"]}],
    }

    assert (
        client_for(answering(body))
        .search(TedSearchQuery())
        .notices[0]
        .deadline_utc_offset_minutes
        == -180
    )


def test_a_pdf_in_no_language_we_asked_for_is_still_offered() -> None:
    """Better the notice in a language nobody picked than no link to the notice at all."""
    body = {**BODY, "notices": [{**NOTICE, "links": {"pdf": {"POL": "https://ted/pl.pdf"}}}]}

    assert client_for(answering(body)).search(TedSearchQuery()).notices[0].notice_pdf_url == (
        "https://ted/pl.pdf"
    )


def test_junk_among_the_cpv_codes_is_dropped() -> None:
    body = {**BODY, "notices": [{**NOTICE, "classification-cpv": ["72246000", None, "", 7]}]}

    assert client_for(answering(body)).search(TedSearchQuery()).notices[0].cpv == ("72246000",)


def test_a_documents_url_sent_as_a_bare_string_is_accepted() -> None:
    """`document-url-lot` is a list on every notice seen; a string is read all the same."""
    body = {**BODY, "notices": [{**NOTICE, "document-url-lot": "https://platform.example"}]}

    assert client_for(answering(body)).search(TedSearchQuery()).notices[0].documents_url == (
        "https://platform.example"
    )


def test_a_documents_url_list_of_junk_reports_nothing() -> None:
    body = {**BODY, "notices": [{**NOTICE, "document-url-lot": [None, "", 3]}]}

    assert client_for(answering(body)).search(TedSearchQuery()).notices[0].documents_url is None


def test_a_notice_that_is_not_an_object_is_skipped_rather_than_fatal() -> None:
    body = {**BODY, "notices": ["not a notice", NOTICE]}

    assert len(client_for(answering(body)).search(TedSearchQuery()).notices) == 1


def test_a_notices_field_that_is_not_a_list_is_an_empty_page() -> None:
    assert client_for(answering({"notices": {}})).search(TedSearchQuery()).notices == ()


def test_a_notice_with_no_publication_date_and_a_blank_deadline_still_loads() -> None:
    """Both arrive as nothing rather than as a string, which is its own path."""
    body = {
        **BODY,
        "notices": [
            {
                **NOTICE,
                "publication-date": None,
                "deadline-receipt-tender-date-lot": [None, "  "],
            }
        ],
    }
    notice = client_for(answering(body)).search(TedSearchQuery()).notices[0]

    assert notice.published_on is None
    assert notice.deadline is None


# ------------------------------------------------- one notice, by its publication number


def test_the_stated_selection_criteria_come_back_in_the_notices_own_language() -> None:
    """They become requirement *quotes*, and a machine translation of a legal criterion is
    not the criterion — so the bidder's language is deliberately not consulted here."""
    body = {
        **BODY,
        "notices": [
            {
                **NOTICE,
                "official-language": ["DEU"],
                "selection-criterion-description-lot": {
                    "deu": ["Eigenerklaerung zur Eignung.", "Mindestumsatz 3 000 000 EUR."],
                    "eng": ["Declaration of suitability.", "Minimum turnover EUR 3 000 000."],
                },
            }
        ],
    }
    notice = client_for(answering(body)).search(TedSearchQuery(), language="en").notices[0]

    assert notice.selection_criteria == (
        "Eigenerklaerung zur Eignung.",
        "Mindestumsatz 3 000 000 EUR.",
    )


def test_a_notice_stating_no_criteria_reports_none() -> None:
    """The common case: 14-17 % of CPV-72 notices state any, which is the measurement the
    upload-the-pack design rests on."""
    assert (
        client_for(answering(BODY)).search(TedSearchQuery()).notices[0].selection_criteria == ()
    )


def test_criteria_in_a_language_we_did_not_ask_for_are_still_returned() -> None:
    """Better the buyer's words in a language nobody picked than no criteria at all."""
    body = {
        **BODY,
        "notices": [
            {**NOTICE, "selection-criterion-description-lot": {"pol": ["Warunek udzialu."]}}
        ],
    }

    assert client_for(answering(body)).search(TedSearchQuery()).notices[
        0
    ].selection_criteria == ("Warunek udzialu.",)


def test_a_criteria_field_that_is_not_a_mapping_is_ignored() -> None:
    body = {**BODY, "notices": [{**NOTICE, "selection-criterion-description-lot": ["loose"]}]}

    assert (
        client_for(answering(body)).search(TedSearchQuery()).notices[0].selection_criteria == ()
    )


def test_a_lookup_by_publication_number_asks_ted_for_exactly_that_notice() -> None:
    """The v3 API has no by-id endpoint, so it is a search with one clause."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen.append(json.loads(request.content)["query"])
        return httpx.Response(200, json=BODY)

    found = client_for(handler).search_by_publication_number("629621-2026")

    assert found is not None
    assert found.publication_number == "629621-2026"
    assert seen[0] == "publication-number IN (629621-2026)"


def test_a_lookup_does_not_filter_by_notice_type() -> None:
    """The caller already has a specific notice; filtering it out for being an award notice
    would be a confusing nothing."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen.append(json.loads(request.content)["query"])
        return httpx.Response(200, json=BODY)

    client_for(handler).search_by_publication_number("629621-2026")

    assert "notice-type" not in seen[0]


def test_a_publication_number_ted_does_not_know_answers_none() -> None:
    body = {"notices": [], "totalNoticeCount": 0}

    assert client_for(answering(body)).search_by_publication_number("000000-2026") is None


def test_a_language_whose_criteria_are_all_blank_falls_through_to_the_next() -> None:
    """An empty list under the notice's own language is not an answer; the next one is."""
    body = {
        **BODY,
        "notices": [
            {
                **NOTICE,
                "official-language": ["DEU"],
                "selection-criterion-description-lot": {
                    "deu": ["", "  "],
                    "eng": ["A criterion."],
                },
            }
        ],
    }

    assert client_for(answering(body)).search(TedSearchQuery()).notices[
        0
    ].selection_criteria == ("A criterion.",)


def test_a_criteria_mapping_with_nothing_usable_in_it_reports_none() -> None:
    body = {
        **BODY,
        "notices": [{**NOTICE, "selection-criterion-description-lot": {"deu": [], "eng": ""}}],
    }

    assert (
        client_for(answering(body)).search(TedSearchQuery()).notices[0].selection_criteria == ()
    )


@pytest.mark.parametrize(
    "number",
    [
        "629621-2026 OR publication-number IN (000001-2026)",
        "629621-2026) OR classification-cpv IN (72000000",
        "not-a-number",
        "",
        "629621",
    ],
    ids=["injected-or", "closed-predicate", "words", "empty", "no-year"],
)
def test_a_value_that_is_not_a_publication_number_never_reaches_ted(number: str) -> None:
    """The one call that builds its own clause is the one place a value skips `_values`.

    The module's promise is that there is nowhere for an `OR` to get in. `query_override`
    was that nowhere, and the value reaching it starts life in a request body: unchecked, a
    crafted number could close the predicate and open another, so the notice whose deadline
    `parse_docs` then writes onto the bid would not be the notice the bidder chose.
    """

    # Arrange -- a handler that fails the test if it is ever called.
    def refuse(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"a query was sent: {request.content!r}")

    # Act / Assert
    with pytest.raises(TedUnavailableError, match="publication number"):
        client_for(refuse).search_by_publication_number(number)
