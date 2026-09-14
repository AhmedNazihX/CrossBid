"""Who is calling: the user behind the token, and the company every request is scoped to.

Two modes, and the difference between them is the whole security story.

**`AUTH_MODE=supabase` (S0.3.1, this module's main body).** The browser signs in with a
magic link, Supabase Auth issues a JWT, and every API call carries it as
`Authorization: Bearer …`. FastAPI verifies the signature against Supabase's *public* keys,
published at `{SUPABASE_URL}/auth/v1/.well-known/jwks.json`, reads `sub`, and loads the one
company that user owns (`companies.owner_user_id`, unique). No shared secret is involved:
the backend holds nothing it could leak that would let anyone mint a token.

**`AUTH_MODE=dev` (the bridge).** The caller names the company in an `X-Dev-Company` header
and is believed. That is what let Increments 1-3 run before sign-in existed, and it is why
`settings.py` refuses `AUTH_MODE=dev` together with `ENV=production` — a header is not a
credential. Under `AUTH_MODE=supabase` the header is ignored outright, which is the
story's fourth criterion and the test that pins it.

**Verification is strict by construction, not by care.** The accepted algorithms are the
asymmetric ones only (`ES256`/`RS256`, and this project signs `ES256` — probed live on
2026-09-14). Naming them explicitly is what defeats the two classic JWT attacks: `alg:
none`, and HS256 signed with the public key we ourselves publish as though it were a shared
secret. Issuer and audience are pinned, `exp` and `sub` are required, and every failure
becomes the same 401 carrying no detail about *why* — a verifier that distinguishes "bad
signature" from "expired" for the caller is an oracle.

**A JWKS outage is a 503, never a 401.** Telling a user their token is invalid because
Supabase is unreachable sends them to re-authenticate against a service that is down, and
hides an incident behind what looks like user error.

**Key rotation, without a restart and without a fetch storm.** The key set is cached for
the process. A token naming an unknown `kid` triggers at most one refetch per
`JWKS_REFRESH_FLOOR_SECONDS`; without that floor, a stream of forged `kid`s would be a free
denial-of-service amplifier pointed at Supabase.

**`is_developer` is an email list, not a role.** `DEVELOPER_EMAILS` is compared against the
token's `email` claim, folded and trimmed on both sides. An unset list admits nobody, and a
token with no email is never a developer — both are failures in the closed direction.

`CompanyContext` is the one object routers scope their queries by. It stays tiny on purpose:
tenant isolation is application-level here (ADR-0009), so every `WHERE company_id = …` in
the read model traces back to this value and nothing else.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Final, Protocol

import httpx
import jwt
from fastapi import Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from crossbid.main import get_app_settings, get_database
from crossbid.readmodel.companies import CompaniesReadModel
from crossbid.settings import AuthMode, Settings

DEV_COMPANY_HEADER: Final = "X-Dev-Company"
AUTHORIZATION_HEADER: Final = "Authorization"
BEARER_SCHEME: Final = "bearer"

ACCEPTED_ALGORITHMS: Final = ("ES256", "RS256")
"""Asymmetric only. Listing these is the defence against `alg: none` and HS256 confusion."""

TOKEN_AUDIENCE: Final = "authenticated"  # noqa: S105 - an audience claim, not a secret
"""What Supabase Auth puts in `aud` for a signed-in user."""

JWKS_PATH: Final = "/auth/v1/.well-known/jwks.json"
ISSUER_PATH: Final = "/auth/v1"
JWKS_REFRESH_FLOOR_SECONDS: Final = 60.0
JWKS_TIMEOUT_SECONDS: Final = 5.0

MISSING_DEV_HEADER_DETAIL: Final = (
    f"AUTH_MODE=dev: send the company id in the {DEV_COMPANY_HEADER} header."
)
MALFORMED_DEV_HEADER_DETAIL: Final = f"{DEV_COMPANY_HEADER} must be a UUID."
NOT_AUTHENTICATED_DETAIL: Final = "Sign in: send a Supabase access token as a Bearer token."
AUTH_UNAVAILABLE_DETAIL: Final = (
    "Sign-in is temporarily unavailable: the identity provider could not be reached. "
    "Your token was not rejected — retry shortly."
)
NO_COMPANY_DETAIL: Final = (
    "This account has no company yet. Create one with POST /companies before using the app."
)
NOT_A_DEVELOPER_DETAIL: Final = "This account is not on the developer list."

DEV_USER_ID: Final = "00000000-0000-4000-8000-000000000000"
"""The single synthetic user `AUTH_MODE=dev` acts as.

Dev mode authenticates a *company* by header and knows nothing about users, but
`POST /companies` needs an owner, so one fixed id stands in for the developer at the
keyboard. Deliberately not the company id from the header: `companies.owner_user_id` is
unique, so reusing it would let dev mode create a second company per header value and
quietly diverge from the one-company-per-user rule the product is built on."""


class TokenRejectedError(Exception):
    """The token is not one we issued, or not one we still accept. Becomes a 401."""


class SigningKeysUnavailableError(Exception):
    """The public keys could not be read. Becomes a 503: not the caller's fault."""


