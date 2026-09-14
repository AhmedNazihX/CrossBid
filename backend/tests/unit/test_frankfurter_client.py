"""S1.3.1 — the ECB rate client, driven entirely by `httpx.MockTransport`.

No network and no new dependency: `MockTransport` ships with httpx. The body below is a
live answer copied verbatim (probed 2026-09-14), which is the whole of what this endpoint
sends — one flat object, no envelope.

Two properties carry the story. **The rate comes from the ECB and not from a blend**: the
provider is pinned in the URL path, so the request itself is asserted, not only the answer.
And **the second criterion — "given the rate service is down, the last cached rate is
returned with a staleness flag"** — is exercised through the same client the tool builds,
including the case the criterion does not mention and a process meets first: nothing cached
at all, which must be a refusal rather than a number.

The failures are separated on purpose. A 404 or a 422 says the ECB does not quote the pair;
everything else says the service is unreachable. Only the second may be answered from cache,
and the tests below pin both halves of that.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx
import pytest

from crossbid.reference.frankfurter_client import (
    RATE_CACHE,
    ExchangeRate,
    FrankfurterClient,
    RateCache,
    RateUnavailableError,
    UnknownCurrencyPairError,
)

BODY: dict[str, Any] = {
    "date": "2026-09-14",
    "base": "PLN",
    "quote": "EUR",
    "rate": 0.23032,
}


def answering(body: Any, status: int = 200) -> Any:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body)

    return handler


def client_for(handler: Any, *, cache: RateCache | None = None) -> FrankfurterClient:
    """A client over a mock transport, with a cache of its own unless one is passed."""
    return FrankfurterClient(
        httpx.Client(transport=httpx.MockTransport(handler)), cache=cache or RateCache()
    )


# --------------------------------------------------------------------------- the request


def test_the_rate_is_asked_of_the_ecb_and_not_of_the_blend() -> None:
    """`/v2/rate/PLN/EUR` blends ~100 central banks and answers 0.23069; the ECB alone
    answers 0.23032. The story says ECB, so the provider is in the path."""
    # Arrange
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json=BODY)

    # Act
    client_for(handler).rate("PLN", "EUR")

    # Assert
    assert seen == ["https://api.frankfurter.dev/v2/providers/ECB/rate/PLN/EUR"]


def test_a_code_is_upper_cased_before_it_reaches_the_url() -> None:
    """The API accepts either casing and echoes upper; one casing in the answer means no
    caller has to fold it before comparing."""
    # Arrange
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, json=BODY)

    # Act
    rate = client_for(handler).rate(" pln ", "eur")

    # Assert
    assert seen == ["/v2/providers/ECB/rate/PLN/EUR"]
    assert (rate.base, rate.quote) == ("PLN", "EUR")


@pytest.mark.parametrize("code", ["EU", "EURO", "", "../../providers/CBR/rate/EUR"])
def test_a_code_that_is_not_three_letters_never_reaches_the_network(code: str) -> None:
    """The guard is on the URL *path*, so a code carrying `../` cannot walk out of the
    endpoint it was meant for."""

    def handler(_: httpx.Request) -> httpx.Response:  # pragma: no cover - must not run
        raise AssertionError("a malformed currency code opened a socket")

    with pytest.raises(UnknownCurrencyPairError, match="three-letter"):
        client_for(handler).rate(code, "EUR")


# ---------------------------------------------------------------------------- the answer


def test_a_rate_is_read_off_the_flat_body() -> None:
    # Act
    rate = client_for(answering(BODY)).rate("PLN", "EUR")

    # Assert
    assert rate == ExchangeRate(
        base="PLN", quote="EUR", rate=0.23032, rate_date=date(2026, 9, 14), stale=False
    )


def test_the_publication_date_is_the_ecbs_and_not_the_day_of_the_call() -> None:
    """Asked on a Monday, the ECB answers with Friday's rate — so the date is reported
    rather than assumed, and `stale` is about the service, not about the weekend."""
    # Act
    rate = client_for(answering({**BODY, "date": "2026-09-11"})).rate("PLN", "EUR")

    # Assert
    assert rate.rate_date == date(2026, 9, 11)
    assert rate.stale is False


# ----------------------------------------------------------------- the pair does not exist


@pytest.mark.parametrize("status", [404, 422])
def test_a_pair_the_ecb_does_not_publish_is_typed_and_never_retried(status: int) -> None:
    """`XXX` is 422 `invalid currency`; `AFN` — a real currency the ECB does not quote — is
    404. Neither improves on a second ask."""
    # Arrange
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(status, json={"status": status, "message": "not found"})

    # Act & Assert
    with pytest.raises(UnknownCurrencyPairError, match="publishes no EUR/AFN"):
        client_for(handler).rate("EUR", "AFN")
    assert attempts == 1


def test_an_unknown_pair_is_not_answered_from_the_cache() -> None:
    """If the ECB stops quoting a currency, saying so beats serving last week's number for
    the rest of the process's life."""
    # Arrange
    cache = RateCache()
    client_for(answering(BODY), cache=cache).rate("PLN", "EUR")

    # Act & Assert
    with pytest.raises(UnknownCurrencyPairError):
        client_for(answering({"message": "gone"}, status=404), cache=cache).rate("PLN", "EUR")


