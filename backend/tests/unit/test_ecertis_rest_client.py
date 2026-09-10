"""S1.1.1 — the build-time REST client, driven entirely by `httpx.MockTransport`.

No network, no new dependency: `MockTransport` is part of httpx, so these tests exercise
the real request building, query encoding and `raise_for_status` path while every response
is scripted here.

The policy under test is the awkward one. eCertis answers `200` with a zero-byte body in
two different situations that are indistinguishable at the wire level:

* **stable emptiness** — the country registered no national sub-criterion for that EU
  criterion. Measured 2026-09-10: 17 of 56 for FR, 1 of 56 for DE, identical over six
  consecutive calls. This is an answer, not a failure.
* **transient emptiness** — a pair that normally answers returns nothing once.

So a criterion is retried hard and then reported as unanswered rather than raised, while
an empty *criterion list* is always fatal.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest

from crossbid.reference.ecertis_client import (
    MAX_ATTEMPTS,
    RESPONSE_LANGUAGE,
    TAXONOMY_NATIONAL_ENTITY,
    EcertisRestClient,
    EcertisUnavailableError,
)
from crossbid.reference.ecertis_schema import CachedCriterion

BASE_URL = "https://ecertis.invalid/rest/"
TAXES_ID = "b61bbeb7-690e-4a40-bc68-d6d4ecfaa3d4"

Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler, **kwargs: Any) -> EcertisRestClient:
    transport = httpx.MockTransport(handler)
    http = httpx.Client(base_url=BASE_URL, transport=transport)
    return EcertisRestClient(client=http, **kwargs)


def _criterion(criterion_id: str = TAXES_ID) -> CachedCriterion:
    return CachedCriterion(
        id=criterion_id, name="Payment of taxes", description="", type_name="", version="3"
    )


def _scripted(*responses: httpx.Response) -> tuple[Handler, list[httpx.Request]]:
    """A handler that plays `responses` in order, then repeats the last one forever."""
    seen: list[httpx.Request] = []
    queue: Iterator[httpx.Response] = iter(responses)
    last: list[httpx.Response] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        with contextlib.suppress(StopIteration):
            last.append(next(queue))
        return last[-1]

    return handler, seen


def _empty() -> httpx.Response:
    return httpx.Response(200, content=b"")


# ---------------------------------------------------------------------- empty-body policy


def test_persistent_empty_body_is_reported_as_unanswered(no_sleep: None) -> None:
    """A country with no national entry for a criterion is normal, not an error."""
    # Arrange
    handler, seen = _scripted(_empty())
    client = _client(handler)

    # Act
    row, answered = client.fetch_evidence(_criterion(), "fr")

    # Assert
    assert answered is False
    assert row.criterion_id == TAXES_ID
    assert row.criterion_name == "Payment of taxes"
    assert row.sub_criteria == ()
    assert len(seen) == MAX_ATTEMPTS, "an empty body must be retried, not accepted at once"


def test_empty_then_full_body_succeeds(no_sleep: None, ecertis_fixture: Any) -> None:
    """Transient emptiness must not cost us the criterion's evidence."""
    # Arrange
    detail = ecertis_fixture("criterion_detail_de_taxes")
    handler, seen = _scripted(_empty(), httpx.Response(200, json=detail))
    client = _client(handler)

    # Act
    row, answered = client.fetch_evidence(_criterion(), "de")

    # Assert
    assert answered is True
    assert len(row.sub_criteria) == 3
    assert len(seen) == 2


def test_retry_count_is_configurable(no_sleep: None) -> None:
    # Arrange
    handler, seen = _scripted(_empty())
    client = _client(handler, max_attempts=2)

    # Act
    _row, answered = client.fetch_evidence(_criterion(), "fr")

    # Assert
    assert answered is False
    assert len(seen) == 2


def test_a_body_of_only_whitespace_counts_as_empty(no_sleep: None) -> None:
    # Arrange
    handler, _seen = _scripted(httpx.Response(200, content=b"   \n  "))
    client = _client(handler)

    # Act / Assert
    assert client.fetch_evidence(_criterion(), "fr")[1] is False


# ------------------------------------------------------------------------ failure handling


def test_transport_error_raises_after_the_last_attempt(no_sleep: None) -> None:
    # Arrange
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        raise httpx.ConnectError("no route to host", request=request)

    client = _client(handler)

    # Act / Assert
    with pytest.raises(EcertisUnavailableError, match="failed after"):
        client.fetch_evidence(_criterion(), "de")
    assert len(attempts) == MAX_ATTEMPTS


def test_http_error_status_raises(no_sleep: None) -> None:
    # Arrange
    handler, seen = _scripted(httpx.Response(503, text="service unavailable"))
    client = _client(handler)

    # Act / Assert
    with pytest.raises(EcertisUnavailableError, match="failed after"):
        client.fetch_evidence(_criterion(), "de")
    assert len(seen) == MAX_ATTEMPTS