class CompanyContext(BaseModel):
    """The tenant a request acts for. Every read-model query is scoped by `company_id`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    company_id: str


class AuthenticatedUser(BaseModel):
    """Who signed in. `is_developer` is decided here, never sent by the client."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    user_id: str
    email: str | None = None
    is_developer: bool = False


# ------------------------------------------------------------------ token verification


class CompanyLookup(Protocol):
    """The one lookup `current_company` makes. A protocol so the dependency can be faked."""

    def company_id_for_owner(
        self, *, owner_user_id: uuid.UUID
    ) -> Awaitable[uuid.UUID | None]: ...


class JwksSource(Protocol):
    """Fetches the JWKS document. A protocol so tests need no socket and no fixture file."""

    def __call__(self) -> Awaitable[Mapping[str, Any]]: ...


class SupabaseTokenVerifier:
    """Verifies a Supabase access token against the project's published public keys."""

    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        jwks: JwksSource,
        refresh_floor_seconds: float = JWKS_REFRESH_FLOOR_SECONDS,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._issuer = issuer
        self._audience = audience
        self._jwks = jwks
        self._refresh_floor = refresh_floor_seconds
        self._now = now
        self._keys: dict[str, jwt.PyJWK] = {}
        self._fetched_at: float | None = None

    async def verify(self, token: str) -> AuthenticatedUser:
        """The user the token stands for.

        Raises `TokenRejectedError` for anything we did not issue or no longer accept, and
        `SigningKeysUnavailableError` when the public keys could not be read at all.
        """
        key = await self._key_for(self._key_id(token))
        claims = self._claims(token, key)
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject.strip():
            raise TokenRejectedError("the token carries no subject")
        return AuthenticatedUser(user_id=subject, email=self._email(claims.get("email")))

    @staticmethod
    def _email(claim: object) -> str | None:
        """Folded and trimmed, because the developer list is compared against it."""
        return claim.strip().casefold() if isinstance(claim, str) and claim.strip() else None

    def _claims(self, token: str, key: jwt.PyJWK) -> Mapping[str, Any]:
        try:
            return jwt.decode(
                token,
                key=key,  # pyright: ignore[reportArgumentType]  (PyJWK is accepted)
                algorithms=list(ACCEPTED_ALGORITHMS),
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "sub", "aud", "iss"]},
            )
        except jwt.PyJWTError as error:
            # Deliberately not `from error`: the cause carries the reason, and the reason
            # is exactly what a caller probing tokens would like to be told.
            raise TokenRejectedError(
                f"the token was not accepted ({type(error).__name__})"
            ) from None

    @staticmethod
    def _key_id(token: str) -> str | None:
        """The `kid` header, without trusting anything else the header says."""
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError:
            raise TokenRejectedError("the token is not a readable JWT") from None
        kid = header.get("kid")
        return kid if isinstance(kid, str) else None

    async def _key_for(self, kid: str | None) -> jwt.PyJWK:
        if self._fetched_at is None:
            await self._refresh()
        key = self._keys.get(kid) if kid is not None else None
        if key is None and self._may_refresh():
            await self._refresh()
            key = self._keys.get(kid) if kid is not None else None
        if key is None:
            raise TokenRejectedError(
                "the token names a signing key this project does not publish"
            )
        return key

    def _may_refresh(self) -> bool:
        """One refetch per floor, so unknown key ids cannot be turned into a fetch storm."""
        return self._fetched_at is None or self._now() - self._fetched_at >= self._refresh_floor

    async def _refresh(self) -> None:
        try:
            document = await self._jwks()
            keys = document["keys"]
            if not isinstance(keys, list):
                raise TypeError(f"`keys` is a {type(keys).__name__}, not a list")
            fetched = {
                str(entry["kid"]): jwt.PyJWK.from_dict(dict(entry))
                for entry in keys
                if isinstance(entry, Mapping) and entry.get("kid")
            }
        except (OSError, httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise SigningKeysUnavailableError(
                f"the signing keys could not be read: {error}"
            ) from error
        self._keys = fetched
        self._fetched_at = self._now()


def jwks_source(
    supabase_url: str, *, transport: httpx.AsyncBaseTransport | None = None
) -> JwksSource:
    """The real fetcher: one short-lived client per fetch, which happens about never.

    `transport` exists so a test can serve the document without a socket; nothing in the
    application passes it.
    """

    async def fetch() -> Mapping[str, Any]:
        async with httpx.AsyncClient(
            timeout=JWKS_TIMEOUT_SECONDS, transport=transport
        ) as client:
            response = await client.get(f"{supabase_url.rstrip('/')}{JWKS_PATH}")
            response.raise_for_status()
            return response.json()

    return fetch


def build_token_verifier(settings: Settings) -> SupabaseTokenVerifier:
    """The verifier for this deployment. `SUPABASE_URL` is required by `AUTH_MODE=supabase`.

    `load_settings` refuses that combination at startup, so the guard below is only
    reachable through a `Settings` object assembled in code — which every test does.
    """
    url = settings.env.supabase_url
    if url is None:
        raise RuntimeError("AUTH_MODE=supabase needs SUPABASE_URL")
    base = url.rstrip("/")
    return SupabaseTokenVerifier(
        issuer=f"{base}{ISSUER_PATH}", audience=TOKEN_AUDIENCE, jwks=jwks_source(base)
    )


# ------------------------------------------------------------------------ dependencies


def get_token_verifier(
    request: Request, settings: Settings = Depends(get_app_settings)
) -> SupabaseTokenVerifier | None:
    """One verifier per app, so the fetched key set is shared by every request.

    `None` under `AUTH_MODE=dev`, and that is not laziness for its own sake: FastAPI
    resolves a dependency before the function that declares it runs, so building one
    eagerly would make every dev-mode request construct a verifier for a Supabase project
    the deployment does not have.
    """
    if settings.env.auth_mode is not AuthMode.SUPABASE:
        return None
    verifier = getattr(request.app.state, "token_verifier", None)
    if verifier is None:
        verifier = build_token_verifier(settings)
        request.app.state.token_verifier = verifier
    return verifier


def get_company_lookup(
    request: Request, settings: Settings = Depends(get_app_settings)
) -> CompanyLookup | None:
    """What `current_company` resolves the tenant with, or `None` under `AUTH_MODE=dev`.

    Mode-aware for the same reason `get_token_verifier` is: FastAPI resolves a dependency
    before the function declaring it runs, so a plain `Depends(get_database)` here would
    demand a connection pool on every dev-mode request — and the dev bridge reads the
    company off a header without touching the database at all. `routers/companies.py`
    keeps its own unconditional provider; this one exists only for the resolution step.
    """
    if settings.env.auth_mode is not AuthMode.SUPABASE:
        return None
    return CompaniesReadModel(get_database(request))


def _bearer_token(request: Request) -> str:
    header = request.headers.get(AUTHORIZATION_HEADER, "")
    scheme, _, token = header.partition(" ")
    if scheme.strip().casefold() != BEARER_SCHEME or not token.strip():
        raise _unauthenticated(NOT_AUTHENTICATED_DETAIL)
    return token.strip()


def _unauthenticated(detail: str) -> HTTPException:
    """401 with the challenge RFC 7235 requires, so a browser knows what is wanted."""
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED, detail=detail, headers={"WWW-Authenticate": "Bearer"}
    )


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


