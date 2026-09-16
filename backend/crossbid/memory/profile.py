"""`profile/{company_id}` — where the agent reads the bidder's own facts.

The `companies` row is the source of truth; this namespace is the agent's copy of it, so
`check_reqs` reasons about the same turnover, headcount and certificates the form answers
with. The whole profile is **one item** under the namespace rather than a key per field: the
agent reads the facts as a unit, and one `aput` makes a save atomic from its point of view.

The three names lived in `routers/companies.py` while the save path (S2.4.1) was the only
writer. S2.4.3's demo seed is the second: it writes the same item with no HTTP request in
sight, because a company seeded into Postgres alone is half-seeded — the agent would find no
memory of it. A seeding module importing a router to learn an address would be an import
pointing the wrong way (`docs/project-plan.md`, Repository layout), so the address moved down
to the layer the plan already reserves for it and both writers now point at one definition.

This module is the address **and the read** (ADR-0077). Who writes it, and what happens when
the write fails, still belongs to the caller: the router answers 200 with a warning, the seed
reports it. What lives here is the one thing that makes the namespace memory rather than a
copy nobody opens — `RememberedProfile`, which `plan_checks` and `score_verdict` are built
over.
"""

from __future__ import annotations

import logging
import uuid
from typing import Final, Protocol

from langgraph.store.base import BaseStore
from pydantic import ValidationError

from crossbid.models.company import CompanyProfile

logger = logging.getLogger(__name__)

PROFILE_NAMESPACE_PREFIX: Final = "profile"
"""The namespace's first segment; `db.py` writes the whole as `profile/{company_id}`."""

PROFILE_STORE_KEY: Final = "company"
"""The one item's key. See the module docstring for why the profile is not split by field."""


def profile_namespace(company_id: uuid.UUID) -> tuple[str, str]:
    """`profile/{company_id}` as LangGraph spells a namespace. One definition, every side."""
    return (PROFILE_NAMESPACE_PREFIX, str(company_id))


class ProfileSource(Protocol):
    """The slice of `readmodel.companies.CompaniesReadModel` the memory reads behind itself."""

    async def get(self, *, company_id: uuid.UUID) -> CompanyProfile | None: ...


class RememberedProfile:
    """The bidder's facts as the agent remembers them, with the row standing behind it.

    Satisfies `check_reqs.CompanyLookup`, so the two nodes that want the bidder read their own
    memory and are otherwise unchanged. The order is memory first, row second, and it is that
    way round on purpose: reading the row first would make the namespace a write nobody opens,
    which is the finding this class closes.

    **The row is still the source of truth, and three things keep the memory honest about it.**
    Every save rewrites the item; a save whose Store write fails *deletes* the item rather than
    leaving yesterday's figures behind it (`routers/companies.py`); and a namespace with
    nothing in it is answered from the row and repaired on the way out, which is what every
    company saved before ADR-0077 gets on its first bid.

    **Nothing here fails a run that the row could have answered.** A Store that cannot be read,
    an item written by an older build that no longer validates, a repair that cannot be
    written — each is a warning in the log and a fall through to the row. What is *not* caught
    is the row failing: `plan_checks` and `score_verdict` each decide for themselves what
    survives that, and a memory that swallowed it would check a pack against a bidder from
    nowhere.
    """

    def __init__(self, store: BaseStore, row: ProfileSource) -> None:
        self._store = store
        self._row = row

    async def get(self, *, company_id: uuid.UUID) -> CompanyProfile | None:
        """What the agent knows about this bidder, from memory or from the row behind it."""
        remembered = await self._recall(company_id)
        if remembered is not None:
            return remembered
        profile = await self._row.get(company_id=company_id)
        if profile is not None:
            await self._remember(company_id, profile)
        return profile

    async def _recall(self, company_id: uuid.UUID) -> CompanyProfile | None:
        """The stored item, or `None` and a line in the log saying which way it went wrong."""
        try:
            item = await self._store.aget(profile_namespace(company_id), PROFILE_STORE_KEY)
        except Exception as exc:
            logger.warning(
                "The agent's memory of company %s could not be read (%s); using the row",
                company_id,
                type(exc).__name__,
            )
            return None
        if item is None:
            return None
        try:
            return CompanyProfile.model_validate(item.value)
        except ValidationError:
            logger.warning(
                "The agent's memory of company %s no longer validates; using the row",
                company_id,
            )
            return None

    async def _remember(self, company_id: uuid.UUID, profile: CompanyProfile) -> None:
        """Write the row's answer back, in the one shape every writer of this item uses.

        `logger.warning`, not `exception`: unlike the router's write, nobody is waiting to be
        told to retry — the caller already has its answer and the next bid tries again.
        """
        try:
            await self._store.aput(
                profile_namespace(company_id),
                PROFILE_STORE_KEY,
                profile.model_dump(mode="json"),
            )
        except Exception as exc:
            logger.warning(
                "The agent's memory of company %s could not be repaired (%s)",
                company_id,
                type(exc).__name__,
            )