# ------------------------------------------------------------------- the service is down


def test_a_transport_failure_is_retried_once_then_typed() -> None:
    """Nothing cached, so there is nothing honest to answer with."""
    # Arrange
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("no route to host")

    # Act & Assert
    with pytest.raises(RateUnavailableError, match="2 attempts"):
        client_for(handler).rate("PLN", "EUR")
    assert attempts == 2


def test_a_failure_that_clears_on_the_retry_succeeds() -> None:
    # Arrange
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ReadTimeout("slow")
        return httpx.Response(200, json=BODY)

    # Act
    rate = client_for(handler).rate("PLN", "EUR")

    # Assert
    assert rate.rate == 0.23032
    assert attempts == 2


def test_a_server_error_is_retried_and_then_typed() -> None:
    """A 503 is the shape the API documents for its own outages; it is not a bad pair."""
    with pytest.raises(RateUnavailableError):
        client_for(answering({"message": "unavailable"}, status=503)).rate("PLN", "EUR")


def test_the_last_good_rate_is_served_with_a_staleness_flag() -> None:
    """The story's second criterion, end to end through one cache."""
    # Arrange
    cache = RateCache()
    fresh = client_for(answering(BODY), cache=cache).rate("PLN", "EUR")

    # Act
    down = client_for(answering({}, status=502), cache=cache).rate("PLN", "EUR")

    # Assert
    assert down.stale is True
    assert down.rate == fresh.rate
    assert down.rate_date == fresh.rate_date


def test_serving_a_stale_rate_does_not_mutate_the_remembered_one() -> None:
    """The flag describes one answer, not the cache: the next call that succeeds must not
    find a record that has been quietly relabelled."""
    # Arrange
    cache = RateCache()
    client_for(answering(BODY), cache=cache).rate("PLN", "EUR")

    # Act
    client_for(answering({}, status=502), cache=cache).rate("PLN", "EUR")

    # Assert
    remembered = cache.last_good("PLN", "EUR")
    assert remembered is not None
    assert remembered.stale is False


def test_a_cold_process_has_nothing_to_fall_back_on_and_says_so() -> None:
    """The cost of an in-process cache, stated: a restarted API meeting a downed service
    refuses rather than inventing a rate."""
    with pytest.raises(RateUnavailableError):
        client_for(answering({}, status=502), cache=RateCache()).rate("PLN", "EUR")


def test_a_cached_pair_is_found_whatever_casing_it_is_asked_for() -> None:
    # Arrange
    cache = RateCache()
    client_for(answering(BODY), cache=cache).rate("PLN", "EUR")

    # Act & Assert
    assert cache.last_good("pln", "eur") is not None
    assert cache.last_good("PLN", "CZK") is None


def test_the_cache_is_the_processs_and_not_one_clients() -> None:
    """The default `cache` argument is the module singleton, and that is load-bearing: the
    tool builds a fresh client per call, so a per-instance cache would be cold every time
    and the story's second criterion could never be met.

    This is the one test that writes into `RATE_CACHE`, deliberately and on a pair no other
    test reads — the entry it leaves behind is the property being asserted.
    """
    # Arrange
    warm = FrankfurterClient(httpx.Client(transport=httpx.MockTransport(answering(BODY))))

    # Act
    warm.rate("PLN", "EUR")
    down = FrankfurterClient(
        httpx.Client(transport=httpx.MockTransport(answering({}, status=502)))
    ).rate("PLN", "EUR")

    # Assert
    assert down.stale is True
    assert RATE_CACHE.last_good("PLN", "EUR") is not None


# ----------------------------------------------------------- an answer we cannot trust


def test_a_body_that_is_not_json_is_typed_immediately() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>gateway</html>")

    with pytest.raises(RateUnavailableError, match="not JSON"):
        client_for(handler).rate("PLN", "EUR")


def test_a_body_that_is_not_an_object_is_typed() -> None:
    with pytest.raises(RateUnavailableError, match="not an object"):
        client_for(answering([1, 2, 3])).rate("PLN", "EUR")


def test_an_answer_about_a_different_pair_is_refused() -> None:
    """The failure worth the check: a rate applied to the bidder's amount under our own
    label is a wrong number with nothing on the row to give it away."""
    body = {**BODY, "quote": "CZK"}

    with pytest.raises(RateUnavailableError, match="answered about PLN/CZK"):
        client_for(answering(body)).rate("PLN", "EUR")


@pytest.mark.parametrize(
    "body",
    [
        {"date": "2026-09-14", "base": "PLN", "quote": "EUR"},
        {**BODY, "rate": "not a number"},
        {**BODY, "rate": 0},
        {**BODY, "rate": None},
        {**BODY, "date": "the fourteenth"},
        {**BODY, "date": None},
    ],
    ids=["no rate", "unreadable rate", "zero rate", "null rate", "unreadable date", "no date"],
)
def test_a_rate_that_cannot_be_read_is_typed_rather_than_guessed(body: dict[str, Any]) -> None:
    """A zero rate is in here for a reason: it parses, and it would turn every threshold in
    the world into nothing."""
    with pytest.raises(RateUnavailableError, match="cannot read"):
        client_for(answering(body)).rate("PLN", "EUR")
