"""S0.3.1 — verifying a Supabase magic-link token, and what it resolves to.

Offline. Supabase signs this project's tokens with **ES256** and publishes the public half
at `{SUPABASE_URL}/auth/v1/.well-known/jwks.json` (probed live 2026-09-14), so every test
here mints its own EC keypair and serves its own JWKS through a fake fetcher. Nothing
opens a socket, and no test needs a real Supabase session.

The attacks are the point. A verifier that accepts a well-formed token is trivial; the
value is in what it refuses — another key's signature, `alg: none`, an HS256 token signed
with the public key as the shared secret, another project's issuer, an expired token, and
a token with no subject. Each of those is a test below, because each of them is a real
published attack on JWT verification rather than a hypothetical.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from collections.abc import Iterator, Mapping
from types import SimpleNamespace
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from crossbid.auth import (
    AuthenticatedUser,
    CompanyContext,
    SigningKeysUnavailableError,
    SupabaseTokenVerifier,
    TokenRejectedError,
    build_token_verifier,
    current_company,
    current_user,
    get_company_lookup,
    get_token_verifier,
    jwks_source,
    require_developer,
)
from crossbid.main import create_app
from crossbid.readmodel.companies import CompaniesReadModel
from crossbid.settings import AuthMode, Settings

pytestmark = pytest.mark.anyio
"""Applies to the async tests below; the `TestClient` ones ignore it."""

ISSUER = "https://project.supabase.co/auth/v1"
AUDIENCE = "authenticated"
USER_ID = str(uuid.uuid4())
COMPANY_ID = str(uuid.uuid4())
EMAIL = "sabine@example-it.de"
DEVELOPER_EMAIL = "ahmed@example.dev"


# ------------------------------------------------------------------- keys and tokens


class Signer:
    """One EC keypair, its JWKS entry, and tokens signed with it."""

    def __init__(self, kid: str) -> None:
        self.kid = kid
        self._key = ec.generate_private_key(ec.SECP256R1())

    @property
    def jwk(self) -> dict[str, Any]:
        entry = jwt.algorithms.ECAlgorithm.to_jwk(self._key.public_key(), as_dict=True)
        return {**entry, "kid": self.kid, "use": "sig", "alg": "ES256"}

    @property
    def public_pem(self) -> str:
        from cryptography.hazmat.primitives import serialization

        return (
            self._key.public_key()
            .public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode()
        )

    def token(self, **overrides: Any) -> str:
        claims: dict[str, Any] = {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": USER_ID,
            "email": EMAIL,
            "role": "authenticated",
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()) - 5,
        }
        claims.update(overrides)
        for name, value in list(claims.items()):
            if value is None:
                del claims[name]
        return jwt.encode(claims, self._key, algorithm="ES256", headers={"kid": self.kid})


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _hs256_with(secret: str, *, kid: str) -> str:
    """A token whose `alg` claims HMAC, keyed on the public key an attacker can read."""
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT", "kid": kid}).encode())
    payload = _b64(
        json.dumps(
            {"iss": ISSUER, "aud": AUDIENCE, "sub": USER_ID, "exp": int(time.time()) + 60}
        ).encode()
    )
    signing_input = f"{header}.{payload}".encode()
    signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64(signature)}"


class FakeJwks:
    """A JWKS document that can change between fetches, counting every fetch."""

    def __init__(self, *signers: Signer) -> None:
        self.signers = list(signers)
        self.calls = 0
        self.error: Exception | None = None

    async def __call__(self) -> Mapping[str, Any]:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return {"keys": [signer.jwk for signer in self.signers]}


@pytest.fixture
def signer() -> Signer:
    return Signer("key-one")


@pytest.fixture
def jwks(signer: Signer) -> FakeJwks:
    return FakeJwks(signer)


@pytest.fixture
def verifier(jwks: FakeJwks) -> SupabaseTokenVerifier:
    return SupabaseTokenVerifier(issuer=ISSUER, audience=AUDIENCE, jwks=jwks)


# --------------------------------------------------------------- what it accepts


async def test_a_valid_token_resolves_to_its_user(
    verifier: SupabaseTokenVerifier, signer: Signer
) -> None:
    user = await verifier.verify(signer.token())

    assert user == AuthenticatedUser(user_id=USER_ID, email=EMAIL)


async def test_a_token_without_an_email_still_resolves(
    verifier: SupabaseTokenVerifier, signer: Signer
) -> None:
    """Supabase omits `email` for a phone or anonymous sign-in; that is not an error here."""
    user = await verifier.verify(signer.token(email=None))

    assert user.user_id == USER_ID
    assert user.email is None


async def test_the_email_is_folded_to_lower_case(
    verifier: SupabaseTokenVerifier, signer: Signer
) -> None:
    """The developer list is compared against this, and email case is not significant."""
    user = await verifier.verify(signer.token(email="Sabine@Example-IT.de"))

    assert user.email == EMAIL


async def test_the_jwks_is_fetched_once_and_reused(
    verifier: SupabaseTokenVerifier, signer: Signer, jwks: FakeJwks
) -> None:
    await verifier.verify(signer.token())
    await verifier.verify(signer.token())

    assert jwks.calls == 1


# --------------------------------------------------------------- what it refuses


async def test_an_expired_token_is_refused(
    verifier: SupabaseTokenVerifier, signer: Signer
) -> None:
    with pytest.raises(TokenRejectedError):
        await verifier.verify(signer.token(exp=int(time.time()) - 1))


async def test_another_keys_signature_is_refused(
    verifier: SupabaseTokenVerifier, jwks: FakeJwks
) -> None:
    """Same `kid`, different key: the attacker names a key we trust and signs with theirs."""
    forged = Signer("key-one")

    with pytest.raises(TokenRejectedError):
        await verifier.verify(forged.token())
    assert jwks.calls >= 1


async def test_an_unsigned_token_is_refused(verifier: SupabaseTokenVerifier) -> None:
    """`alg: none` — the oldest JWT attack there is."""
    unsigned = jwt.encode(
        {"iss": ISSUER, "aud": AUDIENCE, "sub": USER_ID, "exp": int(time.time()) + 60},
        key="",
        algorithm="none",
        headers={"kid": "key-one"},
    )

    with pytest.raises(TokenRejectedError):
        await verifier.verify(unsigned)


async def test_the_public_key_used_as_a_shared_secret_is_refused(
    verifier: SupabaseTokenVerifier, signer: Signer
) -> None:
    """Algorithm confusion: HS256 signed with the very public key we publish.

    Hand-rolled, because PyJWT refuses to *encode* this — which is a defence on the signing
    side and says nothing about what we accept on the verifying side.
    """
    confused = _hs256_with(signer.public_pem, kid="key-one")

    with pytest.raises(TokenRejectedError):
        await verifier.verify(confused)


async def test_another_projects_issuer_is_refused(
    verifier: SupabaseTokenVerifier, signer: Signer
) -> None:
    with pytest.raises(TokenRejectedError):
        await verifier.verify(signer.token(iss="https://someone-else.supabase.co/auth/v1"))


async def test_a_token_for_another_audience_is_refused(
    verifier: SupabaseTokenVerifier, signer: Signer
) -> None:
    with pytest.raises(TokenRejectedError):
        await verifier.verify(signer.token(aud="anon"))


async def test_a_token_without_a_subject_is_refused(
    verifier: SupabaseTokenVerifier, signer: Signer
) -> None:
    """No `sub` means no user, and a company would then be resolved for nobody."""
    with pytest.raises(TokenRejectedError):
        await verifier.verify(signer.token(sub=None))


@pytest.mark.parametrize("token", ["", "   ", "not.a.token", "a.b", "Bearer x.y.z"])
async def test_junk_is_refused(verifier: SupabaseTokenVerifier, token: str) -> None:
    with pytest.raises(TokenRejectedError):
        await verifier.verify(token)


async def test_the_refusal_never_quotes_the_token(
    verifier: SupabaseTokenVerifier, signer: Signer
) -> None:
    """A rejected token is a credential; it must not reach a log line or a response."""
    token = signer.token(exp=int(time.time()) - 1)

    with pytest.raises(TokenRejectedError) as raised:
        await verifier.verify(token)

    assert token not in str(raised.value)


# ------------------------------------------------------- key rotation and outages


async def test_an_unknown_key_id_refetches_the_jwks(jwks: FakeJwks) -> None:
    """Supabase rotates signing keys; a token signed by a new one must not need a restart."""
    rotated = Signer("key-two")
    verifier = SupabaseTokenVerifier(
        issuer=ISSUER, audience=AUDIENCE, jwks=jwks, refresh_floor_seconds=0.0
    )
    await verifier.verify(jwks.signers[0].token())
    jwks.signers.append(rotated)

    user = await verifier.verify(rotated.token())

    assert user.user_id == USER_ID
    assert jwks.calls == 2


async def test_an_unknown_key_id_does_not_refetch_on_every_request(jwks: FakeJwks) -> None:
    """Otherwise a stream of forged `kid`s is a free denial of service against Supabase."""
    clock = iter([0.0, 0.0, 1.0, 2.0, 3.0, 4.0, 5.0])
    verifier = SupabaseTokenVerifier(
        issuer=ISSUER, audience=AUDIENCE, jwks=jwks, now=lambda: next(clock)
    )
    stranger = Signer("key-unknown")

    for _ in range(3):
        with pytest.raises(TokenRejectedError):
            await verifier.verify(stranger.token())

    assert jwks.calls == 1


async def test_the_refresh_floor_lifts_once_it_has_passed(jwks: FakeJwks) -> None:
    ticks = iter([0.0, 0.0, 1000.0, 1000.0])
    verifier = SupabaseTokenVerifier(
        issuer=ISSUER, audience=AUDIENCE, jwks=jwks, now=lambda: next(ticks)
    )
    rotated = Signer("key-two")
    with pytest.raises(TokenRejectedError):
        await verifier.verify(rotated.token())
    jwks.signers.append(rotated)

    user = await verifier.verify(rotated.token())

    assert user.user_id == USER_ID
    assert jwks.calls == 2


async def test_an_unreachable_jwks_is_not_the_callers_fault(
    verifier: SupabaseTokenVerifier, signer: Signer, jwks: FakeJwks
) -> None:
    """A Supabase outage is a 503, never a 401 telling the user their token is bad."""
    jwks.error = OSError("connection refused")

    with pytest.raises(SigningKeysUnavailableError):
        await verifier.verify(signer.token())


async def test_a_malformed_jwks_document_is_an_outage_not_a_rejection(
    signer: Signer,
) -> None:
    async def broken() -> Mapping[str, Any]:
        return {"keys": "not a list"}

    verifier = SupabaseTokenVerifier(issuer=ISSUER, audience=AUDIENCE, jwks=broken)

    with pytest.raises(SigningKeysUnavailableError):
        await verifier.verify(signer.token())


# ----------------------------------------------------------- the request pipeline


class FakeCompanies:
    """Just the one lookup `current_company` makes."""

    def __init__(self, owned: Mapping[str, str] | None = None) -> None:
        # `or` would be wrong: an empty mapping is the "not onboarded yet" case.
        self.owned = dict({USER_ID: COMPANY_ID} if owned is None else owned)
        self.calls: list[str] = []

    async def company_id_for_owner(self, *, owner_user_id: uuid.UUID) -> uuid.UUID | None:
        self.calls.append(str(owner_user_id))
        found = self.owned.get(str(owner_user_id))
        return None if found is None else uuid.UUID(found)


def supabase_app(
    settings: Settings,
    *,
    signer: Signer,
    jwks: FakeJwks,
    companies: FakeCompanies,
    developer_emails: str = "",
) -> FastAPI:
    env = settings.env.model_copy(
        update={
            "auth_mode": AuthMode.SUPABASE,
            "supabase_url": "https://project.supabase.co",
            "developer_emails": developer_emails,
        }
    )
    app = create_app(Settings(env=env, runtime=settings.runtime))

    @app.get("/whoami")
    async def whoami(company: CompanyContext = Depends(current_company)) -> CompanyContext:
        return company

    @app.get("/me")
    async def me(user: AuthenticatedUser = Depends(current_user)) -> AuthenticatedUser:
        return user

    @app.get("/dev/probe")
    async def probe(user: AuthenticatedUser = Depends(require_developer)) -> str:
        return user.user_id

    app.dependency_overrides[get_token_verifier] = lambda: SupabaseTokenVerifier(
        issuer=ISSUER, audience=AUDIENCE, jwks=jwks
    )
    app.dependency_overrides[get_company_lookup] = lambda: companies
    return app


@pytest.fixture
def companies() -> FakeCompanies:
    return FakeCompanies()


@pytest.fixture
def client(
    offline_settings: Settings, signer: Signer, jwks: FakeJwks, companies: FakeCompanies
) -> Iterator[TestClient]:
    app = supabase_app(offline_settings, signer=signer, jwks=jwks, companies=companies)
    with TestClient(app) as test_client:
        yield test_client


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_a_signed_in_user_resolves_to_their_company(
    client: TestClient, signer: Signer, companies: FakeCompanies
) -> None:
    response = client.get("/whoami", headers=bearer(signer.token()))

    assert response.status_code == 200
    assert response.json() == {"company_id": COMPANY_ID}
    assert companies.calls == [USER_ID]


def test_a_signed_in_user_with_no_company_is_404(
    offline_settings: Settings, signer: Signer, jwks: FakeJwks
) -> None:
    """Signed in but not onboarded yet: the web app sends them to the company form."""
    app = supabase_app(
        offline_settings, signer=signer, jwks=jwks, companies=FakeCompanies(owned={})
    )
    with TestClient(app) as client:
        response = client.get("/whoami", headers=bearer(signer.token()))

    assert response.status_code == 404


def test_the_user_dependency_answers_the_token_s_claims(
    client: TestClient, signer: Signer
) -> None:
    response = client.get("/me", headers=bearer(signer.token()))

    assert response.json() == {"user_id": USER_ID, "email": EMAIL, "is_developer": False}


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": ""}, {"Authorization": "Bearer"}, {"Authorization": "Basic abc"}],
)
def test_a_request_without_a_bearer_token_is_401(
    client: TestClient, headers: dict[str, str]
) -> None:
    response = client.get("/whoami", headers=headers)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_the_scheme_is_matched_case_insensitively(client: TestClient, signer: Signer) -> None:
    """RFC 7235 says the scheme is case-insensitive, and browsers differ."""
    response = client.get("/whoami", headers={"Authorization": f"bearer {signer.token()}"})

    assert response.status_code == 200


def test_a_forged_token_is_401(client: TestClient) -> None:
    response = client.get("/whoami", headers=bearer(Signer("key-one").token()))

    assert response.status_code == 401


def test_the_dev_header_is_ignored_under_supabase_auth(
    client: TestClient, signer: Signer
) -> None:
    """The criterion, stated directly: a header is not a credential outside dev mode."""
    from crossbid.auth import DEV_COMPANY_HEADER

    response = client.get("/whoami", headers={DEV_COMPANY_HEADER: str(uuid.uuid4())})

    assert response.status_code == 401
    assert response.json()["detail"] != COMPANY_ID
    assert client.get("/whoami", headers=bearer(signer.token())).json() == {
        "company_id": COMPANY_ID
    }


def test_a_supabase_outage_is_503_and_not_a_rejected_token(
    client: TestClient, signer: Signer, jwks: FakeJwks
) -> None:
    jwks.error = OSError("connection refused")

    response = client.get("/whoami", headers=bearer(signer.token()))

    assert response.status_code == 503


# ------------------------------------------------------------- the developer gate


def developer_client(
    settings: Settings, signer: Signer, jwks: FakeJwks, emails: str
) -> TestClient:
    app = supabase_app(
        settings,
        signer=signer,
        jwks=jwks,
        companies=FakeCompanies(),
        developer_emails=emails,
    )
    return TestClient(app)


def test_an_email_on_the_developer_list_reaches_a_dev_route(
    offline_settings: Settings, signer: Signer, jwks: FakeJwks
) -> None:
    with developer_client(offline_settings, signer, jwks, f"{DEVELOPER_EMAIL},{EMAIL}") as c:
        response = c.get("/dev/probe", headers=bearer(signer.token()))

    assert response.status_code == 200


def test_the_developer_list_is_compared_case_and_space_insensitively(
    offline_settings: Settings, signer: Signer, jwks: FakeJwks
) -> None:
    listed = f"  {EMAIL.upper()} , {DEVELOPER_EMAIL}  "

    with developer_client(offline_settings, signer, jwks, listed) as c:
        response = c.get("/dev/probe", headers=bearer(signer.token()))

    assert response.status_code == 200


def test_an_email_not_on_the_list_is_403(
    offline_settings: Settings, signer: Signer, jwks: FakeJwks
) -> None:
    with developer_client(offline_settings, signer, jwks, DEVELOPER_EMAIL) as c:
        response = c.get("/dev/probe", headers=bearer(signer.token()))

    assert response.status_code == 403


def test_an_empty_developer_list_admits_nobody(
    offline_settings: Settings, signer: Signer, jwks: FakeJwks
) -> None:
    """An unset DEVELOPER_EMAILS must close the door, never open it."""
    with developer_client(offline_settings, signer, jwks, "") as c:
        response = c.get("/dev/probe", headers=bearer(signer.token()))

    assert response.status_code == 403


def test_a_token_with_no_email_is_never_a_developer(
    offline_settings: Settings, signer: Signer, jwks: FakeJwks
) -> None:
    with developer_client(offline_settings, signer, jwks, DEVELOPER_EMAIL) as c:
        response = c.get("/dev/probe", headers=bearer(signer.token(email=None)))

    assert response.status_code == 403


# --------------------------------------------------------------- the wiring itself


async def test_a_token_whose_subject_is_blank_is_refused(
    verifier: SupabaseTokenVerifier, signer: Signer
) -> None:
    """`require` only asks that the claim be *present*; an empty user is still no user."""
    with pytest.raises(TokenRejectedError):
        await verifier.verify(signer.token(sub="   "))


async def test_a_token_whose_subject_is_not_a_string_is_refused(
    verifier: SupabaseTokenVerifier, signer: Signer
) -> None:
    with pytest.raises(TokenRejectedError):
        await verifier.verify(signer.token(sub=12345))


async def test_the_real_fetcher_reads_the_projects_jwks_url(signer: Signer) -> None:
    """The one place the JWKS URL is assembled, served over a transport rather than a socket."""
    seen: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json={"keys": [signer.jwk]})

    fetch = jwks_source("https://project.supabase.co/", transport=httpx.MockTransport(handle))
    document = await fetch()

    assert seen == ["https://project.supabase.co/auth/v1/.well-known/jwks.json"]
    assert document["keys"][0]["kid"] == "key-one"


async def test_the_real_fetcher_turns_an_error_response_into_an_outage(
    signer: Signer,
) -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(500))
    verifier = SupabaseTokenVerifier(
        issuer=ISSUER,
        audience=AUDIENCE,
        jwks=jwks_source("https://project.supabase.co", transport=transport),
    )

    with pytest.raises(SigningKeysUnavailableError):
        await verifier.verify(signer.token())


def test_the_verifier_is_built_from_the_project_url(offline_settings: Settings) -> None:
    settings = _supabase_settings(offline_settings, url="https://project.supabase.co/")

    built = build_token_verifier(settings)

    assert built._issuer == ISSUER
    assert built._audience == "authenticated"


def test_building_a_verifier_without_a_project_url_is_a_programming_error(
    offline_settings: Settings,
) -> None:
    """`load_settings` refuses this first; reaching it means settings were built in code."""
    settings = _supabase_settings(offline_settings, url=None)

    with pytest.raises(RuntimeError, match="SUPABASE_URL"):
        build_token_verifier(settings)


def test_the_verifier_is_built_once_per_app(offline_settings: Settings) -> None:
    """The key cache is only worth having if every request shares the same verifier."""
    settings = _supabase_settings(offline_settings, url="https://project.supabase.co")
    request = _StubRequest()

    first = get_token_verifier(request, settings)  # pyright: ignore[reportArgumentType]
    second = get_token_verifier(request, settings)  # pyright: ignore[reportArgumentType]

    assert first is second


def test_no_verifier_is_built_under_dev_auth(offline_settings: Settings) -> None:
    request = _StubRequest()

    assert get_token_verifier(request, offline_settings) is None  # pyright: ignore[reportArgumentType]


def test_the_company_lookup_is_the_read_model_under_supabase_auth(
    offline_settings: Settings,
) -> None:
    settings = _supabase_settings(offline_settings, url="https://project.supabase.co")
    request = _StubRequest()

    lookup = get_company_lookup(request, settings)  # pyright: ignore[reportArgumentType]

    assert isinstance(lookup, CompaniesReadModel)


def test_no_company_lookup_is_built_under_dev_auth(offline_settings: Settings) -> None:
    """The dev bridge reads the company off a header, so it must need no pool at all."""
    request = _StubRequest()

    assert get_company_lookup(request, offline_settings) is None  # pyright: ignore[reportArgumentType]


def _supabase_settings(settings: Settings, *, url: str | None) -> Settings:
    env = settings.env.model_copy(update={"auth_mode": AuthMode.SUPABASE, "supabase_url": url})
    return Settings(env=env, runtime=settings.runtime)


class _StubRequest:
    """Just the `app.state` the two providers reach through."""

    def __init__(self) -> None:
        self.app = SimpleNamespace(state=SimpleNamespace(db=object()))
