"""S2.4.1 — `GET /companies/me` and `PUT /companies/me`, offline and end to end over HTTP.

The app is the real `create_app` and the router is the real one; only the two dependencies
that would open a socket are replaced — the `companies` table by an in-memory stand-in that a
save and a read share, and LangGraph's Store by a recorder. That is enough to exercise both
halves of the story's first criterion in one request pair (**the row comes back *and* the
Store namespace is written**), which is the point: neither write is optional.

"Today" arrives through `get_today`, a dependency, so the expiry tests state the date they
mean instead of depending on the day the suite runs. The final test group is about what
happens when the Store write fails after the row write — the answer is a 200 carrying a
`warning`, because the row it is a copy of was genuinely written and a caller told "save
failed" would reasonably assume their facts were lost. The half a bidder cannot act on goes
to the log instead, with the traceback, since retrying is what they are asked to do.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from crossbid.auth import DEV_COMPANY_HEADER, DEV_USER_ID
from crossbid.main import create_app
from crossbid.models import CertificateHeld, CompanyProfile, LegalForm, Tone, TurnoverYear
from crossbid.readmodel.companies import CompaniesReadModel
from crossbid.routers.companies import (
    MEMORY_NOT_UPDATED_WARNING,
    NO_SUCH_COMPANY_DETAIL,
    PROFILE_STORE_KEY,
    CertificateResponse,
    CompanyProfileResponse,
    get_company_records,
    get_profile_store,
    get_today,
    profile_namespace,
    router,
)
from crossbid.settings import Settings
from tests.conftest import FakeConnectionSource, FakePoolFactory, company_row, connect

COMPANY = uuid.UUID("11111111-1111-4111-8111-111111111111")
OTHER_COMPANY = uuid.UUID("22222222-2222-4222-8222-222222222222")
AS_COMPANY = {DEV_COMPANY_HEADER: str(COMPANY)}
AS_OTHER_COMPANY = {DEV_COMPANY_HEADER: str(OTHER_COMPANY)}

TODAY = date(2026, 9, 11)

EXPIRED = CertificateHeld(name="ISO 9001:2015", expires_on=date(2025, 1, 31))
VALID = CertificateHeld(name="ISO/IEC 27001:2022", expires_on=date(2027, 5, 1))
UNDATED = CertificateHeld(name="Präqualifikation PQ-VOB")

PROFILE = CompanyProfile(
    name="Beispiel IT Services GmbH",
    country="de",
    legal_form=LegalForm.GMBH,
    registration_number="HRB 84512",
    registration_court="Amtsgericht München",
    language="de",
    tone=Tone.PLAIN,
    staff_fte=48.0,
    staff_fte_relevant=31.5,
    turnover=(TurnoverYear(year=2025, amount=7_400_000.0, currency="EUR"),),
    certificates=(EXPIRED, VALID, UNDATED),
)


# -------------------------------------------------------------------------- the fakes


class InMemoryCompanies:
    """`CompaniesReadModel`'s two methods over a dict, so a save and a read share state.

    A company that is not in the dict was never created: `save` reports it the way the real
    `update ... returning` does, by answering `None` rather than creating a row. `create` is
    the one route that makes one, and it takes the owner from the verified token (S0.3.1).
    """

    def __init__(self, **profiles: CompanyProfile) -> None:
        self.profiles = {uuid.UUID(key): value for key, value in profiles.items()}
        self.owners: dict[uuid.UUID, uuid.UUID] = {}

    async def get(self, *, company_id: uuid.UUID) -> CompanyProfile | None:
        return self.profiles.get(company_id)

    async def company_id_for_owner(self, *, owner_user_id: uuid.UUID) -> uuid.UUID | None:
        for company_id, owner in self.owners.items():
            if owner == owner_user_id:
                return company_id
        return None

    async def create(
        self, *, company_id: uuid.UUID, owner_user_id: uuid.UUID, profile: CompanyProfile
    ) -> CompanyProfile | None:
        if company_id in self.profiles:
            return None
        self.profiles[company_id] = profile
        self.owners[company_id] = owner_user_id
        return profile

    async def save(
        self, *, company_id: uuid.UUID, profile: CompanyProfile
    ) -> CompanyProfile | None:
        if company_id not in self.profiles:
            return None
        self.profiles[company_id] = profile
        return profile


class RecordingStore:
    """The slice of LangGraph's `BaseStore` the router uses, with an optional failure."""

    def __init__(
        self, error: Exception | None = None, *, delete_error: Exception | None = None
    ) -> None:
        self.items: dict[tuple[tuple[str, ...], str], dict[str, Any]] = {}
        self._error = error
        self._delete_error = delete_error
        self.deletes: list[tuple[tuple[str, ...], str]] = []

    async def aput(self, namespace: tuple[str, ...], key: str, value: dict[str, Any]) -> None:
        if self._error is not None:
            raise self._error
        self.items[(namespace, key)] = value

    async def adelete(self, namespace: tuple[str, ...], key: str) -> None:
        self.deletes.append((namespace, key))
        if self._delete_error is not None:
            raise self._delete_error
        self.items.pop((namespace, key), None)


