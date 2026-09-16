"""LLM providers a company's bids can run through.

Default is the app's own OpenRouter route, and in this build it is the only one: `usage.py`
stamps `Provider.OPENROUTER` on every recorded call because nothing else buys tokens yet.

A company storing its own key is stories S5.4-S5.6, Increment 6, stretch: encrypted at rest
with Fernet, scoped by company, verified with a one-token call on save, and **never returned
to the client** -- only a last-4 hint leaves the server.

**The models for that flow used to live here and were removed on 2026-09-16.**
`ProviderKeyStatus`, `ProviderSelection` and `KEY_HINT_LENGTH` were written ahead of the
stories, reached no route, appeared in no OpenAPI schema, and were exercised only by the test
that walks `models.__all__`. A type nothing produces is a type nothing keeps honest: it drifts
from the flow it was written for, and the next reader cannot tell a contract from a sketch.
They come back with S5.4, shaped by whatever `provider_keys` actually needs then. A
`ModelRole` also lived here, a four-member copy of the five-member one in `settings.py` --
missing `FALLBACK`, which S3.4.4 depends on -- and a natural `from crossbid.models import
ModelRole` would silently have got the wrong one. `crossbid.settings.ModelRole` is the one.

Note from ADR-0005: a company on its own key bypasses this account's OpenRouter data-policy
guardrails, so the models available to it are *wider* than the app's defaults. The provider UI
must not assume the app's verified model list applies.
"""

from __future__ import annotations

from enum import StrEnum


class Provider(StrEnum):
    """Where the tokens are bought."""

    OPENROUTER = "openrouter"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
