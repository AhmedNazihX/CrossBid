"""S1.3.1 against the real Frankfurter API. Marked `live`: excluded from `make test`, run by
`make test-live`.

It costs nothing — the service is public, needs no key and charges nothing — but it is the
only thing that can fail when the API moves on, which it is visibly in the middle of doing:
v1 is `frozen` and sends a `deprecation` header, v2 is `current`. The unit tests pin the
mapping against a recorded answer; this pins that the recording is still what is sent.

The first test is the one that matters. `/v2/rate/{base}/{quote}` blends about a hundred
central banks, and the story asks for the ECB's reference rate — if the `providers/ECB`
prefix ever stops selecting the ECB alone, every threshold on the matrix quietly moves.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from crossbid.reference.frankfurter_client import (
    REQUEST_TIMEOUT_S,
    FrankfurterClient,
    RateCache,
    UnknownCurrencyPairError,
)

pytestmark = pytest.mark.live


@pytest.fixture
def client() -> FrankfurterClient:
    """A cache of its own, so a live answer never leaks into the process-wide one."""
    return FrankfurterClient(httpx.Client(timeout=REQUEST_TIMEOUT_S), cache=RateCache())


def test_the_ecb_rate_differs_from_the_multi_provider_blend(client: FrankfurterClient) -> None:
    """Probed 2026-09-14: ECB 0.23032, blend 0.23069. Both are plausible numbers, which is
    exactly why this has to be asserted rather than eyeballed."""
    ours = client.rate("PLN", "EUR")
    blended = httpx.get(
        "https://api.frankfurter.dev/v2/rate/PLN/EUR", timeout=REQUEST_TIMEOUT_S
    ).json()

    assert ours.rate != blended["rate"], "the providers/ECB prefix has stopped selecting"


def test_a_threshold_in_zloty_converts_to_a_euro_figure(client: FrankfurterClient) -> None:
    """The story's first criterion against the live service. The band is wide on purpose:
    this is a check that the rate is a rate, not a forecast of the zloty."""
    rate = client.rate("PLN", "EUR")

    assert 0.1 < rate.rate < 0.5
    assert rate.stale is False
    assert 200_000 < 2_000_000 * rate.rate < 1_000_000


def test_the_date_is_the_ecbs_publication_day(client: FrankfurterClient) -> None:
    """Never in the future, and stale over a weekend — which is why it is reported."""
    assert client.rate("EUR", "USD").rate_date <= datetime.now(UTC).date()


def test_a_currency_the_ecb_does_not_quote_is_a_refusal_and_not_an_outage(
    client: FrankfurterClient,
) -> None:
    """AFN is a real currency (Frankfurter lists it) that the ECB does not publish: 404."""
    with pytest.raises(UnknownCurrencyPairError):
        client.rate("EUR", "AFN")
