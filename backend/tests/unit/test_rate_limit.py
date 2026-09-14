"""S2.3.3 — one company cannot start unbounded uploads or bid runs.

Offline, and with no `time.sleep` anywhere: the limiter takes its clock as a parameter, so
"an hour later" is one call to `Clock.advance` and the window test runs in microseconds
rather than being skipped for being slow.

Two layers are exercised. The limiter itself is driven directly, because the arithmetic that
matters — when a slot frees, what a refusal does to the deadline — is easier to pin without
HTTP in the way. The dependency is driven over real HTTP, because the acceptance criterion is
about a status code and a header, and because that is the only way to prove that
`current_company` resolves *before* the counter is touched.

The load-bearing test is `test_two_companies_never_share_a_budget`: a counter keyed on
anything but `company_id` would let one tenant's uploads lock another tenant out, which is a
cross-tenant bug wearing a quota's clothes.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import Depends, FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from crossbid.auth import DEV_COMPANY_HEADER
from crossbid.ingestion.storage import DEFAULT_CONTENT_TYPE
from crossbid.main import create_app
from crossbid.rate_limit import (
    HOUR_SECONDS,
    LIMITER_STATE_KEY,
    Quota,
    RequestLimit,
    SlidingWindowLimiter,
    bid_start_limit,
    document_upload_limit,
    get_rate_limiter,
)
from crossbid.routers.bids import router as bids_router
from crossbid.routers.documents import (
    get_document_records,
    get_pipeline,
)
from crossbid.routers.documents import (
    router as documents_router,
)
from crossbid.settings import LimitsSettings, Settings
from tests.conftest import ORIGINAL_FILENAME, PDF_BYTES, Harness, harness

COMPANY = "11111111-1111-4111-8111-111111111111"
OTHER_COMPANY = "22222222-2222-4222-8222-222222222222"
AS_COMPANY = {DEV_COMPANY_HEADER: COMPANY}
AS_OTHER_COMPANY = {DEV_COMPANY_HEADER: OTHER_COMPANY}

MINUTE = 60.0
UPLOADS = "documents"
BIDS = "bids"


class Clock:
    """A monotonic clock a test moves by hand. Sleeping for a window would be an hour."""

    def __init__(self, start: float = 1_000.0) -> None:
        self._seconds = start

    def __call__(self) -> float:
        return self._seconds

    def advance(self, seconds: float) -> None:
        self._seconds += seconds


def limiter_at(clock: Clock, **kwargs: Any) -> SlidingWindowLimiter:
    return SlidingWindowLimiter(now=clock, **kwargs)


def quota(limit: int = 3, window_seconds: float = HOUR_SECONDS) -> Quota:
    return Quota(limit=limit, window_seconds=window_seconds)


# ------------------------------------------------------------------- the window itself


def test_every_call_under_the_limit_is_allowed() -> None:
    limiter = limiter_at(Clock())

    waits = [limiter.hit(scope=BIDS, key=COMPANY, quota=quota(limit=3)) for _ in range(3)]

    assert waits == [None, None, None]


def test_the_call_that_reaches_the_limit_is_refused() -> None:
    limiter = limiter_at(Clock())
    for _ in range(3):
        limiter.hit(scope=BIDS, key=COMPANY, quota=quota(limit=3))

    wait = limiter.hit(scope=BIDS, key=COMPANY, quota=quota(limit=3))

    assert wait == pytest.approx(HOUR_SECONDS)


def test_the_wait_counts_from_the_oldest_call_not_from_now() -> None:
    """The slot that frees next is the one the oldest call holds, so the answer shrinks."""
    clock = Clock()
    limiter = limiter_at(clock)
    limiter.hit(scope=BIDS, key=COMPANY, quota=quota(limit=1))

    clock.advance(20 * MINUTE)
    wait = limiter.hit(scope=BIDS, key=COMPANY, quota=quota(limit=1))

    assert wait == pytest.approx(HOUR_SECONDS - 20 * MINUTE)


def test_the_window_rolls_and_the_caller_is_unblocked() -> None:
    clock = Clock()
    limiter = limiter_at(clock)
    limiter.hit(scope=BIDS, key=COMPANY, quota=quota(limit=1))
    assert limiter.hit(scope=BIDS, key=COMPANY, quota=quota(limit=1)) is not None

    clock.advance(HOUR_SECONDS)

    assert limiter.hit(scope=BIDS, key=COMPANY, quota=quota(limit=1)) is None


def test_a_refused_call_does_not_extend_the_block() -> None:
    """Counting refusals would turn one impatient browser tab into an hour of lockout."""
    clock = Clock()
    limiter = limiter_at(clock)
    limiter.hit(scope=BIDS, key=COMPANY, quota=quota(limit=1))

    clock.advance(30 * MINUTE)
    limiter.hit(scope=BIDS, key=COMPANY, quota=quota(limit=1))  # refused, and not recorded
    clock.advance(30 * MINUTE)

    assert limiter.hit(scope=BIDS, key=COMPANY, quota=quota(limit=1)) is None


def test_two_companies_never_share_a_budget() -> None:
    """A counter keyed on anything but the tenant is a cross-tenant denial of service."""
    limiter = limiter_at(Clock())
    limiter.hit(scope=BIDS, key=COMPANY, quota=quota(limit=1))

    assert limiter.hit(scope=BIDS, key=COMPANY, quota=quota(limit=1)) is not None
    assert limiter.hit(scope=BIDS, key=OTHER_COMPANY, quota=quota(limit=1)) is None


def test_uploading_does_not_spend_the_budget_for_starting_a_bid() -> None:
    """The two routes cost different things, so they are limited by different numbers."""
    limiter = limiter_at(Clock())
    limiter.hit(scope=UPLOADS, key=COMPANY, quota=quota(limit=1))

    assert limiter.hit(scope=UPLOADS, key=COMPANY, quota=quota(limit=1)) is not None
    assert limiter.hit(scope=BIDS, key=COMPANY, quota=quota(limit=1)) is None


def test_idle_keys_are_swept_and_live_ones_are_kept() -> None:
    """Under dev auth every header value mints a key, so the map has to have a ceiling."""
    clock = Clock()
    limiter = limiter_at(clock, max_tracked_keys=2)
    for key in ("a", "b", "c"):
        limiter.hit(scope=BIDS, key=key, quota=quota(limit=5, window_seconds=MINUTE))
    assert limiter.tracked_keys == 3  # swept, but nothing had expired yet

    clock.advance(2 * MINUTE)
    limiter.hit(scope=BIDS, key="d", quota=quota(limit=5, window_seconds=MINUTE))

    assert limiter.tracked_keys == 1


# ----------------------------------------------------------------- the dependency, over HTTP


def settings_with(base: Settings, *, uploads: int = 100, bids: int = 100) -> Settings:
    limits = LimitsSettings(document_uploads_per_hour=uploads, bid_creations_per_hour=bids)
    return Settings(env=base.env, runtime=base.runtime.model_copy(update={"limits": limits}))


def app_spending(
    settings: Settings, limit: RequestLimit, limiter: SlidingWindowLimiter | None = None
) -> FastAPI:
    """The real app plus one throwaway route that does nothing but consume the quota."""
    app = create_app(settings)

    @app.post("/spend", dependencies=[Depends(limit)])
    async def spend() -> str:
        return "spent"

    if limiter is not None:
        app.dependency_overrides[get_rate_limiter] = lambda: limiter
    return app


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def spender(offline_settings: Settings, clock: Clock) -> Iterator[TestClient]:
    """One upload allowed per hour, on a clock the test controls."""
    settings = settings_with(offline_settings, uploads=1)
    app = app_spending(settings, document_upload_limit, limiter_at(clock))
    with TestClient(app) as client:
        yield client


def test_the_first_call_passes_and_the_next_is_429(spender: TestClient) -> None:
    assert spender.post("/spend", headers=AS_COMPANY).status_code == 200

    response = spender.post("/spend", headers=AS_COMPANY)

    assert response.status_code == 429


def test_the_429_carries_a_retry_after_of_sane_seconds(spender: TestClient) -> None:
    spender.post("/spend", headers=AS_COMPANY)

    response = spender.post("/spend", headers=AS_COMPANY)

    retry_after = int(response.headers["Retry-After"])
    assert 0 < retry_after <= HOUR_SECONDS
    assert retry_after == int(HOUR_SECONDS)


def test_the_detail_names_the_limit_and_when_to_come_back(spender: TestClient) -> None:
    spender.post("/spend", headers=AS_COMPANY)

    detail = spender.post("/spend", headers=AS_COMPANY).json()["detail"]

    assert "document uploads: at most 1 per hour" in detail
    assert "3600 seconds" in detail


def test_retry_after_rounds_a_part_second_up_rather_than_to_zero(
    spender: TestClient, clock: Clock
) -> None:
    """A client that obeys `Retry-After: 0` retries at once and is refused again."""
    spender.post("/spend", headers=AS_COMPANY)
    clock.advance(HOUR_SECONDS - 0.2)

    response = spender.post("/spend", headers=AS_COMPANY)

    assert response.headers["Retry-After"] == "1"


def test_the_window_rolls_over_http_too(spender: TestClient, clock: Clock) -> None:
    spender.post("/spend", headers=AS_COMPANY)
    assert spender.post("/spend", headers=AS_COMPANY).status_code == 429

    clock.advance(HOUR_SECONDS)

    assert spender.post("/spend", headers=AS_COMPANY).status_code == 200


def test_one_company_over_its_limit_does_not_block_another(spender: TestClient) -> None:
    spender.post("/spend", headers=AS_COMPANY)
    assert spender.post("/spend", headers=AS_COMPANY).status_code == 429

    assert spender.post("/spend", headers=AS_OTHER_COMPANY).status_code == 200


def test_an_unauthenticated_caller_is_401_and_is_never_counted(
    spender: TestClient, clock: Clock
) -> None:
    """`current_company` runs first, so a caller that proved nothing spends nobody's quota."""
    for _ in range(5):
        assert spender.post("/spend").status_code == 401

    assert spender.post("/spend", headers=AS_COMPANY).status_code == 200


