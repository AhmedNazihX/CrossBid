"""S5.4 — the `provider_keys` read model: one key per company per provider, scoped.

Offline, over `conftest`'s recording connection, so what is asserted is the statement
Postgres would receive. The API connects as a `BYPASSRLS` role (ADR-0009), so the
`company_id = %(company_id)s` in each statement is the only tenant boundary there is:
asserting it is a security test.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from crossbid.crypto import seal
from crossbid.models import Provider
from crossbid.readmodel.provider_keys import (
    DELETE_PROVIDER_KEY_SQL,
    SELECT_PROVIDER_KEY_SQL,
    UPSERT_PROVIDER_KEY_SQL,
    ProviderKeyRecord,
    ProviderKeysReadModel,
)
from tests.conftest import FakeConnectionSource

COMPANY = uuid.UUID("11111111-1111-4111-8111-111111111111")
OTHER_COMPANY = uuid.UUID("22222222-2222-4222-8222-222222222222")
ENCRYPTION_KEY = SecretStr(Fernet.generate_key().decode())
PROVIDER_KEY = "sk-or-v1-0123456789abcdef0123456789abcdef"
SAVED_AT = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)


def row(company_id: uuid.UUID = COMPANY) -> dict[str, object]:
    return {
        "company_id": company_id,
        "provider": Provider.OPENROUTER.value,
        "encrypted_key": seal(PROVIDER_KEY, key=ENCRYPTION_KEY),
        "key_hint": "cdef",
        "verified_at": SAVED_AT,
        "created_at": SAVED_AT,
    }


@pytest.mark.anyio
async def test_saving_a_key_stores_ciphertext_and_never_the_key() -> None:
    """The one assertion this table exists for."""
    # Arrange
    source = FakeConnectionSource([row()])
    model = ProviderKeysReadModel(source, encryption_key=ENCRYPTION_KEY)

    # Act
    await model.save(
        company_id=COMPANY, provider=Provider.OPENROUTER, provider_key=PROVIDER_KEY
    )

    # Assert
    statement = source.only
    assert PROVIDER_KEY not in str(statement.params)
    assert statement.params["key_hint"] == "cdef"
    assert isinstance(statement.params["encrypted_key"], bytes)


@pytest.mark.anyio
async def test_saving_again_replaces_the_key_rather_than_adding_a_second() -> None:
    """`primary key (company_id, provider)`: a bidder pasting a new key has one key, not two."""
    source = FakeConnectionSource([row()])
    model = ProviderKeysReadModel(source, encryption_key=ENCRYPTION_KEY)

    await model.save(
        company_id=COMPANY, provider=Provider.OPENROUTER, provider_key=PROVIDER_KEY
    )

    assert "on conflict (company_id, provider) do update" in source.only.sql.lower()


@pytest.mark.anyio
async def test_reading_a_key_scopes_the_statement_to_the_company() -> None:
    source = FakeConnectionSource([row()])
    model = ProviderKeysReadModel(source, encryption_key=ENCRYPTION_KEY)

    await model.get(company_id=COMPANY, provider=Provider.OPENROUTER)

    assert "company_id = %(company_id)s" in source.only.sql
    assert source.only.params["company_id"] == COMPANY


@pytest.mark.anyio
async def test_the_key_comes_back_usable() -> None:
    source = FakeConnectionSource([row()])
    model = ProviderKeysReadModel(source, encryption_key=ENCRYPTION_KEY)

    found = await model.get(company_id=COMPANY, provider=Provider.OPENROUTER)

    assert found is not None
    assert found.provider_key.get_secret_value() == PROVIDER_KEY
    assert found.key_hint == "cdef"


@pytest.mark.anyio
async def test_a_company_with_no_key_reads_as_none_rather_than_raising() -> None:
    """ "No key saved" is an ordinary state, not an error: it is what a new company looks
    like, and the caller turns it into a sentence the bidder can act on."""
    source = FakeConnectionSource([])
    model = ProviderKeysReadModel(source, encryption_key=ENCRYPTION_KEY)

    assert await model.get(company_id=COMPANY, provider=Provider.OPENROUTER) is None


@pytest.mark.anyio
async def test_deleting_is_scoped_to_the_company_too() -> None:
    source = FakeConnectionSource([{"company_id": COMPANY}])
    model = ProviderKeysReadModel(source, encryption_key=ENCRYPTION_KEY)

    removed = await model.delete(company_id=COMPANY, provider=Provider.OPENROUTER)

    assert removed is True
    assert "company_id = %(company_id)s" in source.only.sql


@pytest.mark.anyio
async def test_deleting_a_key_that_is_not_there_says_so_rather_than_pretending() -> None:
    source = FakeConnectionSource([])
    model = ProviderKeysReadModel(source, encryption_key=ENCRYPTION_KEY)

    assert await model.delete(company_id=COMPANY, provider=Provider.OPENROUTER) is False


def test_every_statement_is_scoped_by_company() -> None:
    """The guard: a statement added later without a tenant clause fails here."""
    for statement in (
        SELECT_PROVIDER_KEY_SQL,
        UPSERT_PROVIDER_KEY_SQL,
        DELETE_PROVIDER_KEY_SQL,
    ):
        assert "%(company_id)s" in statement


def test_the_record_does_not_print_the_key() -> None:
    """It ends up in a log line or an exception sooner or later."""
    record = ProviderKeyRecord(
        provider=Provider.OPENROUTER,
        provider_key=SecretStr(PROVIDER_KEY),
        key_hint="cdef",
        verified_at=SAVED_AT,
    )

    assert PROVIDER_KEY not in repr(record)