# ----------------------------------------------------------------------------- fixtures


def build_api(
    settings: Settings,
    records: Any,
    store: Any,
    *,
    today: date | None = TODAY,
) -> TestClient:
    """The real app and router with the database and the Store replaced, nothing else."""
    app: FastAPI = create_app(settings)
    app.include_router(router)
    app.dependency_overrides[get_company_records] = lambda: records
    app.dependency_overrides[get_profile_store] = lambda: store
    if today is not None:
        app.dependency_overrides[get_today] = lambda: today
    return TestClient(app)


@pytest.fixture
def records() -> InMemoryCompanies:
    return InMemoryCompanies(**{str(COMPANY): PROFILE})


@pytest.fixture
def store() -> RecordingStore:
    return RecordingStore()


@pytest.fixture
def api(
    offline_settings: Settings, records: InMemoryCompanies, store: RecordingStore
) -> Iterator[TestClient]:
    with build_api(offline_settings, records, store) as client:
        yield client


def body_of(profile: CompanyProfile, **overrides: Any) -> dict[str, Any]:
    return profile.model_dump(mode="json") | overrides


# ------------------------------------------------------------------------ registration


def test_the_company_routes_are_registered(client: TestClient) -> None:
    """S2.4.1 is wired; the OpenAPI schema is what `frontend/lib/api.ts` is generated from."""
    schema = client.get("/openapi.json").json()

    assert "/companies/me" in schema["paths"]
    assert set(schema["paths"]["/companies/me"]) == {"get", "put"}


# ------------------------------------------------------------------------------- read


def test_get_returns_the_calling_companys_profile(api: TestClient) -> None:
    # Act
    response = api.get("/companies/me", headers=AS_COMPANY)

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == PROFILE.name
    assert body["country"] == "de"
    assert body["legal_form"] == "gmbh"
    assert body["registration_number"] == "HRB 84512"
    assert body["staff_fte_relevant"] == 31.5
    assert body["turnover"] == [
        {"year": 2025, "amount": 7_400_000.0, "currency": "EUR", "field_of_activity": None}
    ]


def test_a_company_with_no_row_is_a_404_and_not_an_empty_profile(api: TestClient) -> None:
    """`AUTH_MODE=dev` believes any UUID in the header; an unseeded one has no facts."""
    response = api.get("/companies/me", headers=AS_OTHER_COMPANY)

    assert response.status_code == 404
    assert response.json()["detail"] == NO_SUCH_COMPANY_DETAIL


def test_the_read_is_scoped_to_the_caller_by_the_statement_itself(
    offline_settings: Settings, store: RecordingStore
) -> None:
    """The real read model over a recording connection: the scope is in the SQL, not in code."""
    # Arrange
    source = FakeConnectionSource((company_row(),))

    # Act
    with build_api(offline_settings, CompaniesReadModel(source), store) as api:
        api.get("/companies/me", headers=AS_COMPANY)

    # Assert
    assert source.only.params == {"company_id": COMPANY}
    assert "id = %(company_id)s" in source.only.sql


# ------------------------------------------------------------------------------ write


def test_saving_the_form_returns_the_profile_and_writes_the_store_namespace(
    api: TestClient, records: InMemoryCompanies, store: RecordingStore
) -> None:
    """The story's first criterion, both halves: the row answers and the memory is written."""
    # Arrange
    changed = PROFILE.model_copy(update={"staff_fte": 52.0, "language": "en"})

    # Act
    saved = api.put("/companies/me", json=body_of(changed), headers=AS_COMPANY)

    # Assert
    assert saved.status_code == 200
    assert saved.json()["staff_fte"] == 52.0
    assert api.get("/companies/me", headers=AS_COMPANY).json()["language"] == "en"
    assert records.profiles[COMPANY] == changed

    remembered = store.items[(profile_namespace(COMPANY), PROFILE_STORE_KEY)]
    assert remembered["staff_fte"] == 52.0
    assert remembered["name"] == PROFILE.name
    assert remembered["certificates"][0]["name"] == EXPIRED.name