def test_the_limit_is_read_from_the_settings_in_force(
    offline_settings: Settings, clock: Clock
) -> None:
    """Per request, not captured at import, so S4.6.2's override reaches it."""
    app = app_spending(
        settings_with(offline_settings, uploads=3), document_upload_limit, limiter_at(clock)
    )

    with TestClient(app) as client:
        codes = [client.post("/spend", headers=AS_COMPANY).status_code for _ in range(4)]

    assert codes == [200, 200, 200, 429]


def test_one_limiter_serves_every_request_of_an_app(offline_settings: Settings) -> None:
    """Counters on `app.state`, built on first use: a per-request limiter would count to one."""
    app = app_spending(settings_with(offline_settings, uploads=1), document_upload_limit)

    with TestClient(app) as client:
        assert getattr(client.app.state, LIMITER_STATE_KEY, None) is None
        assert client.post("/spend", headers=AS_COMPANY).status_code == 200
        built = getattr(client.app.state, LIMITER_STATE_KEY)
        assert client.post("/spend", headers=AS_COMPANY).status_code == 429
        assert getattr(client.app.state, LIMITER_STATE_KEY) is built


# -------------------------------------------------------------------------- the wiring


def route_for(router: Any, path: str, method: str) -> APIRoute:
    found = [
        route
        for route in router.routes
        if isinstance(route, APIRoute) and route.path == path and method in route.methods
    ]
    assert len(found) == 1, f"expected exactly one {method} {path}"
    return found[0]


