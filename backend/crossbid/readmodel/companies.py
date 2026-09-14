"""S2.4.1 — the `companies` row: the facts the bidder controls, read and written by one form.

One company per user (settled decision), so there is no list and no id in the path: every
statement here is about the row `auth.current_company` names. The tenant key is therefore the
**primary key** rather than a `company_id` column — `where id = %(company_id)s` — and the
parameter keeps the name it has everywhere else so the predicate reads the same in every read
model. As in `documents.py` and `bids.py` the statements are `Final[LiteralString]` module
constants with the scope already in their text: the API connects as a `BYPASSRLS` role, so
that predicate is the *only* thing between two companies (ADR-0009), and `SCOPED_STATEMENTS`
exists so one test can assert it across all of them. The one exception is `INSERT_COMPANY_SQL`
(S2.4.3), which creates the row instead of filtering rows and so binds the tenant as a value;
`documents.py` already draws that line and the test draws it the same way here.

**Where each field of `CompanyProfile` lives, and why.** The `companies` table already had
both halves before this story — `migrations/0001_init.sql` gives it the five scalar columns
*and* a `profile jsonb not null default '{}'` — so S2.4.1 writes no migration. The split is
not arbitrary:

* **Real columns — `name`, `country`, `legal_form`, `language`, `tone`.** Every one of them is
  something the *database* or another query already depends on. `country` carries a regex
  check, `legal_form` and `tone` carry check constraints whose value lists
  `tests/unit/test_migrations.py` asserts against the Pydantic `StrEnum`s, and `language` is
  read by code that never loads a profile at all: `readmodel/bids.py`'s
  `SELECT_COMPANY_LANGUAGE` joins `c.language` onto every bid to get the bidder language.
  A jsonb copy of any of them would be a second source of truth free to drift from the one
  the constraints police.
* **The `profile` jsonb — `registration_number`, `registration_court`, `staff_fte`,
  `staff_fte_relevant`, `turnover`, `certificates`.** Nothing filters, joins or constrains
  these. Two of them are variable-length lists of objects, which as columns would be two more
  tables and two more migrations, and all of them change shape with the form rather than with
  the schema. `profile jsonb` is the column that exists for exactly this.

`COLUMN_FIELDS` and `JSONB_FIELDS` name the two halves, and a test asserts they partition
`CompanyProfile` exactly — so a field added to the model later cannot be quietly dropped on
the next save; it fails a test until someone decides where it belongs.

The row is **external data**, whatever wrote it: the jsonb is hand-editable in the Supabase
console and older writes may predate a model change. It is therefore re-validated on the way
out, and a row that does not validate raises rather than becoming a half-filled profile.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from typing import Any, Final, LiteralString, Protocol

from psycopg import AsyncConnection
from psycopg.rows import DictRow
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from crossbid.models import CompanyProfile


class CompanyReadModelError(RuntimeError):
    """The row could not be read back as a profile. Never carries a DSN or a secret."""


class ConnectionSource(Protocol):
    """Something that lends a pooled connection; `crossbid.db.Database` satisfies it.

    Restated rather than imported, as in `documents.py`: the read model should not have to
    depend on another read model for a three-line structural type.
    """

    def connection(self) -> AbstractAsyncContextManager[AsyncConnection[DictRow]]: ...


# ----------------------------------------------------------------------- the split

COLUMN_FIELDS: Final[tuple[str, ...]] = ("name", "country", "legal_form", "language", "tone")
"""`CompanyProfile` fields that are real columns. See the module docstring for why."""

JSONB_FIELDS: Final[tuple[str, ...]] = (
    "registration_number",
    "registration_court",
    "staff_fte",
    "staff_fte_relevant",
    "turnover",
    "certificates",
)
"""`CompanyProfile` fields that live in the `profile` jsonb. The two tuples partition the
model; a test asserts it, so a new field has to be placed deliberately."""


# ------------------------------------------------------------------------- statements

SELECT_COMPANY_SQL: Final[LiteralString] = """
select id, name, country, legal_form, language, tone, profile
from companies
where id = %(company_id)s
"""

UPDATE_COMPANY_SQL: Final[LiteralString] = """
update companies
set name = %(name)s,
    country = %(country)s,
    legal_form = %(legal_form)s,
    language = %(language)s,
    tone = %(tone)s,
    profile = %(profile)s,
    updated_at = now()
