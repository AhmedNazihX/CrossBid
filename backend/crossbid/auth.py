"""Who is calling: the company every request is scoped to.

Only the **dev-mode bridge** exists so far (S0.3.1's Notes): with `AUTH_MODE=dev` the caller
names the company in an `X-Dev-Company` header and is believed. That is what lets Increments
1-3 run end to end before magic-link sign-in lands, and it is why `settings.py` refuses
`AUTH_MODE=dev` together with `ENV=production` -- a header is not a credential. Supabase JWT
verification (`AUTH_MODE=supabase`) is S0.3.1 proper; until then that mode answers 501 rather
than pretending, so a misconfigured deployment cannot look authenticated.

`CompanyContext` is the one object routers scope their queries by. It is deliberately tiny:
tenant isolation is application-level here (ADR-0009), so every `WHERE company_id = ...` in
the read model traces back to this value and nothing else.
"""

from __future__ import annotations

import uuid
from typing import Final

from fastapi import Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from crossbid.main import get_app_settings
from crossbid.settings import AuthMode, Settings

DEV_COMPANY_HEADER: Final = "X-Dev-Company"

MISSING_DEV_HEADER_DETAIL: Final = (
    f"AUTH_MODE=dev: send the company id in the {DEV_COMPANY_HEADER} header."
)
MALFORMED_DEV_HEADER_DETAIL: Final = f"{DEV_COMPANY_HEADER} must be a UUID."
SUPABASE_AUTH_NOT_BUILT_DETAIL: Final = (
    "AUTH_MODE=supabase: token verification lands with S0.3.1. Run with AUTH_MODE=dev "
    "outside production."
)


class CompanyContext(BaseModel):
    """The tenant a request acts for. Every read-model query is scoped by `company_id`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    company_id: str


def _dev_company(request: Request) -> CompanyContext:
    header = request.headers.get(DEV_COMPANY_HEADER)
    if header is None or not header.strip():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=MISSING_DEV_HEADER_DETAIL)
    try:
        company_id = uuid.UUID(header.strip())
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail=MALFORMED_DEV_HEADER_DETAIL
        ) from exc
    return CompanyContext(company_id=str(company_id))


async def current_company(
    request: Request, settings: Settings = Depends(get_app_settings)
) -> CompanyContext:
    """FastAPI dependency: the calling company, or 401. See the module docstring."""
    if settings.env.auth_mode is AuthMode.DEV:
        return _dev_company(request)
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail=SUPABASE_AUTH_NOT_BUILT_DETAIL)