def test_the_store_namespace_is_profile_slash_company_id() -> None:
    """`db.py` names it `profile/{company_id}`; the agent's long-term memory reads it there."""
    assert profile_namespace(COMPANY) == ("profile", str(COMPANY))


def test_saving_for_a_company_with_no_row_is_a_404_and_writes_no_memory(
    api: TestClient, store: RecordingStore
) -> None:
    """No route creates a company: `owner_user_id` comes from sign-up, not from this form."""
    response = api.put("/companies/me", json=body_of(PROFILE), headers=AS_OTHER_COMPANY)

    assert response.status_code == 404
    assert response.json()["detail"] == NO_SUCH_COMPANY_DETAIL
    assert store.items == {}


@pytest.mark.parametrize("country", ["deu", "DE"])
def test_a_rejected_field_is_named_in_the_422(api: TestClient, country: str) -> None:
    """S4.2.1 puts the message under the input, so the response must say which input.

    `"DE"` is the case the length bounds alone let through: two letters, so Pydantic passed
    it, and `companies_country_check` then refused it — a `CheckViolation` surfacing as a 500
    with a traceback, which is the opposite of what this route's docstring promises. The
    schema now carries the column's own regex, so the refusal happens here and names the
    field.
    """
    response = api.put(
        "/companies/me", json=body_of(PROFILE, country=country), headers=AS_COMPANY
    )

    assert response.status_code == 422
    assert [error["loc"] for error in response.json()["detail"]] == [["body", "country"]]


def test_an_unknown_field_is_refused_rather_than_dropped(api: TestClient) -> None:
    """`CompanyProfile` forbids extras: a typo in the form is an error, not a lost fact."""
    response = api.put("/companies/me", json=body_of(PROFILE, headcount=12), headers=AS_COMPANY)

    assert response.status_code == 422
    assert ["body", "headcount"] in [error["loc"] for error in response.json()["detail"]]


# ------------------------------------------------------------------- certificate flags


def test_an_expired_certificate_is_flagged_and_a_current_one_is_not(api: TestClient) -> None:
    """The story's second criterion. `TODAY` is injected, so this does not rot."""
    # Act
    body = api.get("/companies/me", headers=AS_COMPANY).json()

    # Assert
    expired, valid, _ = body["certificates"]
    assert body["checked_on"] == TODAY.isoformat()
    assert (expired["name"], expired["is_expired"], expired["is_valid"]) == (
        EXPIRED.name,
        True,
        False,
    )
    assert (valid["is_expired"], valid["is_valid"]) == (False, True)
    assert body["has_expired_certificates"] is True


def test_a_certificate_with_no_expiry_is_not_valid_and_not_expired(api: TestClient) -> None:
    """`is_valid_on` refuses to claim validity without a date; that is not the same as expired,
    and the form must not tell a bidder to renew a certificate that has no renewal date."""
    undated = api.get("/companies/me", headers=AS_COMPANY).json()["certificates"][2]

    assert undated["expires_on"] is None
    assert undated["is_valid"] is False
    assert undated["is_expired"] is False


def test_a_certificate_expiring_today_is_still_valid(api: TestClient) -> None:
    """`expires_on >= when`: the last day counts, which is what a bidder would argue."""
    # Arrange
    today = CertificateHeld(name="Heute", expires_on=TODAY)
    flagged = CertificateResponse.flagged(today, today=TODAY)

    # Assert
    assert flagged.is_valid is True and flagged.is_expired is False


def test_a_profile_with_no_certificates_is_not_flagged(
    offline_settings: Settings, store: RecordingStore
) -> None:
    without = PROFILE.model_copy(update={"certificates": ()})
    records = InMemoryCompanies(**{str(COMPANY): without})

    with build_api(offline_settings, records, store) as api:
        body = api.get("/companies/me", headers=AS_COMPANY).json()

    assert body["certificates"] == []
    assert body["has_expired_certificates"] is False


def test_today_defaults_to_the_current_utc_date(
    offline_settings: Settings, records: InMemoryCompanies, store: RecordingStore
) -> None:
    """The seam has a production implementation; only the tests inject a fixed date."""
    # Act -- no override for `get_today`
    with build_api(offline_settings, records, store, today=None) as api:
        body = api.get("/companies/me", headers=AS_COMPANY).json()

    # Assert
    assert body["checked_on"] == datetime.now(UTC).date().isoformat()


# ------------------------------------------------------- when the memory write fails


