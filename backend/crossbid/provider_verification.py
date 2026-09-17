"""S5.4 — is this key real? Asked of the provider, before it is stored as verified.

A key is verified by spending nothing: OpenRouter's `GET /api/v1/key` answers for the key in
the `Authorization` header and costs no tokens. It also reports the key's own spending cap,
which is the difference between "this key works" and "this key works and has money", and a
cap of zero is exactly the failure that cost this project two sessions (ADR-0087, ADR-0090).

**A key that is refused is not stored.** The alternative — save it and find out on the first
bid — moves a typo from a form field the bidder is looking at to a run that fails four
minutes in.

Direct OpenAI and Anthropic keys are not verified here because they are not used anywhere
yet: every slug in `settings.default.yaml` is an OpenRouter slug, so a key for another
provider would have nothing to call. `Provider` carries the other two for the day that
changes, and this refuses them rather than pretending.
"""

from __future__ import annotations

from typing import Final

import httpx
from pydantic import BaseModel, ConfigDict

from crossbid.models import Provider

OPENROUTER_KEY_URL: Final = "https://openrouter.ai/api/v1/key"
VERIFY_TIMEOUT_SECONDS: Final = 10.0


class VerificationError(RuntimeError):
    """The key was refused, or the provider could not be reached. Never carries the key."""


class VerifiedKey(BaseModel):
    """What the provider said about the key, in the two terms a bidder acts on."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str | None
    limit_remaining: float | None
    """`None` means no cap on this key, which is the usual and the good case. `0` means the
    key is real and will refuse the first call, which is worth saying now rather than later."""

    @property
    def is_exhausted(self) -> bool:
        return self.limit_remaining is not None and self.limit_remaining <= 0


async def verify_openrouter_key(
    provider_key: str, *, client: httpx.AsyncClient | None = None
) -> VerifiedKey:
    """Ask OpenRouter about the key. Raises `VerificationError` if it is not usable."""
    owned = client is None
    http = client or httpx.AsyncClient(timeout=VERIFY_TIMEOUT_SECONDS)
    try:
        response = await http.get(
            OPENROUTER_KEY_URL, headers={"Authorization": f"Bearer {provider_key}"}
        )
    except httpx.HTTPError as exc:
        # The message never quotes the request: the key is in its headers.
        raise VerificationError(
            "OpenRouter could not be reached to check the key. Try again."
        ) from exc
    finally:
        if owned:
            await http.aclose()

    if response.status_code in {401, 403}:
        raise VerificationError(
            "OpenRouter refused this key. Check that it was copied whole, and that it has "
            "not been revoked."
        )
    if response.status_code >= 400:
        raise VerificationError(
            f"OpenRouter answered {response.status_code} when asked about this key. Try again."
        )

    data = response.json().get("data", {})
    return VerifiedKey(label=data.get("label"), limit_remaining=data.get("limit_remaining"))


async def verify(
    provider: Provider, provider_key: str, *, client: httpx.AsyncClient | None = None
) -> VerifiedKey:
    """Verify a key for `provider`, or refuse a provider nothing can use yet."""
    if provider is not Provider.OPENROUTER:
        raise VerificationError(
            f"Keys for {provider.value} cannot be used yet: every model this app is "
            "configured with is an OpenRouter slug. Save an OpenRouter key instead."
        )
    return await verify_openrouter_key(provider_key, client=client)