async def current_user(
    request: Request,
    settings: Settings = Depends(get_app_settings),
    verifier: SupabaseTokenVerifier | None = Depends(get_token_verifier),
) -> AuthenticatedUser:
    """FastAPI dependency: the signed-in user, or 401.

    Under `AUTH_MODE=dev` there is no token and so no email; the caller is treated as a
    developer, which is the same door `ENV != production` already opens on `/dev/*`.
    """
    if settings.env.auth_mode is AuthMode.DEV:
        # No token, so no email and no company header required: `/dev/*` is open in dev
        # mode exactly as it was before this story, and `current_company` below is what
        # still demands the header on every tenant-scoped route.
        return AuthenticatedUser(user_id=DEV_USER_ID, is_developer=True)
    assert verifier is not None, "AUTH_MODE=supabase always builds one"
    try:
        user = await verifier.verify(_bearer_token(request))
    except TokenRejectedError as error:
        raise _unauthenticated(NOT_AUTHENTICATED_DETAIL) from error
    except SigningKeysUnavailableError as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail=AUTH_UNAVAILABLE_DETAIL
        ) from error
    return user.model_copy(update={"is_developer": settings.env.is_developer_email(user.email)})


async def current_company(
    request: Request,
    settings: Settings = Depends(get_app_settings),
    user: AuthenticatedUser = Depends(current_user),
    companies: CompanyLookup | None = Depends(get_company_lookup),
) -> CompanyContext:
    """FastAPI dependency: the calling company, or 401 / 404. See the module docstring."""
    if settings.env.auth_mode is AuthMode.DEV:
        return _dev_company(request)
    assert companies is not None, "AUTH_MODE=supabase always builds one"
    company_id = await companies.company_id_for_owner(owner_user_id=uuid.UUID(user.user_id))
    if company_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NO_COMPANY_DETAIL)
    return CompanyContext(company_id=str(company_id))


async def require_developer(
    user: AuthenticatedUser = Depends(current_user),
) -> AuthenticatedUser:
    """FastAPI dependency for `/dev/*`: 403 for anyone not on `DEVELOPER_EMAILS`."""
    if not user.is_developer:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_A_DEVELOPER_DETAIL)
    return user
