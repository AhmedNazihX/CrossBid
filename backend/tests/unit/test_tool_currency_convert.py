"""S1.3.1 — `currency_convert`, the tool the matrix needs before it can compare two amounts.

Offline: the client underneath is exercised in `test_frankfurter_client.py` against
`httpx.MockTransport`, so what is pinned here is the *tool* — its manifest, its argument
schema, and the shape of what the model gets back.

The story's first criterion is stated literally below: 2 000 000 PLN in, a euro figure and
the date of the rate out. The second is the one that shapes the answer's schema — a stale
rate is an `ok` with a flag, not a failure, because a bidder sizing a bid bond against
Friday's rate is in a different position from one who has no rate at all.

Totality is the standing rule from S3.3.1: `check_reqs` calls tools inside a per-requirement
ReAct loop that has already cost money, so a downed Frankfurter comes back as a status the
model can read rather than as an exception.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from pydantic import ValidationError

from crossbid.reference.frankfurter_client import (
    ExchangeRate,
    RateUnavailableError,
    UnknownCurrencyPairError,
)
from crossbid.tools.currency_convert import MANIFEST, CurrencyConvertArgs, build_tool

PLN_EUR = ExchangeRate(
    base="PLN", quote="EUR", rate=0.23032, rate_date=date(2026, 9, 14), stale=False
)


def run_tool(**kwargs: Any) -> dict[str, Any]:
    """The bound tool, invoked as the model would, with the client patched out."""
    tool = build_tool(context=None)  # type: ignore[arg-type]  - unused, see the module
    result: dict[str, Any] = tool.invoke(kwargs)
    return result


def answering(rate: ExchangeRate) -> Any:
    class Fake:
        def rate(self, *_: Any, **__: Any) -> ExchangeRate:
            return rate

    return lambda *_, **__: Fake()


def raising(error: Exception) -> Any:
    class Fake:
        def rate(self, *_: Any, **__: Any) -> ExchangeRate:
            raise error

    return lambda *_, **__: Fake()


# ------------------------------------------------------------------------------ manifest


def test_the_manifest_says_the_tool_leaves_the_process() -> None:
    """`settings.default.yaml` lists it, so `default_enabled` has to agree, and it opens a
    socket, so an operator has to be able to see that and turn it off."""
    assert MANIFEST.name == "currency_convert"
    assert MANIFEST.external is True
    assert MANIFEST.default_enabled is True


def test_the_description_tells_the_model_what_stale_means() -> None:
    """A rate flagged stale is still an answer; the model has to know to say so rather than
    to treat the flag as noise."""
    assert "European Central Bank" in MANIFEST.description
    assert "stale" in MANIFEST.description
    assert "unknown_currency" in MANIFEST.description


# ------------------------------------------------------------------------ argument schema


def test_a_currency_that_is_not_three_letters_is_refused_by_the_schema() -> None:
    """Bound into the tool schema, so a malformed code is rejected before any request."""
    with pytest.raises(ValidationError):
        CurrencyConvertArgs(amount=1.0, from_currency="zloty")


def test_an_amount_of_zero_or_less_is_refused() -> None:
    """A threshold is a positive number; converting anything else is a modelling mistake
    worth surfacing rather than answering."""
    with pytest.raises(ValidationError):
        CurrencyConvertArgs(amount=0, from_currency="PLN")


def test_the_target_defaults_to_the_currency_the_matrix_compares_in() -> None:
    assert CurrencyConvertArgs(amount=1.0, from_currency="PLN").to_currency == "EUR"


# ----------------------------------------------------------------------------- behaviour


def test_two_million_zloty_comes_back_in_euro_with_the_rate_date() -> None:
    """The story's first criterion, word for word."""
    with patch("crossbid.tools.currency_convert.FrankfurterClient", answering(PLN_EUR)):
        result = run_tool(amount=2_000_000, from_currency="PLN")

    assert result == {
        "status": "ok",
        "amount": 2_000_000,
        "from": "PLN",
        "to": "EUR",
        "converted": 460_640.0,
        "rate": 0.23032,
        "rate_date": "2026-09-14",
        "stale": False,
    }


