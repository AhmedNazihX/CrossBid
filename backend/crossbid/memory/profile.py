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

This module is the address and nothing else. Who writes it, and what happens when the write
fails, belongs to the caller: the router answers 200 with a warning, the seed reports it.
"""

from __future__ import annotations

import uuid
from typing import Final

PROFILE_NAMESPACE_PREFIX: Final = "profile"
"""The namespace's first segment; `db.py` writes the whole as `profile/{company_id}`."""

PROFILE_STORE_KEY: Final = "company"
"""The one item's key. See the module docstring for why the profile is not split by field."""


def profile_namespace(company_id: uuid.UUID) -> tuple[str, str]:
    """`profile/{company_id}` as LangGraph spells a namespace. One definition, every side."""
    return (PROFILE_NAMESPACE_PREFIX, str(company_id))
