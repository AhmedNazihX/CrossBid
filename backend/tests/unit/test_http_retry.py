"""`is_retryable` — the one judgement four HTTP clients used to make four different ways.

Audit finding M21. Three of the four retry loops caught `httpx.HTTPError` flat, so a 400 was
sent again exactly as readily as a reset connection: a malformed TED query went twice, an
eCertis path that does not exist slept two seconds and went three times, and a bidder waited
the whole of it to be told something the first answer had already settled.

The loops themselves stay separate and are meant to — eCertis reads a catalogue on a
sixty-second budget and can afford to sleep, a TED search sits inside a request somebody is
waiting on. What they must agree on is which failures are permanent, because that is a fact
about HTTP rather than a policy of the caller. This module is that fact, and these are its
edges.
"""

from __future__ import annotations

import httpx
import pytest

from crossbid.http_retry import RETRYABLE_STATUS_CODES, is_retryable

REQUEST = httpx.Request("GET", "https://example.invalid/thing")


def status_error(code: int) -> httpx.HTTPStatusError:
    """The error `raise_for_status` produces for `code`."""
    response = httpx.Response(code, request=REQUEST)
    return httpx.HTTPStatusError(f"HTTP {code}", request=REQUEST, response=response)


# ------------------------------------------------------------------ what comes back again


@pytest.mark.parametrize("code", sorted(RETRYABLE_STATUS_CODES))
def test_a_transient_status_is_worth_another_attempt(code: int) -> None:
    assert is_retryable(status_error(code))


@pytest.mark.parametrize("code", [400, 401, 403, 404, 405, 410, 418, 422, 451])
def test_a_permanent_refusal_is_not(code: int) -> None:
    """The server is saying the request is the problem, and it will say it again."""
    assert not is_retryable(status_error(code))


def test_404_is_not_retryable_because_of_how_openrouter_refuses_a_slug() -> None:
    """ADR-0005: a model listed in the catalogue is refused by this account's data policy
    with a 404. Retrying it turns a clear configuration error into a slow one."""
    assert not is_retryable(status_error(404))


def test_429_is_retryable_because_waiting_is_the_whole_remedy() -> None:
    assert is_retryable(status_error(429))


# --------------------------------------------------------------------- transport failures


@pytest.mark.parametrize(
    "error",
    [
        httpx.ConnectError("connection refused", request=REQUEST),
        httpx.ReadTimeout("timed out", request=REQUEST),
        httpx.RemoteProtocolError("peer closed connection", request=REQUEST),
        httpx.ConnectTimeout("timed out", request=REQUEST),
    ],
    ids=["refused", "read timeout", "protocol", "connect timeout"],
)
def test_a_transport_failure_is_always_worth_another_attempt(error: httpx.HTTPError) -> None:
    """Nothing about a reset connection says the request was wrong."""
    assert is_retryable(error)


def test_an_http_error_carrying_no_response_is_treated_as_transport() -> None:
    """The safe direction: one wasted attempt beats giving up on a blip.

    `HTTPError` is the base class, and a subclass this module has never heard of arrives
    here with no status to judge. Refusing it would make an unknown failure permanent.
    """
    assert is_retryable(httpx.HTTPError("something new"))


def test_no_success_code_is_in_the_retryable_set() -> None:
    """A guard on the constant itself: a 2xx in here would make a success look transient."""
    assert not any(200 <= code < 300 for code in RETRYABLE_STATUS_CODES)
