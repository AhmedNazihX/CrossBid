"""S2.4.1 — `GET /companies/me` and `PUT /companies/me`: the facts the bidder controls.

One company per user (settled decision), so the path is `/companies/me` and there is no id in
it: the tenant comes from `auth.current_company` and nothing else. There is no create route —
`companies.owner_user_id` is `NOT NULL` and comes from sign-up (or, today, from
`scripts/seed_dev_company.py`) — so a company with no row answers **404**, never 403, for the
same reason `documents.py` gives: a "forbidden" would confirm that the id exists.

**PUT, not PATCH.** S4.2.1 is a single form that loads the whole profile, lets the bidder edit
any part of it and saves it in one submit, so the request always carries every field and a
full replacement is what actually happens. PATCH would have to answer two questions this
story has no good answer to: on `turnover` and `certificates` — both lists — does a merge
replace the list, append to it, or match by some key the model has no id for? And with every
optional field defaulting to `None`, "absent" and "clear this field" are indistinguishable
without a sentinel the generated TypeScript client could not express either. PUT is idempotent
as well, which is what makes the retry described below safe.

**Two writes, and what happens when the second fails.** The row is written first and is the
source of truth; the LangGraph Store namespace `profile/{company_id}` is the agent's copy of
it (brief Medium 2 — long-term memory), so `check_reqs` reasons about the same facts the API
answers with. The namespace itself is `memory/profile.py`'s, not this module's: S2.4.3's demo
seed writes the same item with no request behind it, and one address serves both writers.

If the Store write fails the row is already saved, so the answer is **200 with
`warning` set** rather than a 5xx: reporting failure for a write that landed is the worse lie,
and a bidder told "save failed" would reasonably assume their facts were lost. The warning
carries the partial failure instead — a typed, described field on the response, so S4.2.1 can
render it, and `None` on the happy path so a client can treat "present" as "something needs
attention". The underlying error is logged with the company id and never reaches the browser.
Because PUT is idempotent, repeating the save rewrites the same row and retries the memory
write; there is nothing to undo and nothing to duplicate, which is what the warning asks for.

**Expiry is derived, never stored.** `CompanyProfile` is frozen and the repo forbids in-place
mutation, so the flag lives on a response model built from the profile:
`CertificateHeld.is_valid_on` is the one definition of validity, and `checked_on` says which
day the answer is about. "Today" arrives through the `get_today` dependency so tests state the
date they mean instead of depending on the day they run.

Response fields all carry a description: `frontend/lib/api.ts` is generated from this schema.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime
from typing import Final

from fastapi import APIRouter, Depends, HTTPException, status
from langgraph.store.base import BaseStore
from pydantic import BaseModel, ConfigDict, Field

from crossbid.auth import AuthenticatedUser, CompanyContext, current_company, current_user
from crossbid.db import Database
from crossbid.main import get_database
from crossbid.memory.profile import PROFILE_STORE_KEY, profile_namespace
from crossbid.models import CertificateHeld, CompanyProfile, LegalForm, Tone, TurnoverYear
from crossbid.readmodel.companies import CompaniesReadModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/companies", tags=["companies"])

NO_SUCH_COMPANY_DETAIL: Final = "No such company."
ALREADY_HAS_A_COMPANY_DETAIL: Final = (
    "This account already has a company. Change it with PUT /companies/me."
)
"""One company per user is enforced by `companies_owner_user_id_key`, so a second create is
a 409 rather than a second row. The message names the route that does what they meant."""
MEMORY_NOT_UPDATED_WARNING: Final = (
    "Your profile was saved, but the agent's memory of it could not be updated. Save again "
    "before you start a bid, so the agent checks requirements against these facts."
)
"""The `warning` on an otherwise successful save. A sentence the bidder can act on, and it
says *when* it matters — the stale memory only bites once a bid runs."""

# ----------------------------------------------------------------------- response models


class CertificateResponse(BaseModel):
    """One certificate the company holds, with the expiry flags the form shows beside it."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="e.g. 'ISO/IEC 27001:2022'")
    issuer: str | None = Field(description="Who issued it, if recorded")
    number: str | None = Field(description="The certificate number, if recorded")
    issued_on: date | None = Field(description="When it was issued, if recorded")
    expires_on: date | None = Field(description="When it expires; null when not recorded")
    scope: str | None = Field(description="What the certificate actually covers")
    is_expired: bool = Field(
        description="The recorded expiry is before checked_on — this is no longer evidence"
    )
    is_valid: bool = Field(
        description=(
            "Valid on checked_on. False when no expiry is recorded: without a date the "
            "profile cannot claim validity, which is not the same as being expired"
        )
    )

    @classmethod
    def flagged(cls, held: CertificateHeld, *, today: date) -> CertificateResponse:
        """The held certificate plus the two flags, computed against one day."""
        return cls(
            **held.model_dump(),
            is_expired=held.is_expired_on(today),
            is_valid=held.is_valid_on(today),
        )