def test_a_transport_error_that_clears_is_retried_successfully(no_sleep: None) -> None:
    # Arrange
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ReadTimeout("slow", request=request)
        return httpx.Response(200, json={"Id": {"value": TAXES_ID}, "SubCriterion": []})

    client = _client(handler)

    # Act
    _row, answered = client.fetch_evidence(_criterion(), "de")

    # Assert
    assert answered is True
    assert len(calls) == 2


def test_malformed_json_raises(no_sleep: None) -> None:
    # Arrange
    handler, _seen = _scripted(httpx.Response(200, content=b"{not json at all"))
    client = _client(handler)

    # Act / Assert
    with pytest.raises(EcertisUnavailableError, match="malformed JSON"):
        client.fetch_evidence(_criterion(), "de")


def test_a_json_array_instead_of_an_object_raises(no_sleep: None) -> None:
    # Arrange
    handler, _seen = _scripted(httpx.Response(200, json=[1, 2, 3]))
    client = _client(handler)

    # Act / Assert
    with pytest.raises(EcertisUnavailableError, match="returned list, not an object"):
        client.fetch_evidence(_criterion(), "de")


def test_a_structurally_wrong_detail_raises(no_sleep: None) -> None:
    """`extra="ignore"` tolerates new fields; it must not tolerate a changed type."""
    # Arrange
    handler, _seen = _scripted(httpx.Response(200, json={"SubCriterion": "not a list"}))
    client = _client(handler)

    # Act / Assert
    with pytest.raises(EcertisUnavailableError, match="unexpected shape"):
        client.fetch_evidence(_criterion(), "de")


def test_an_unknown_extra_field_is_tolerated(no_sleep: None) -> None:
    # Arrange
    payload = {"Id": {"value": TAXES_ID}, "SubCriterion": [], "FieldFromTheFuture": {"a": 1}}
    handler, _seen = _scripted(httpx.Response(200, json=payload))
    client = _client(handler)

    # Act / Assert
    assert client.fetch_evidence(_criterion(), "de")[1] is True


# ----------------------------------------------------------------------- the criteria list


def _listing_handler(
    ecertis_fixture: Any, *, taxonomy: bool = True
) -> tuple[Handler, list[httpx.Request]]:
    listing = ecertis_fixture("criteria_list")
    labels = ecertis_fixture("criteria_list_taxonomy") if taxonomy else {"criterion": []}
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        wanted = listing if "nationalEntity" not in request.url.params else labels
        return httpx.Response(200, json=wanted)

    return handler, seen


def test_fetch_criteria_returns_rows_sorted_by_id(ecertis_fixture: Any) -> None:
    # Arrange
    handler, seen = _listing_handler(ecertis_fixture)
    client = _client(handler)

    # Act
    criteria = client.fetch_criteria()

    # Assert
    assert [c.id for c in criteria] == sorted(c.id for c in criteria)
    assert {c.name for c in criteria} == {
        "Payment of taxes",
        "Corruption",
        "General yearly turnover",
    }
    assert len(seen) == 2, "one call for the list, one for the taxonomy"


def test_fetch_criteria_pins_the_response_language(ecertis_fixture: Any) -> None:
    """Never trust a server default: `lang` is sent explicitly on every request."""
    # Arrange
    handler, seen = _listing_handler(ecertis_fixture)
    client = _client(handler)

    # Act
    client.fetch_criteria()

    # Assert
    assert all(request.url.params["lang"] == RESPONSE_LANGUAGE for request in seen)


def test_fetch_criteria_reads_the_taxonomy_from_the_eu_entity(ecertis_fixture: Any) -> None:
    """`GET criteria` omits `CriteriaTypeName`; only a nationalEntity listing carries it."""
    # Arrange
    handler, seen = _listing_handler(ecertis_fixture)
    client = _client(handler)

    # Act
    criteria = client.fetch_criteria()
    by_name = {c.name: c.type_name for c in criteria}

    # Assert
    assert seen[1].url.params["nationalEntity"] == TAXONOMY_NATIONAL_ENTITY
    assert by_name["Payment of taxes"].startswith("Exclusion Ground /")
    assert by_name["Corruption"] == "Exclusion Ground / Criminal convictions"
    # Absent from the taxonomy fixture on purpose — a missing label is blank, not a crash.
    assert by_name["General yearly turnover"] == ""


def test_fetch_criteria_keeps_only_eu_level_ids(ecertis_fixture: Any) -> None:
    """The taxonomy listing's ids are country-scoped and must never leak into the output."""
    # Arrange
    handler, _seen = _listing_handler(ecertis_fixture)
    client = _client(handler)
    taxonomy_ids = {
        row["Id"]["value"] for row in ecertis_fixture("criteria_list_taxonomy")["criterion"]
    }

    # Act
    criteria = client.fetch_criteria()

    # Assert
    assert {c.id for c in criteria}.isdisjoint(taxonomy_ids)
    assert TAXES_ID in {c.id for c in criteria}


