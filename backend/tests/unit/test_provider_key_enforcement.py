"""S5.4, S5.5 — a company's work runs on that company's key, or it does not run.

The behaviour these tests pin is a billing boundary, not a convenience. Before this, every
model call in the product went out on one application key: whoever held it paid for
everyone's runs, and a cap reached on it stopped every account at once — which is exactly
how two sessions of this project were spent (ADR-0087, ADR-0090).

So the rule is: no key, no work, and **never** a silent fall back to the application key.
`402 Payment Required` is the answer, because what is missing is the means to pay.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from crossbid.company_keys import (
    NO_PROVIDER_KEY_DETAIL,
    NoProviderKeyError,
    settings_for_company,
    with_provider_key,
)
from crossbid.crypto import seal
from crossbid.settings import Settings
from tests.conftest import FakeConnectionSource

COMPANY = uuid.UUID("11111111-1111-4111-8111-111111111111")
COMPANY_KEY = "sk-or-v1-the-companys-own-key"


def saved_row(encryption_key: SecretStr) -> dict[str, Any]:
    return {
        "company_id": COMPANY,
        "provider": "openrouter",
        "encrypted_key": seal(COMPANY_KEY, key=encryption_key),
        "key_hint": "-key",
        "verified_at": None,
        "created_at": None,
    }


@pytest.mark.anyio
async def test_a_companys_settings_carry_that_companys_key(
    offline_settings: Settings,
) -> None:
    # Arrange
    source = FakeConnectionSource([saved_row(offline_settings.env.app_encryption_key)])

    # Act
    resolved = await settings_for_company(source, offline_settings, company_id=COMPANY)

    # Assert
    assert resolved.env.openrouter_api_key.get_secret_value() == COMPANY_KEY


@pytest.mark.anyio
async def test_the_application_key_is_not_handed_out_when_a_company_has_none(
    offline_settings: Settings,
) -> None:
    """The whole point. A fallback here is one account paying for another's bids."""
    # Arrange
    source = FakeConnectionSource([])

    # Act / Assert
    with pytest.raises(NoProviderKeyError) as refusal:
        await settings_for_company(source, offline_settings, company_id=COMPANY)
    assert str(refusal.value) == NO_PROVIDER_KEY_DETAIL


@pytest.mark.anyio
async def test_the_refusal_names_where_to_fix_it(offline_settings: Settings) -> None:
    """A bidder can act on this one themselves, so the sentence has to say how."""
    source = FakeConnectionSource([])

    with pytest.raises(NoProviderKeyError, match="company profile"):
        await settings_for_company(source, offline_settings, company_id=COMPANY)


@pytest.mark.anyio
async def test_resolving_one_company_does_not_alter_the_shared_settings(
    offline_settings: Settings,
) -> None:
    """`Settings` is frozen and shared across requests; a mutation here would leak one
    company's key into the next company's run."""
    # Arrange
    before = offline_settings.env.openrouter_api_key.get_secret_value()
    source = FakeConnectionSource([saved_row(offline_settings.env.app_encryption_key)])

    # Act
    await settings_for_company(source, offline_settings, company_id=COMPANY)

    # Assert
    assert offline_settings.env.openrouter_api_key.get_secret_value() == before


def test_two_companies_get_two_different_settings(offline_settings: Settings) -> None:
    first = with_provider_key(offline_settings, SecretStr("sk-or-v1-first"))
    second = with_provider_key(offline_settings, SecretStr("sk-or-v1-second"))

    assert first.env.openrouter_api_key.get_secret_value() == "sk-or-v1-first"
    assert second.env.openrouter_api_key.get_secret_value() == "sk-or-v1-second"


@pytest.mark.anyio
async def test_a_key_sealed_under_a_different_encryption_key_is_reported_not_ignored(
    offline_settings: Settings,
) -> None:
    """Rotating `APP_ENCRYPTION_KEY` without re-saving makes every stored key unreadable.
    That must surface as a refusal to run, never as a quiet fall back to the app key."""
    # Arrange -- sealed under a key this deployment does not have
    stranger = SecretStr(Fernet.generate_key().decode())
    source = FakeConnectionSource([saved_row(stranger)])

    # Act / Assert
    from crossbid.crypto import CryptoError

    with pytest.raises(CryptoError, match="could not be decrypted"):
        await settings_for_company(source, offline_settings, company_id=COMPANY)