class CompanyProfileResponse(BaseModel):
    """The calling company's profile as the form reads it back, expiry already checked."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Legal name, as it appears on the register")
    country: str = Field(description="ISO 3166-1 alpha-2, lowercase — where the bidder is")
    legal_form: LegalForm = Field(description="Legal form; 'other' when none of them fits")
    registration_number: str | None = Field(description="e.g. 'HRB 84512'")
    registration_court: str | None = Field(description="The register the number belongs to")
    language: str = Field(description="BCP 47; requirements are explained in this language")
    tone: Tone = Field(description="How explanations are written")
    staff_fte: float | None = Field(description="Total full-time equivalents")
    staff_fte_relevant: float | None = Field(
        description="FTE in the field of the contract, which is what tenders ask for"
    )
    turnover: list[TurnoverYear] = Field(
        description="Turnover per fiscal year in the field of the contract"
    )
    certificates: list[CertificateResponse] = Field(
        description="Certificates held, each flagged against checked_on"
    )
    has_expired_certificates: bool = Field(
        description="At least one certificate has expired; the form warns about it"
    )
    checked_on: date = Field(description="The day the expiry flags were computed for, UTC")
    warning: str | None = Field(
        default=None,
        description=(
            "Null unless a save only partly succeeded. Set when the profile was stored but "
            "the agent's memory of it was not: the facts above are saved, and saving again "
            "repairs the rest. A read never sets it"
        ),
    )

    @classmethod
    def flagged(
        cls, profile: CompanyProfile, *, today: date, warning: str | None = None
    ) -> CompanyProfileResponse:
        """Derive the response from a frozen profile; nothing about the profile is changed."""
        certificates = [
            CertificateResponse.flagged(held, today=today) for held in profile.certificates
        ]
        return cls(
            **profile.model_dump(exclude={"certificates"}),
            certificates=certificates,
            has_expired_certificates=any(held.is_expired for held in certificates),
            checked_on=today,
            warning=warning,
        )


# ------------------------------------------------------------------------- dependencies


def get_company_records(db: Database = Depends(get_database)) -> CompaniesReadModel:
    """The `companies` reader and writer on the process pool. Overridden in tests."""
    return CompaniesReadModel(db)


def get_profile_store(db: Database = Depends(get_database)) -> BaseStore:
    """LangGraph's long-term memory, where `profile/{company_id}` is written on save."""
    return db.store


def get_today() -> date:
    """The day expiries are judged against. A dependency so tests are not time-dependent.

    UTC rather than a local zone: the server has no business guessing the bidder's, and a
    certificate's expiry is a date on a piece of paper, not a moment.
    """
    return datetime.now(UTC).date()


# ------------------------------------------------------------------------------- routes


@router.post(
    "",
    response_model=CompanyProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create the calling user's company",
)
async def post_company(
    profile: CompanyProfile,
    user: AuthenticatedUser = Depends(current_user),
    records: CompaniesReadModel = Depends(get_company_records),
    today: date = Depends(get_today),
) -> CompanyProfileResponse:
    """Onboarding: the first thing a newly signed-in bidder does (S0.3.1, S4.2.1).

    This is the only route that takes `current_user` rather than `current_company`, and it
    has to: a user with no company cannot be scoped to one, so every other route answers
    404 until this has run. The owner comes from the verified token and never from the
    body — a client that could name the owner could create a company for somebody else.
    """
    owner = uuid.UUID(user.user_id)
    if await records.company_id_for_owner(owner_user_id=owner) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=ALREADY_HAS_A_COMPANY_DETAIL)
    created = await records.create(
        company_id=uuid.uuid4(), owner_user_id=owner, profile=profile
    )
    if created is None:  # pragma: no cover - a fresh uuid4 cannot collide
        raise HTTPException(status.HTTP_409_CONFLICT, detail=ALREADY_HAS_A_COMPANY_DETAIL)
    logger.info("Company created for user %s", owner)
    return CompanyProfileResponse.flagged(created, today=today)


