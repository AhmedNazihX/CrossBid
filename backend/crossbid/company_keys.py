"""S5.4, S5.5 — the company's own provider key, and the settings that carry it.

**Every token a bid spends is billed to the key that made the call**, so the key belongs to
the company whose bid it is. This module is the one place a company id becomes a `Settings`
whose `openrouter_api_key` is that company's, and the one place the absence of a key becomes
a sentence rather than a silent charge to somebody else.

`Settings` is the carrier on purpose. `chat_model(role, settings)` and
`EmbeddingsClient(settings)` already take it, at eleven call sites between them, so swapping
one field at the boundary reaches every model call without touching any of them — and a call
site that somehow gets the base settings gets the application key, which is why the enforcing
happens here and at the routes rather than being left to each node's good manners.

The application key keeps exactly one job after this: operator tooling — `make eval`, the
judge, the scripts — which is nobody's bid and nobody's bill but the maintainer's.
"""

from __future__ import annotations

import uuid
from typing import Final

from fastapi import Depends, HTTPException, status

from crossbid.auth import CompanyContext, current_company
from crossbid.db import Database
from crossbid.deps import get_app_settings, get_database
from crossbid.models import Provider
from crossbid.readmodel.provider_keys import ProviderKeysReadModel
from crossbid.settings import Settings

NO_PROVIDER_KEY_DETAIL: Final = (
    "This company has no OpenRouter key saved, so nothing can be run on its behalf. Add a "
    "key on the company profile; it pays for this company's own runs and nobody else's."
)

KEY_UNREADABLE_DETAIL: Final = (
    "The saved OpenRouter key could not be read. Save it again on the company profile."
)


class NoProviderKeyError(RuntimeError):
    """The company has no usable key. Carries a sentence meant for the bidder."""


async def settings_for_company(
    db: Database, base: Settings, *, company_id: str | uuid.UUID
) -> Settings:
    """`base`, with this company's OpenRouter key in place of the application's.

    Raises `NoProviderKeyError` when no key is saved, which is a state to report and not a
    reason to fall back: falling back is how one account ends up paying for another's runs,
    which is the whole reason this exists.
    """
    keys = ProviderKeysReadModel(db, encryption_key=base.env.app_encryption_key)
    record = await keys.get(company_id=uuid.UUID(str(company_id)), provider=Provider.OPENROUTER)
    if record is None:
        raise NoProviderKeyError(NO_PROVIDER_KEY_DETAIL)
    return with_provider_key(base, record.provider_key)


def with_provider_key(base: Settings, provider_key: object) -> Settings:
    """`base` with one field replaced. Frozen models, so this is a copy and not a mutation."""
    env = base.env.model_copy(update={"openrouter_api_key": provider_key})
    return base.model_copy(update={"env": env})


NO_PROVIDER_KEY_STATUS: Final = status.HTTP_402_PAYMENT_REQUIRED
"""402 rather than 403 or 409. The request is well formed, the caller is who they say they
are, and nothing about the company conflicts -- what is missing is the means to pay for the
work, which is the one thing 402 was reserved to say. The browser turns it into a link to the
company profile rather than a shrug.

This lives here rather than in `deps.py` because it needs `current_company`, and `auth.py`
imports `deps.py`: the dependency that resolves a tenant cannot sit in the module the tenant
resolver itself depends on."""


async def get_company_settings(
    company: CompanyContext = Depends(current_company),
    db: Database = Depends(get_database),
    settings: Settings = Depends(get_app_settings),
) -> Settings:
    """The settings every model call on behalf of this company must use (S5.4, S5.5).

    The application key never reaches a bidder's work: a company without its own key is
    refused here, before a document is embedded or a run is started, with a sentence saying
    where to add one. Falling back to the application key is exactly the behaviour this
    dependency exists to remove.
    """
    try:
        return await settings_for_company(db, settings, company_id=company.company_id)
    except NoProviderKeyError as exc:
        raise HTTPException(NO_PROVIDER_KEY_STATUS, detail=str(exc)) from exc