def test_the_converted_amount_is_the_cited_rate_times_the_amount() -> None:
    """The citation has to be checkable by hand: the row carries the rate, the date and the
    arithmetic that connects them."""
    with patch("crossbid.tools.currency_convert.FrankfurterClient", answering(PLN_EUR)):
        result = run_tool(amount=1_234.56, from_currency="pln", to_currency="eur")

    assert result["converted"] == round(1_234.56 * result["rate"], 2)


def test_a_stale_rate_is_an_answer_with_a_flag_and_not_a_failure() -> None:
    """The story's second criterion as the model sees it: still `ok`, still convertible,
    and carrying the date of the rate it fell back to."""
    stale = PLN_EUR.model_copy(update={"stale": True, "rate_date": date(2026, 9, 11)})
    with patch("crossbid.tools.currency_convert.FrankfurterClient", answering(stale)):
        result = run_tool(amount=2_000_000, from_currency="PLN")

    assert result["status"] == "ok"
    assert result["stale"] is True
    assert result["rate_date"] == "2026-09-11"


def test_an_unreachable_service_is_a_status_and_never_an_exception() -> None:
    """S3.3.1's rule: a tool may not end a run that has already cost money."""
    with patch(
        "crossbid.tools.currency_convert.FrankfurterClient",
        raising(RateUnavailableError("no route")),
    ):
        result = run_tool(amount=2_000_000, from_currency="PLN")

    assert result["status"] == "unavailable"
    assert "no route" in result["detail"]
    assert "converted" not in result, "a failure must not carry a number that looks usable"


def test_a_currency_the_ecb_does_not_publish_is_its_own_status() -> None:
    """Separate from `unavailable` so the model stops asking instead of backing off: no
    amount of waiting will make the ECB quote that pair."""
    with patch(
        "crossbid.tools.currency_convert.FrankfurterClient",
        raising(UnknownCurrencyPairError("the ECB publishes no EUR/AFN rate (HTTP 404)")),
    ):
        result = run_tool(amount=100, from_currency="EUR", to_currency="AFN")

    assert result["status"] == "unknown_currency"
    assert "AFN" in result["detail"]


def test_the_currencies_asked_for_reach_the_client() -> None:
    """The tool passes the pair straight through; casing is the client's to normalise."""
    seen: list[tuple[str, str]] = []

    class Recording:
        def rate(self, base: str, quote: str) -> ExchangeRate:
            seen.append((base, quote))
            return PLN_EUR

    with patch(
        "crossbid.tools.currency_convert.FrankfurterClient", lambda *_, **__: Recording()
    ):
        run_tool(amount=1.0, from_currency="pln", to_currency="EUR")

    assert seen == [("pln", "EUR")]


def opened_clients(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Client]:
    """Records every `httpx.Client` the module under test opens, and hands back the real one.

    M22: the leak is in the tool, not in the client wrapper the other tests patch out, so it
    is only visible from here — one layer further down than the fake.
    """
    opened: list[httpx.Client] = []
    real = httpx.Client

    def recording(*args: Any, **kwargs: Any) -> httpx.Client:
        client = real(*args, **kwargs)
        opened.append(client)
        return client

    monkeypatch.setattr(httpx, "Client", recording)
    return opened


def test_the_tool_closes_the_http_client_it_opened(monkeypatch: pytest.MonkeyPatch) -> None:
    """The worst of the four leaks: this tool is built per call inside a per-requirement
    loop, so a 350-requirement pack left 350 connection pools to the garbage collector."""
    # Arrange
    opened = opened_clients(monkeypatch)

    # Act
    with patch("crossbid.tools.currency_convert.FrankfurterClient", answering(PLN_EUR)):
        run_tool(amount=2_000_000, from_currency="PLN")

    # Assert
    assert opened, "the tool opened no client at all; this test is watching the wrong thing"
    assert all(client.is_closed for client in opened)


def test_a_downed_rate_service_still_closes_the_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A leak on the failure path is the one that compounds: it happens when TED or the ECB
    is having a bad day and the loop is retrying."""
    opened = opened_clients(monkeypatch)

    with patch(
        "crossbid.tools.currency_convert.FrankfurterClient",
        raising(RateUnavailableError("no route to host")),
    ):
        run_tool(amount=1.0, from_currency="PLN")

    assert opened and all(client.is_closed for client in opened)