@router.get(
    "/me",
    response_model=CompanyProfileResponse,
    summary="The calling company's profile",
)
async def get_company_profile(
    company: CompanyContext = Depends(current_company),
    records: CompaniesReadModel = Depends(get_company_records),
    today: date = Depends(get_today),
) -> CompanyProfileResponse:
    """The facts the matrix checks a tender against. A company with no row answers 404."""
    profile = await records.get(company_id=_company_uuid(company))
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NO_SUCH_COMPANY_DETAIL)
    return CompanyProfileResponse.flagged(profile, today=today)


@router.put(
    "/me",
    response_model=CompanyProfileResponse,
    summary="Replace the calling company's profile",
)
async def put_company_profile(
    profile: CompanyProfile,
    company: CompanyContext = Depends(current_company),
    records: CompaniesReadModel = Depends(get_company_records),
    store: BaseStore = Depends(get_profile_store),
    today: date = Depends(get_today),
) -> CompanyProfileResponse:
    """Save the whole profile, then write it to the agent's memory.

    The row is the source of truth and is written first, so a memory write that fails leaves
    a genuinely saved profile: that answers 200 with `warning` set, not a 5xx. A company with
    no row is the only 404 here.

    The body is the domain model itself, so an unknown field or one outside its bounds is
    FastAPI's own 422 and names the field — which is what S4.2.1 puts under the input.
    """
    company_id = _company_uuid(company)
    saved = await records.save(company_id=company_id, profile=profile)
    if saved is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NO_SUCH_COMPANY_DETAIL)
    warning = await _remember(store, company_id=company_id, profile=saved)
    logger.info("Profile saved for company %s", company_id)
    return CompanyProfileResponse.flagged(saved, today=today, warning=warning)


# ------------------------------------------------------------------------------ helpers


def _company_uuid(company: CompanyContext) -> uuid.UUID:
    """`CompanyContext.company_id` is a string by contract; the read model binds UUIDs."""
    return uuid.UUID(company.company_id)


async def _remember(
    store: BaseStore, *, company_id: uuid.UUID, profile: CompanyProfile
) -> str | None:
    """Project the saved row into `profile/{company_id}`, or say why it could not be.

    The whole profile goes in, column fields included: the Store is what the agent reads, and
    it should not have to join two sources to learn the bidder's country.

    Returns the warning for the response on failure — `None` when the write landed. The
    failure is *not* swallowed: it is logged with the company id and the underlying error, and
    the caller surfaces it to the bidder. What it is not is a failed request, because the row
    it is a copy of was written (see the module docstring).

    **A failed write forgets the item rather than leaving the old one behind it.** Since
    ADR-0077 the agent reads this namespace, so an item that still holds yesterday's headcount
    is worse than no item at all: the next bid would be checked against the superseded figure
    and nothing on screen would say so. `RememberedProfile` answers a missing item from the
    row, so deleting turns a silent wrong answer into a slightly slower right one. A delete
    that fails too is the same one warning — the bidder is already being told to retry, and
    the retry rewrites the item outright.

    `logger.exception`, not `logger.error`: the bidder is told to retry, so a failure that
    keeps happening will be diagnosed from this line and nothing else. The message alone
    ("connection pool exhausted") does not say which of the Store's calls raised it.
    """
    try:
        await store.aput(
            profile_namespace(company_id), PROFILE_STORE_KEY, profile.model_dump(mode="json")
        )
    except Exception as exc:
        logger.exception(
            "profile for company %s was saved but not written to the Store: %s", company_id, exc
        )
        await _forget(store, company_id=company_id)
        return MEMORY_NOT_UPDATED_WARNING
    return None


async def _forget(store: BaseStore, *, company_id: uuid.UUID) -> None:
    """Drop the stale item so the agent falls back to the row. Never raises; see `_remember`."""
    try:
        await store.adelete(profile_namespace(company_id), PROFILE_STORE_KEY)
    except Exception as exc:
        logger.warning(
            "the agent's superseded memory of company %s could not be dropped either (%s)",
            company_id,
            type(exc).__name__,
        )
