"""LLM providers a company's bids can run through.

Default is the app's own OpenRouter route. A company may instead store its own key — stories
S5.4-S5.6, Increment 6, stretch — in which case the key is encrypted at rest with Fernet,
scoped by company, verified with a one-token call on save, and **never returned to the client**:
only a last-4 hint leaves the server.

Note from ADR-0005: a company on its own key bypasses this account's OpenRouter data-policy
guardrails, so the models available to it are *wider* than the app's defaults. The provider UI
must not assume the app's verified model list applies.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

KEY_HINT_LENGTH = 4


class Provider(StrEnum):
    """Where the tokens are bought."""

    OPENROUTER = "openrouter"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class ModelRole(StrEnum):
    """What a configured slug is for. Slugs live in settings.default.yaml, never in code."""

    EXTRACT = "extract"
    CHEAP = "cheap"
    EMBED = "embed"
    JUDGE = "judge"


class ProviderKeyStatus(BaseModel):
    """What the client is allowed to know about a stored key. Never the key itself."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: Provider
    key_hint: str = Field(
        min_length=KEY_HINT_LENGTH,
        max_length=KEY_HINT_LENGTH,
        description="Last 4 characters only, so a user can tell which key is stored",
    )
    verified_at: datetime | None = Field(
        default=None, description="When the one-token verification call last succeeded"
    )


class ProviderSelection(BaseModel):
    """Which provider a company's bids currently run through."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    active: Provider = Field(
        default=Provider.OPENROUTER,
        description="OPENROUTER means the app's own route unless the company stored a key",
    )
    uses_own_key: bool = Field(
        default=False, description="False means the app's shared OpenRouter route"
    )
    configured: tuple[ProviderKeyStatus, ...] = ()