where id = %(company_id)s
returning id, name, country, legal_form, language, tone, profile
"""
"""A full replacement, matching `PUT /companies/me` (see `routers/companies.py` for why the
form is a PUT). `returning` means the caller answers with what the row says rather than with
what it sent — the two differ whenever Postgres normalises something."""

INSERT_COMPANY_SQL: Final[LiteralString] = """
insert into companies
    (id, owner_user_id, name, country, legal_form, language, tone, profile)
values
    (%(company_id)s, %(owner_user_id)s, %(name)s, %(country)s, %(legal_form)s,
     %(language)s, %(tone)s, %(profile)s)
on conflict (id) do nothing
returning id, name, country, legal_form, language, tone, profile
"""
"""The one statement that *creates* a company, for the S2.4.3 demo seed.

There is no create route and there must not be one: `owner_user_id` is `NOT NULL` and comes
from sign-up, so a company arrives with its owner or not at all — which is why `save` is an
update and answers `None` for a row that does not exist. The seed is the exception the plan
always had, and it brings both ids because it invents the tenant rather than finding it.

`on conflict (id) do nothing` is the whole idempotence mechanism: a second seed inserts
nothing, returns no row, and the caller reads the existing profile instead of racing a
select against an insert. `active_provider` is left to its column default (`openrouter`),
so the one value the seed has no opinion about cannot drift from the schema.