def test_a_failed_store_write_is_a_200_carrying_a_warning_not_a_failed_save(
    offline_settings: Settings,
    records: InMemoryCompanies,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The row write landed, so the save succeeded; reporting failure would be the worse lie.

    The partial failure travels as the typed `warning` field instead — and it is still logged
    with the company id and the underlying error, which is the half a bidder cannot act on.
    """
    # Arrange
    store = RecordingStore(error=RuntimeError("connection pool exhausted"))

    # Act
    with build_api(offline_settings, records, store) as api:
        response = api.put("/companies/me", json=body_of(PROFILE), headers=AS_COMPANY)

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["warning"] == MEMORY_NOT_UPDATED_WARNING
    assert body["name"] == PROFILE.name, "the saved facts still come back"
    assert records.profiles[COMPANY] == PROFILE, "and the row is genuinely written"
    assert "connection pool exhausted" in caplog.text
    assert str(COMPANY) in caplog.text
    failure = next(record for record in caplog.records if record.levelno == logging.ERROR)
    assert failure.exc_info is not None, (
        "this line is the only record of why the Store write failed, and the bidder is told "
        "to retry — a recurring failure is undiagnosable without the frame it happened in"
    )


def test_a_failed_store_write_forgets_the_stale_memory_rather_than_leaving_it(
    offline_settings: Settings, records: InMemoryCompanies
) -> None:
    """Since ADR-0077 the agent *reads* this item, so a stale one is worse than none at all.

    The hazard is specific: a bidder corrects their headcount, the row is written, the Store
    write fails, and the next bid is checked against yesterday's figure with nothing on screen
    to say so. Deleting turns that into a miss, and a miss is answered from the row.
    """
    # Arrange
    stale = PROFILE.model_dump(mode="json")
    store = RecordingStore(error=RuntimeError("connection pool exhausted"))
    store.items[(profile_namespace(COMPANY), PROFILE_STORE_KEY)] = stale

    # Act
    with build_api(offline_settings, records, store) as api:
        response = api.put(
            "/companies/me",
            json=body_of(PROFILE.model_copy(update={"staff_fte": 60.0})),
            headers=AS_COMPANY,
        )

    # Assert
    assert response.json()["warning"] == MEMORY_NOT_UPDATED_WARNING
    assert store.deletes == [(profile_namespace(COMPANY), PROFILE_STORE_KEY)]
    assert (profile_namespace(COMPANY), PROFILE_STORE_KEY) not in store.items


def test_a_forget_that_also_fails_is_still_one_warning_and_no_raise(
    offline_settings: Settings, records: InMemoryCompanies
) -> None:
    """A Store that is down fails both calls. The save still landed, so the answer is 200."""
    # Arrange
    store = RecordingStore(
        error=RuntimeError("connection pool exhausted"),
        delete_error=RuntimeError("connection pool exhausted"),
    )
    store.items[(profile_namespace(COMPANY), PROFILE_STORE_KEY)] = PROFILE.model_dump(
        mode="json"
    )

    # Act
    with build_api(offline_settings, records, store) as api:
        response = api.put("/companies/me", json=body_of(PROFILE), headers=AS_COMPANY)

    # Assert
    assert response.status_code == 200
    assert response.json()["warning"] == MEMORY_NOT_UPDATED_WARNING


def test_a_save_that_wrote_both_carries_no_warning(api: TestClient) -> None:
    """`None` on the happy path, so a client can treat "present" as "something needs
    attention" without comparing the text."""
    saved = api.put("/companies/me", json=body_of(PROFILE), headers=AS_COMPANY)

    assert saved.json()["warning"] is None


def test_reading_the_profile_never_sets_the_warning(api: TestClient) -> None:
    """`GET` writes nothing, so it has nothing to warn about."""
    assert api.get("/companies/me", headers=AS_COMPANY).json()["warning"] is None


def test_the_row_survives_a_failed_store_write_so_repeating_the_save_repairs_it(
    offline_settings: Settings, records: InMemoryCompanies
) -> None:
    """`PUT` is idempotent: the retry rewrites the same row and re-runs the memory write."""
    # Arrange
    changed = PROFILE.model_copy(update={"staff_fte": 60.0})
    failing = RecordingStore(error=RuntimeError("no"))
    working = RecordingStore()

    # Act
    with build_api(offline_settings, records, failing) as api:
        api.put("/companies/me", json=body_of(changed), headers=AS_COMPANY)
    with build_api(offline_settings, records, working) as api:
        retried = api.put("/companies/me", json=body_of(changed), headers=AS_COMPANY)

    # Assert
    assert retried.status_code == 200
    assert retried.json()["warning"] is None, "the repair is complete, so nothing to flag"
    assert records.profiles[COMPANY] == changed
    assert working.items[(profile_namespace(COMPANY), PROFILE_STORE_KEY)]["staff_fte"] == 60.0


# ------------------------------------------------------------------- the contract itself


def test_every_response_field_is_described_for_the_generated_client() -> None:
    """`frontend/lib/api.ts` is generated from this schema; a bare field is a bare type."""
    for model in (CompanyProfileResponse, CertificateResponse):
        for name, info in model.model_fields.items():
            assert info.description, f"{model.__name__}.{name} has no description"


def test_the_response_is_the_profile_plus_the_derived_flags() -> None:
    """Derived, not mutated: `CompanyProfile` is frozen and stays the shape that is saved."""
    derived = {"has_expired_certificates", "checked_on", "warning"}

    profile_fields = set(CompanyProfile.model_fields)

    assert set(CompanyProfileResponse.model_fields) == profile_fields | derived
    assert set(CertificateResponse.model_fields) == set(CertificateHeld.model_fields) | {
        "is_expired",
        "is_valid",
    }


@pytest.mark.anyio
async def test_the_production_dependencies_are_the_pool_and_langgraphs_own_store() -> None:
    """Every test above replaces these two, so this is where they are exercised for real.

    Over `conftest`'s fake pool: the read model is built on the process pool and
    the memory the router writes to is LangGraph's `AsyncPostgresStore`, not a second client.
    Nothing opens a socket.
    """
    # Arrange
    db = await connect(FakePoolFactory())

    # Act / Assert
    try:
        assert isinstance(get_company_records(db), CompaniesReadModel)
        assert get_profile_store(db) is db.store
    finally:
        await db.close()


# ------------------------------------------------------- POST /companies (S0.3.1)


def test_creating_a_company_returns_201_and_the_saved_profile(
    offline_settings: Settings, records: InMemoryCompanies, store: RecordingStore
) -> None:
    with build_api(offline_settings, records, store) as client:
        response = client.post("/companies", json=PROFILE.model_dump(mode="json"))

    assert response.status_code == 201
    assert response.json()["name"] == PROFILE.name


def test_the_new_company_is_owned_by_the_calling_user(
    offline_settings: Settings, records: InMemoryCompanies, store: RecordingStore
) -> None:
    """The owner comes from the caller's identity, never from anything they sent."""
    with build_api(offline_settings, records, store) as client:
        client.post("/companies", json=PROFILE.model_dump(mode="json"))

    assert list(records.owners.values()) == [uuid.UUID(DEV_USER_ID)]


def test_a_body_naming_an_owner_is_refused_rather_than_ignored(
    offline_settings: Settings, records: InMemoryCompanies, store: RecordingStore
) -> None:
    """A client that could name the owner could create a company for somebody else, and a
    silently dropped field would leave them believing they had."""
    with build_api(offline_settings, records, store) as client:
        response = client.post(
            "/companies",
            json={**PROFILE.model_dump(mode="json"), "owner_user_id": str(OTHER_COMPANY)},
        )

    assert response.status_code == 422
    assert records.owners == {}


def test_a_second_company_for_the_same_user_is_409(
    offline_settings: Settings, records: InMemoryCompanies, store: RecordingStore
) -> None:
    """One company per user, enforced by the unique index and answered as a conflict."""
    with build_api(offline_settings, records, store) as client:
        client.post("/companies", json=PROFILE.model_dump(mode="json"))
        response = client.post("/companies", json=PROFILE.model_dump(mode="json"))

    assert response.status_code == 409
    assert "PUT /companies/me" in response.json()["detail"]


def test_creating_a_company_validates_the_body(
    offline_settings: Settings, records: InMemoryCompanies, store: RecordingStore
) -> None:
    with build_api(offline_settings, records, store) as client:
        response = client.post("/companies", json={"name": "No country given"})

    assert response.status_code == 422


def test_creating_a_company_flags_an_expired_certificate(
    offline_settings: Settings, records: InMemoryCompanies, store: RecordingStore
) -> None:
    """The same response model as the other two routes, so onboarding shows the gap at once."""
    with build_api(offline_settings, records, store) as client:
        response = client.post("/companies", json=PROFILE.model_dump(mode="json"))

    expired = [item for item in response.json()["certificates"] if item["is_expired"]]
    assert [item["name"] for item in expired] == [EXPIRED.name]
