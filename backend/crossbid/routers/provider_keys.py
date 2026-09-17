"""S5.4, S4.6.4 — `/companies/me/provider-key`: the bidder's own OpenRouter key.

**Why a company must have one.** Every token a bid spends is billed to the key that made the
call. A shared application key means one account paying for everyone's runs, and it is how
this project spent a session debugging a $25 cap that belonged to somebody else's work
(ADR-0087, ADR-0090). The key lives on the company, the bill follows the company, and the
application key is left to operator tooling — `make eval`, the judge, the scripts — which is
not anybody's bid.

**The key is verified before it is stored, and stored sealed.** A refused key is never
written, so a typo is caught in the form rather than four minutes into a run. What comes back
is never the key: the last four characters, when it was verified, and when it was saved.

**PUT replaces.** `primary key (company_id, provider)` means pasting a new key leaves one key
and no question about which is in force. DELETE removes it, and a company with no key cannot
run a bid or upload a document — deliberately, see `deps.company_settings`.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Final

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from crossbid.auth import CompanyContext, current_company
from crossbid.crypto import CryptoError
from crossbid.db import Database
from crossbid.deps import get_app_settings, get_database
from crossbid.models import Provider
from crossbid.provider_verification import VerificationError, verify
from crossbid.readmodel.provider_keys import ProviderKeysReadModel, SavedProviderKey
from crossbid.settings import Settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/companies/me/provider-key", tags=["provider keys"])

NO_KEY_SAVED_DETAIL: Final = "No provider key is saved for this company."
KEY_EXHAUSTED_DETAIL: Final = (
    "OpenRouter accepted this key, but it has no spending left on it. Raise the key's limit "
    "or add credit, then save it again."
)


class SaveProviderKeyRequest(BaseModel):
    """The key itself, write-only: no route ever sends it back."""

    model_config = ConfigDict(extra="forbid")

    provider: Provider = Field(
        default=Provider.OPENROUTER,
        description=(
            "Which provider the key is for. Only `openrouter` can be used today: every "
            "model this app is configured with is an OpenRouter slug."
        ),
    )
    provider_key: str = Field(
        min_length=8,
        description="The API key, sent once. It is sealed before it reaches the database.",
    )


class ProviderKeyResponse(BaseModel):
    """What a bidder may see of their own key."""

    model_config = ConfigDict(frozen=True)

    provider: Provider = Field(description="Which provider this key is for")
    key_hint: str = Field(description="The last four characters, so the bidder knows which key")
    verified_at: datetime | None = Field(
        description="When the provider last confirmed the key; null if it was never checked"
    )
    created_at: datetime = Field(description="When the key was saved")
    label: str | None = Field(
        default=None,
        description="The provider's own name for the key, as it reported on verification",
    )

    @classmethod
    def of(cls, saved: SavedProviderKey, *, label: str | None = None) -> ProviderKeyResponse:
        return cls(
            provider=saved.provider,
            key_hint=saved.key_hint,
            verified_at=saved.verified_at,
            created_at=saved.created_at,
            label=label,
        )


def get_provider_keys(
    db: Database = Depends(get_database), settings: Settings = Depends(get_app_settings)
) -> ProviderKeysReadModel:
    return ProviderKeysReadModel(db, encryption_key=settings.env.app_encryption_key)


@router.put("", response_model=ProviderKeyResponse, summary="Save this company's provider key")
async def save_provider_key(
    body: SaveProviderKeyRequest,
    company: CompanyContext = Depends(current_company),
    keys: ProviderKeysReadModel = Depends(get_provider_keys),
) -> ProviderKeyResponse:
    """Verify the key with the provider, then store it sealed. A refused key is not stored."""
    try:
        verified = await verify(body.provider, body.provider_key)
    except VerificationError as exc:
        # The message is the provider's judgement in our words; it never carries the key.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if verified.is_exhausted:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=KEY_EXHAUSTED_DETAIL)

    try:
        saved = await keys.save(
            company_id=uuid.UUID(company.company_id),
            provider=body.provider,
            provider_key=body.provider_key,
            verified_at=datetime.now(UTC),
        )
    except CryptoError as exc:
        logger.error("a provider key could not be sealed: %s", exc)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    return ProviderKeyResponse.of(saved, label=verified.label)


@router.get("", response_model=ProviderKeyResponse, summary="What key is saved")
async def read_provider_key(
    provider: Provider = Provider.OPENROUTER,
    company: CompanyContext = Depends(current_company),
    keys: ProviderKeysReadModel = Depends(get_provider_keys),
) -> ProviderKeyResponse:
    """The hint and the dates. Never the key — there is no route that returns it."""
    saved = await keys.saved(company_id=uuid.UUID(company.company_id), provider=provider)
    if saved is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NO_KEY_SAVED_DETAIL)
    return ProviderKeyResponse.of(saved)


@router.delete(
    "", status_code=status.HTTP_204_NO_CONTENT, summary="Remove this company's provider key"
)
async def delete_provider_key(
    provider: Provider = Provider.OPENROUTER,
    company: CompanyContext = Depends(current_company),
    keys: ProviderKeysReadModel = Depends(get_provider_keys),
) -> Response:
    """Removing the key stops this company's bids and uploads until another one is saved."""
    removed = await keys.delete(company_id=uuid.UUID(company.company_id), provider=provider)
    if not removed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NO_KEY_SAVED_DETAIL)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