Unlike every statement above it, this one carries no `where`: the tenant is the row being
created, so the scope is the `company_id` *value*. `documents.py`'s insert makes the same
trade for the same reason, and a test pins the binding rather than the predicate."""

SELECT_COMPANY_ID_BY_OWNER_SQL: Final[LiteralString] = """
select id
from companies
where owner_user_id = %(owner_user_id)s
"""
"""The one statement that is *not* scoped by a company, because it is how a company is
found: S0.3.1 turns the `sub` claim of a verified Supabase token into the tenant every other
statement here is then scoped by. `companies_owner_user_id_key` is unique, so this answers at
most one row -- one company per user is a settled decision, and the index is what enforces it
rather than a `limit` written here. It returns the id alone: a caller that wanted the profile
would go on to `get`, and answering with more would invite a route to skip the scope."""

SCOPED_STATEMENTS: Final[tuple[LiteralString, ...]] = (
    SELECT_COMPANY_SQL,
    UPDATE_COMPANY_SQL,
    INSERT_COMPANY_SQL,
    SELECT_COMPANY_ID_BY_OWNER_SQL,
)
"""Every statement in the module. The test asserts the two filtering ones carry the tenant
predicate and that the insert binds the tenant into the row it creates."""

TENANT_PARAMETER: Final = "id = %(company_id)s"
"""What the scope looks like in a `where` clause here: the primary key, bound to the same
parameter name the other read models filter a `company_id` column with."""


# ---------------------------------------------------------------------------- writer


class CompaniesReadModel:
    """Reads and writes one company's row. Create with the process pool.

    The scope argument is keyword-only with no default on every method, so a call that
    forgets the company neither type-checks nor runs.
    """

    def __init__(self, source: ConnectionSource) -> None:
        self._source = source

    async def get(self, *, company_id: uuid.UUID) -> CompanyProfile | None:
        """The company's profile, or `None` when there is no such row.

        `None` covers both "never seeded" and "another company's id"; under `AUTH_MODE=dev`
        the header may name any UUID. The router turns it into 404 — never 403, which would
        confirm that the id exists (S2.2.2's reasoning).
        """
        row = await self._fetch_one(SELECT_COMPANY_SQL, {"company_id": company_id})
        return None if row is None else _profile(row)

    async def company_id_for_owner(self, *, owner_user_id: uuid.UUID) -> uuid.UUID | None:
        """The company this user owns, or `None` when they have not created one yet.

        The one lookup that takes a *user* rather than a company: S0.3.1's `current_company`
        resolves the tenant with it, and every other method here is scoped by what it
        answers. `None` is the not-onboarded case and becomes a 404 pointing at
        `POST /companies`, never a 403 -- there is nothing here to be forbidden from.
        """
        row = await self._fetch_one(
            SELECT_COMPANY_ID_BY_OWNER_SQL, {"owner_user_id": owner_user_id}
        )
        return None if row is None else uuid.UUID(str(row["id"]))

    async def create(
        self, *, company_id: uuid.UUID, owner_user_id: uuid.UUID, profile: CompanyProfile
    ) -> CompanyProfile | None:
        """Insert the company, or answer `None` because it is already there (S2.4.3).

        `None` is not a failure here and must not be treated as one: it is how
        `on conflict (id) do nothing` says "a second run", which is exactly what the seed
        wants to hear. The caller then reads the row and decides whether it still matches.
        """
        row = await self._fetch_one(
            INSERT_COMPANY_SQL,
            {
                "company_id": company_id,
                "owner_user_id": owner_user_id,
                **{field: _column_value(profile, field) for field in COLUMN_FIELDS},
                "profile": Jsonb(profile_document(profile)),
            },
        )
        return None if row is None else _profile(row)

    async def save(
        self, *, company_id: uuid.UUID, profile: CompanyProfile
    ) -> CompanyProfile | None:
        """Replace the profile and return the row as it now reads, or `None` for no such row.

        This never creates a company: `owner_user_id` is `NOT NULL` and comes from sign-up,
        so an unseeded id is a 404 and not an upsert. `create` above is the one insert, and
        only the S2.4.3 seed reaches it — no route does.
        """
        row = await self._fetch_one(
            UPDATE_COMPANY_SQL,
            {
                "company_id": company_id,
                **{field: _column_value(profile, field) for field in COLUMN_FIELDS},
                "profile": Jsonb(profile_document(profile)),
            },
        )
        return None if row is None else _profile(row)

    async def _fetch_one(
        self, sql: LiteralString, params: Mapping[str, Any]
    ) -> Mapping[str, Any] | None:
        async with self._source.connection() as connection:
            cursor = await connection.execute(sql, params)
            return await cursor.fetchone()


# ----------------------------------------------------------------------------- helpers


def profile_document(profile: CompanyProfile) -> dict[str, Any]:
    """The `profile` jsonb payload: the non-column fields, as JSON.

    `mode="json"` because the destination is jsonb — dates become ISO strings and enums
    their values, which is what comes back out of Postgres and what `CompanyProfile` parses
    again. The column fields are excluded rather than merely ignored on the way back in, so
    the jsonb never holds a copy that could disagree with its column.
    """
    return profile.model_dump(mode="json", include=set(JSONB_FIELDS))


def _column_value(profile: CompanyProfile, field: str) -> str:
    """One scalar column's value as `text`.

    All five are `str` or a `StrEnum` of `str`, and `str()` on a `StrEnum` is its value —
    `'gmbh'`, which is what `companies_legal_form_check` accepts. Binding the enum member
    itself would leave psycopg to find a dumper for a `str` subclass; this does not depend
    on that.
    """
    return str(getattr(profile, field))


def _profile(row: Mapping[str, Any]) -> CompanyProfile:
    """One `dict_row` as a `CompanyProfile`, or a loud failure — never a half-filled profile.

    The columns are applied over the jsonb, so a stale copy in the document cannot win over
    the column the check constraints police. Anything the model refuses — an unknown key
    (`CompanyProfile` forbids extras), a value outside its bounds, a `profile` that is not a
    JSON object at all — is drift between this module and the table, and says so.
    """
    document = row["profile"]
    try:
        return CompanyProfile.model_validate(
            {**document, **{field: row[field] for field in COLUMN_FIELDS}}
        )
    except (ValidationError, TypeError, ValueError) as err:
        raise CompanyReadModelError(
            f"A companies row has an unexpected shape: {err}. The read model and the table "
            "have drifted apart; re-check migrations/0001_init.sql and what last wrote the "
            "profile jsonb."
        ) from err
