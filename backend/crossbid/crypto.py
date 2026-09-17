"""S5.4 — a company's provider key at rest, and the only place it is ever readable.

**The threat is a database dump.** `provider_keys.encrypted_key` is a Fernet token and
`APP_ENCRYPTION_KEY` lives only in the process environment, so a dump on its own yields the
last four characters of a key and the date it was saved. That is also the whole of what may
ever leave the server: the read model returns the hint, and the plaintext exists for the
length of one model call.

Fernet rather than raw AES because it is authenticated: a token that has been altered fails
to open instead of decrypting to rubbish that would then be sent to a provider as a key.

Nothing here logs, and no exception carries the key. `CryptoError` says what failed and
nothing about the value -- the same promise `LlmError` makes, for the same reason: these
strings end up in logs.
"""

from __future__ import annotations

from typing import Final

from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr

HINT_LENGTH: Final = 4
"""`provider_keys.key_hint` is `check (char_length(key_hint) = 4)`, so this is the database's
rule as much as this module's."""

HINT_PADDING: Final = "•"
"""What a key shorter than the hint is padded with. A key that short is not a real one, but
the column's length check is not negotiable and truncating to fewer characters would break
the insert rather than the key."""


class CryptoError(RuntimeError):
    """A key could not be sealed or opened. Never carries the key or the encryption key."""


def _cipher(key: SecretStr) -> Fernet:
    try:
        return Fernet(key.get_secret_value().encode())
    except (ValueError, TypeError) as exc:
        raise CryptoError(
            "APP_ENCRYPTION_KEY is not a valid Fernet key; it must be 32 url-safe "
            "base64-encoded bytes, as `Fernet.generate_key()` produces"
        ) from exc


def seal(provider_key: str, *, key: SecretStr) -> bytes:
    """The provider key as ciphertext, ready for `provider_keys.encrypted_key`."""
    if not provider_key.strip():
        raise CryptoError("the provider key is empty")
    return _cipher(key).encrypt(provider_key.encode())


def unseal(token: bytes, *, key: SecretStr) -> str:
    """The provider key back, or `CryptoError`.

    A failure here means the stored token was written under a different `APP_ENCRYPTION_KEY`
    or has been altered. Neither is recoverable by retrying, and both are the company's
    saved key being unusable -- which is something to tell the bidder, not to paper over.
    """
    try:
        return _cipher(key).decrypt(token).decode()
    except InvalidToken as exc:
        raise CryptoError(
            "the stored provider key could not be decrypted; it was saved under a different "
            "APP_ENCRYPTION_KEY, or it has been altered. Save the key again."
        ) from exc


def key_hint(provider_key: str) -> str:
    """The last four characters, which is the one part of a key allowed to leave the server.

    Four is enough for a bidder to recognise which key they saved and useless to anyone else.
    """
    tail = provider_key.strip()[-HINT_LENGTH:]
    return tail.rjust(HINT_LENGTH, HINT_PADDING)
