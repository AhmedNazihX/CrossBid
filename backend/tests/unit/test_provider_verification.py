"""S5.4 — a key is checked with the provider before it is stored.

Offline: `httpx.MockTransport` answers as OpenRouter would. The point of each test is a
sentence a bidder can act on, and an exception that never carries the key.
"""

from __future__ import annotations

import httpx
import pytest

from crossbid.models import Provider
from crossbid.provider_verification import (
    OPENROUTER_KEY_URL,
    VerificationError,
    verify,
    verify_openrouter_key,
)

KEY = "sk-or-v1-0123456789abcdef"


def client_answering(handler: object) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


@pytest.mark.anyio
async def test_a_good_key_comes_back_with_what_the_provider_said() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == f"Bearer {KEY}"
        assert str(request.url) == OPENROUTER_KEY_URL
        return httpx.Response(
            200, json={"data": {"label": "sk-or-v1-5e7...7bd", "limit_remaining": None}}
        )

    async with client_answering(handler) as client:
        verified = await verify_openrouter_key(KEY, client=client)

    assert verified.label == "sk-or-v1-5e7...7bd"
    assert verified.is_exhausted is False


@pytest.mark.anyio
async def test_a_key_with_nothing_left_on_it_is_reported_as_exhausted() -> None:
    """The failure that cost this project two sessions, caught at the form instead."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"label": "x", "limit_remaining": 0}})

    async with client_answering(handler) as client:
        verified = await verify_openrouter_key(KEY, client=client)

    assert verified.is_exhausted is True


@pytest.mark.anyio
@pytest.mark.parametrize("status", [401, 403])
async def test_a_refused_key_says_so_in_words_a_bidder_can_act_on(status: int) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": {"message": "no"}})

    async with client_answering(handler) as client:
        with pytest.raises(VerificationError, match="refused this key"):
            await verify_openrouter_key(KEY, client=client)


@pytest.mark.anyio
async def test_a_provider_that_cannot_be_reached_is_told_apart_from_a_bad_key() -> None:
    """One is worth retrying and the other is worth retyping."""

    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    async with client_answering(handler) as client:
        with pytest.raises(VerificationError, match="could not be reached"):
            await verify_openrouter_key(KEY, client=client)


@pytest.mark.anyio
async def test_no_failure_ever_quotes_the_key() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": KEY}})

    async with client_answering(handler) as client:
        try:
            await verify_openrouter_key(KEY, client=client)
        except VerificationError as exc:
            assert KEY not in str(exc)


@pytest.mark.anyio
@pytest.mark.parametrize("provider", [Provider.OPENAI, Provider.ANTHROPIC])
async def test_a_provider_nothing_can_call_yet_is_refused_rather_than_stored(
    provider: Provider,
) -> None:
    """Every configured slug is an OpenRouter slug, so such a key would have nothing to
    call. Saying so beats saving a key that silently never gets used."""
    with pytest.raises(VerificationError, match="cannot be used yet"):
        await verify(provider, KEY)