@pytest.mark.parametrize(
    ("router", "path", "limit"),
    [
        (documents_router, "/documents", document_upload_limit),
        (bids_router, "/bids", bid_start_limit),
    ],
)
def test_the_spending_routes_declare_their_limit(
    router: Any, path: str, limit: RequestLimit
) -> None:
    """The identity, not merely "some dependency": the two limits read different settings."""
    declared = [depends.dependency for depends in route_for(router, path, "POST").dependencies]

    assert limit in declared


@pytest.fixture
def pipeline() -> Harness:
    return harness()


def test_a_real_upload_over_the_limit_is_refused(
    offline_settings: Settings, pipeline: Harness
) -> None:
    """End to end on the real route: the second upload of the hour is a 429, not a 202."""
    app = create_app(settings_with(offline_settings, uploads=1))
    app.dependency_overrides[get_pipeline] = lambda: pipeline.pipeline
    app.dependency_overrides[get_document_records] = lambda: pipeline.records

    with TestClient(app) as client:
        first = _upload(client)
        second = _upload(client)

    assert first.status_code == 202
    assert second.status_code == 429
    assert second.headers["Retry-After"] == str(int(HOUR_SECONDS))


def test_a_real_bid_over_the_limit_is_refused_before_anything_is_looked_up(
    offline_settings: Settings,
) -> None:
    """The app has no database, so an allowed call 503s — and the refused one still 429s.

    That ordering is the point: the limit is settled before the company, the documents or
    the runner are touched, so a caller over its quota costs a connection and nothing more.
    """
    with TestClient(create_app(settings_with(offline_settings, bids=1))) as client:
        first = _start_bid(client)
        second = _start_bid(client)

    assert first.status_code == 503
    assert second.status_code == 429


def _upload(client: TestClient) -> Any:
    return client.post(
        "/documents",
        files={"file": (ORIGINAL_FILENAME, PDF_BYTES, DEFAULT_CONTENT_TYPE)},
        data={"kind": "company_evidence"},
        headers=AS_COMPANY,
    )


def _start_bid(client: TestClient) -> Any:
    return client.post(
        "/bids",
        json={
            "notice_number": "123456-2026",
            "document_ids": [str(uuid.uuid4())],
            "source_language": "de",
        },
        headers=AS_COMPANY,
    )


# ------------------------------------------------------------------------- the defaults


def test_the_committed_defaults_bound_both_routes(offline_settings: Settings) -> None:
    """`settings.default.yaml` has to carry a number for each, or the story is not wired."""
    limits = offline_settings.runtime.limits

    assert limits.bid_creations_per_hour > 0
    assert limits.document_uploads_per_hour >= limits.bid_creations_per_hour


def test_a_limit_of_zero_is_refused_at_startup() -> None:
    """A quota of nothing would mean an operator typo silently closes the product."""
    with pytest.raises(ValueError, match="greater than 0"):
        LimitsSettings(document_uploads_per_hour=0, bid_creations_per_hour=1)


def test_the_default_clock_is_monotonic_and_needs_no_injection() -> None:
    """Production builds one with no arguments, and it must count from the first call."""
    limiter = SlidingWindowLimiter()

    assert limiter.hit(scope=BIDS, key=COMPANY, quota=quota(limit=1)) is None
    assert limiter.hit(scope=BIDS, key=COMPANY, quota=quota(limit=1)) == pytest.approx(
        HOUR_SECONDS, abs=1.0
    )