def test_fetch_criteria_raises_on_an_empty_list(no_sleep: None) -> None:
    """Unlike one criterion in one country, an empty criterion list is never legitimate."""
    # Arrange
    handler, _seen = _scripted(httpx.Response(200, json={"criterion": []}))
    client = _client(handler)

    # Act / Assert
    with pytest.raises(EcertisUnavailableError, match="no usable criterion rows"):
        client.fetch_criteria()


def test_fetch_criteria_raises_on_an_empty_body(no_sleep: None) -> None:
    # Arrange
    handler, _seen = _scripted(_empty())
    client = _client(handler)

    # Act / Assert
    with pytest.raises(EcertisUnavailableError, match="empty body after retries"):
        client.fetch_criteria()


def test_fetch_criteria_drops_rows_with_no_id_or_no_name(no_sleep: None) -> None:
    # Arrange
    payload = {
        "criterion": [
            {"Id": {"value": TAXES_ID}, "Name": {"value": "Payment of taxes"}},
            {"Id": {}, "Name": {"value": "No id"}},
            {"Id": {"value": "has-id"}, "Name": {}},
        ]
    }
    handler, _seen = _scripted(httpx.Response(200, json=payload))
    client = _client(handler)

    # Act
    criteria = client.fetch_criteria()

    # Assert
    assert [c.id for c in criteria] == [TAXES_ID]


def test_fetch_criteria_raises_on_a_structurally_wrong_list(no_sleep: None) -> None:
    # Arrange
    handler, _seen = _scripted(httpx.Response(200, json={"criterion": {"not": "a list"}}))
    client = _client(handler)

    # Act / Assert
    with pytest.raises(EcertisUnavailableError, match="unexpected shape"):
        client.fetch_criteria()


# ------------------------------------------------------------------------ request plumbing


def test_country_filter_is_sent_on_the_detail_request(ecertis_fixture: Any) -> None:
    # Arrange
    detail = ecertis_fixture("criterion_detail_de_taxes")
    handler, seen = _scripted(httpx.Response(200, json=detail))
    client = _client(handler)

    # Act
    client.fetch_evidence(_criterion(), "de")

    # Assert
    assert seen[0].url.path.endswith(f"/criteria/{TAXES_ID}")
    assert seen[0].url.params["countryFilter"] == "de"
    assert seen[0].method == "GET"


def test_the_client_only_ever_issues_get_requests(ecertis_fixture: Any) -> None:
    """No scraping, no writes: eCertis is a read-only reference (CLAUDE.md)."""
    # Arrange
    handler, seen = _listing_handler(ecertis_fixture)
    client = _client(handler)

    # Act
    criteria = client.fetch_criteria()
    for criterion in criteria:
        client.fetch_evidence(criterion, "de")

    # Assert
    assert {request.method for request in seen} == {"GET"}


def test_an_injected_client_is_not_closed_by_the_context_manager(
    ecertis_fixture: Any,
) -> None:
    """The caller owns what the caller supplied; only a self-made client is closed."""
    # Arrange
    handler, _seen = _listing_handler(ecertis_fixture)
    http = httpx.Client(base_url=BASE_URL, transport=httpx.MockTransport(handler))

    # Act
    with EcertisRestClient(client=http) as client:
        assert client.fetch_criteria()

    # Assert
    assert http.is_closed is False
    http.close()


def test_a_self_made_client_is_closed_on_exit() -> None:
    # Act
    with EcertisRestClient(base_url=BASE_URL) as client:
        internal = client._client

    # Assert
    assert internal.is_closed is True


def test_sleep_is_the_only_wall_clock_wait() -> None:
    """Called with 0 so the suite stays instant while the real body still runs."""
    # Act / Assert — no exception, and nothing else in the module blocks
    assert EcertisRestClient._sleep(0) is None


def test_backoff_grows_with_the_attempt_number(monkeypatch: pytest.MonkeyPatch) -> None:
    """Three attempts means two waits, and the second is longer than the first."""
    # Arrange
    waits: list[float] = []
    monkeypatch.setattr(
        EcertisRestClient, "_sleep", staticmethod(lambda seconds: waits.append(seconds))
    )
    handler, _seen = _scripted(_empty())
    client = _client(handler)

    # Act
    client.fetch_evidence(_criterion(), "fr")

    # Assert
    assert len(waits) == MAX_ATTEMPTS - 1, "no wait after the final attempt"
    assert waits == sorted(waits)
    assert waits[0] < waits[-1]


# -------------------------------------------------------------------------------- live


@pytest.mark.live
def test_live_fetch_criteria_still_returns_the_full_espd_set() -> None:
    """Canary for the committed cache: run with `-m live` when eCertis changes shape."""
    # Arrange / Act
    with EcertisRestClient() as client:
        criteria = client.fetch_criteria()

    # Assert
    assert len(criteria) == 56
    assert all(criterion.type_name for criterion in criteria), "taxonomy stitching broke"
    assert TAXES_ID in {criterion.id for criterion in criteria}
