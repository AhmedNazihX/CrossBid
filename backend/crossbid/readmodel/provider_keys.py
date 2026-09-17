"""S5.4 — `provider_keys`: one key per company per provider, sealed at rest.

The table has been in `0001_init.sql` since the beginning and this is what finally writes to
it. Two rules it exists to keep:

**The key is ciphertext in Postgres and plaintext only in one process.** `crypto.seal` runs
before the statement and `crypto.unseal` after it, so the encryption key never reaches the
database and a dump yields `key_hint` -- four characters -- and a timestamp.

**Every statement is scoped by `company_id`.** The API connects as a `BYPASSRLS` role
(ADR-0009), so the `where company_id = %(company_id)s` written into each statement here is
the entire tenant boundary for the most sensitive row in the schema. There is deliberately no
"read every key" statement: nothing in the product needs one, and the absence is the feature.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Final, LiteralString

from pydantic import BaseModel, ConfigDict, SecretStr

from crossbid.crypto import key_hint, seal, unseal
from crossbid.models import Provider
from crossbid.readmodel.documents import ConnectionSource

UPSERT_PROVIDER_KEY_SQL: Final[LiteralString] = """
insert into provider_keys (company_id, provider, encrypted_key, key_hint, verified_at)
values (%(company_id)s, %(provider)s, %(encrypted_key)s, %(key_hint)s, %(verified_at)s)
on conflict (company_id, provider) do update
set encrypted_key = excluded.encrypted_key,
    key_hint = excluded.key_hint,
    verified_at = excluded.verified_at
returning company_id, provider, encrypted_key, key_hint, verified_at, created_at
"""
"""Replace, never accumulate: `primary key (company_id, provider)` means a bidder pasting a
new key has one key rather than two, and no way to wonder which one is in force."""

SELECT_PROVIDER_KEY_SQL: Final[LiteralString] = """
select company_id, provider, encrypted_key, key_hint, verified_at, created_at
from provider_keys
where company_id = %(company_id)s and provider = %(provider)s
"""

DELETE_PROVIDER_KEY_SQL: Final[LiteralString] = """
delete from provider_keys
where company_id = %(company_id)s and provider = %(provider)s
returning company_id
"""


class ProviderKeyRecord(BaseModel):
    """One saved key, open. `provider_key` is a `SecretStr` so no log line can print it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: Provider
    provider_key: SecretStr
    key_hint: str
    verified_at: datetime | None


class SavedProviderKey(BaseModel):
    """What the bidder is allowed to see back: the hint, and when it was last verified."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: Provider
    key_hint: str
    verified_at: datetime | None
    created_at: datetime


class ProviderKeysReadModel:
    """`provider_keys`, sealed on the way in and opened on the way out."""

    def __init__(self, source: ConnectionSource, *, encryption_key: SecretStr) -> None:
        self._source = source
        self._encryption_key = encryption_key

    async def save(
        self,
        *,
        company_id: uuid.UUID,
        provider: Provider,
        provider_key: str,
        verified_at: datetime | None = None,
    ) -> SavedProviderKey:
        """Seal the key and write it, replacing whatever was there.

        `verified_at` is the caller's: verification is a call to the provider, which is not
        this layer's business. `None` records a key that was stored without being checked.
        """
        row = await self._fetch_one(
            UPSERT_PROVIDER_KEY_SQL,
            {
                "company_id": company_id,
                "provider": provider.value,
                "encrypted_key": seal(provider_key, key=self._encryption_key),
                "key_hint": key_hint(provider_key),
                "verified_at": verified_at,
            },
        )
        if row is None:  # pragma: no cover - an upsert with `returning` always answers
            raise RuntimeError("the provider key was not written")
        return _saved(row)

    async def get(
        self, *, company_id: uuid.UUID, provider: Provider
    ) -> ProviderKeyRecord | None:
        """The company's key for one provider, open and ready to use, or `None`.

        `None` is an ordinary answer: it is what a company that has not saved a key looks
        like, and the caller turns it into a sentence rather than an exception.
        """
        row = await self._fetch_one(
            SELECT_PROVIDER_KEY_SQL,
            {"company_id": company_id, "provider": provider.value},
        )
        if row is None:
            return None
        return ProviderKeyRecord(
            provider=Provider(row["provider"]),
            provider_key=SecretStr(unseal(row["encrypted_key"], key=self._encryption_key)),
            key_hint=row["key_hint"],
            verified_at=row["verified_at"],
        )

    async def saved(
        self, *, company_id: uuid.UUID, provider: Provider
    ) -> SavedProviderKey | None:
        """What the company profile screen shows: the hint and the dates, never the key."""
        row = await self._fetch_one(
            SELECT_PROVIDER_KEY_SQL,
            {"company_id": company_id, "provider": provider.value},
        )
        return None if row is None else _saved(row)

    async def delete(self, *, company_id: uuid.UUID, provider: Provider) -> bool:
        """`False` when there was nothing to delete, so the route can answer 404 honestly."""
        row = await self._fetch_one(
            DELETE_PROVIDER_KEY_SQL,
            {"company_id": company_id, "provider": provider.value},
        )
        return row is not None

    async def _fetch_one(
        self, sql: LiteralString, params: dict[str, Any]
    ) -> dict[str, Any] | None:
        async with self._source.connection() as connection:
            cursor = await connection.execute(sql, params)
            return await cursor.fetchone()


def _saved(row: dict[str, Any]) -> SavedProviderKey:
    return SavedProviderKey(
        provider=Provider(row["provider"]),
        key_hint=row["key_hint"],
        verified_at=row["verified_at"],
        created_at=row["created_at"],
    )
