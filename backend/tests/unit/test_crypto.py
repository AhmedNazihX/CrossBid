"""S5.4 — a company's provider key at rest: Fernet in, Fernet out, and nothing in a log.

The threat this answers is a database dump. `provider_keys.encrypted_key` is ciphertext and
`APP_ENCRYPTION_KEY` never goes near Postgres, so a dump on its own buys an attacker the
last four characters and a timestamp.
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from crossbid.crypto import CryptoError, key_hint, seal, unseal

KEY = SecretStr(Fernet.generate_key().decode())
OTHER_KEY = SecretStr(Fernet.generate_key().decode())
PROVIDER_KEY = "sk-or-v1-0123456789abcdef0123456789abcdef"


def test_a_sealed_key_comes_back_unchanged() -> None:
    assert unseal(seal(PROVIDER_KEY, key=KEY), key=KEY) == PROVIDER_KEY


def test_the_ciphertext_does_not_contain_the_key() -> None:
    """The point of the exercise, stated as a test rather than assumed."""
    assert PROVIDER_KEY.encode() not in seal(PROVIDER_KEY, key=KEY)


def test_sealing_twice_gives_different_ciphertext() -> None:
    """Fernet carries a timestamp and a random IV; equal ciphertexts would leak equality
    between two companies holding the same key."""
    assert seal(PROVIDER_KEY, key=KEY) != seal(PROVIDER_KEY, key=KEY)


def test_another_encryption_key_cannot_open_it() -> None:
    sealed = seal(PROVIDER_KEY, key=KEY)

    with pytest.raises(CryptoError, match="could not be decrypted"):
        unseal(sealed, key=OTHER_KEY)


def test_a_corrupted_token_is_refused_rather_than_half_read() -> None:
    sealed = bytearray(seal(PROVIDER_KEY, key=KEY))
    sealed[-1] ^= 0x01

    with pytest.raises(CryptoError, match="could not be decrypted"):
        unseal(bytes(sealed), key=KEY)


def test_an_encryption_key_that_is_not_a_fernet_key_says_so() -> None:
    """A clear refusal at the boundary, rather than a `binascii` error from three frames in."""
    with pytest.raises(CryptoError, match="not a valid Fernet key"):
        seal(PROVIDER_KEY, key=SecretStr("nowhere near base64"))


def test_a_blank_provider_key_is_refused() -> None:
    with pytest.raises(CryptoError, match="empty"):
        seal("   ", key=KEY)


def test_the_hint_is_the_last_four_characters() -> None:
    assert key_hint(PROVIDER_KEY) == "cdef"


def test_the_hint_of_a_short_key_is_still_four_characters_and_leaks_no_more() -> None:
    """`provider_keys.key_hint` is `char_length(key_hint) = 4` in the schema, so this is the
    database's rule as much as ours."""
    assert len(key_hint("abc")) == 4
    assert key_hint("abc") == "•abc"


def test_the_error_never_carries_the_key() -> None:
    """An exception ends up in a log; `LlmError` makes the same promise for the same reason."""
    try:
        unseal(seal(PROVIDER_KEY, key=KEY), key=OTHER_KEY)
    except CryptoError as exc:
        assert PROVIDER_KEY not in str(exc)
    else:  # pragma: no cover - the call above must raise
        pytest.fail("unseal accepted the wrong key")
