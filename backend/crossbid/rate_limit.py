"""S2.3.3 — per-company limits on the routes that spend money.

`POST /documents`, `POST /bids` and `POST /bids/{id}/chat` are the routes that start real
work: an upload parses and embeds a whole pack, one bid run is about five minutes and $1.60
of OpenRouter (CLAUDE.md's measured figure for the DE pack), and a chat turn (S3.5.1) is a
short ReAct loop over a cheap model. Everything else reads a projection. That is why this is
a **dependency on those routes and not middleware over all of them**: the workspace polls
`GET /bids/{id}` every two seconds by design (S4.5.1), so a limiter in front of every route
would either throttle the poll or be set so high that it stops bounding the LLM bill — the
thing the story exists to bound.

Each route carries its own `scope` and its own number, because they cost different amounts
and an operator tightening one must not silently stop another: a bidder should not lose the
ability to ask what the matrix says because they uploaded a large pack this morning.

**Why not `guards/`.** That package is the *prompt* boundary, and its rule is that nothing
in it imports from the rest of `crossbid` (`test_wrap.py` asserts it), which is what lets
every prompt builder depend on it without a layering argument. A limiter is the *HTTP*
boundary: it needs `CompanyContext`, so it needs `auth`, and putting it in `guards/` would
spend that package's one invariant on an unrelated concern. It lives next to `auth.py`
instead — the other module whose whole job is answering "may this caller do this at all".

**The budget is per company, never per request, IP or user.** `company_id` is the tenant
every statement is already scoped by (ADR-0009) and the thing that holds a credit card. An
IP would put a shared office behind one budget and hand a botnet a fresh one per host. The
key is the `company_id` the *authenticated* dependency resolved, so a caller cannot choose
which budget to spend — under `AUTH_MODE=dev` that is still only as strong as the
`X-Dev-Company` header, which is exactly why `settings.py` refuses dev auth in production.

**A sliding window log, rather than a fixed window or a token bucket.** The limits are tens
of calls per hour, so the log is at most `limit` floats per company per route — small enough
that the exact algorithm costs nothing, which makes accuracy the only thing left to choose
on. A fixed window lets a caller spend the whole limit at 10:59 and the whole limit again at
11:01, which is two hours' LLM budget in two minutes; it also cannot say more than "wait
until the window ends". A token bucket fixes the boundary but turns "10 per hour" into a
drip the operator has to translate. The log keeps the promise the setting's name makes, and
`Retry-After` is then a fact rather than an estimate: the oldest call in the window is the
one whose expiry frees the next slot, so the answer is the second it leaves.

**A refused call is not recorded.** Only accepted calls enter the window. Counting refusals
would let a client that keeps retrying extend its own block indefinitely, turning one
mistake in a browser tab into an hour of lockout.

**What this cannot promise, stated plainly.** The counters are a dictionary in this process.
Two uvicorn workers are two dictionaries, so the effective limit is `workers x limit` and a
caller that lands on a different worker each time sees the highest multiple of it; a restart
forgets every window. It is a bound on runaway spend from one account, not a quota anybody
could bill against, and it is deliberately not Redis: a second piece of infrastructure to
deploy, monitor and fail over is a poor trade for a course build whose deployment is one
container. Set the defaults for the worst honest case — `workers x limit` still inside what
the operator can pay — or move the counters to a shared store before scaling out. The
project plan named `slowapi` for this; it is the same in-process design with a dependency
and a decorator, and it does not make the multi-process caveat go away.

**The 429 is deliberately not in the OpenAPI schema.** `frontend/lib/api.ts` is generated
from that schema and CI fails when it is stale, so declaring a `429` response here would be
a frontend change wearing a backend commit. Nothing is lost: the status and `Retry-After`
are HTTP's own, and `lib/use-polling.ts` reads a status code rather than a generated union.
Declare it when the browser is taught to show the wait, and regenerate the client with it.

**Concurrency.** `hit` reads and writes without awaiting, and the only caller is an `async`
dependency, so the event loop cannot interleave two of them inside the critical section. One
loop per process is what uvicorn runs; a second loop in the same process would need a lock,
and would already have the multi-process caveat above.
"""

from __future__ import annotations

import math
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from fastapi import Depends, HTTPException, Request, status

from crossbid.auth import CompanyContext, current_company
from crossbid.main import get_app_settings
from crossbid.settings import LimitsSettings, Settings

HOUR_SECONDS: Final = 3600.0
"""The window, fixed rather than configured. The acceptance criterion and both setting
names say "per hour"; a configurable window would make those names a lie in any deployment
that changed it, and nothing so far wants a different one."""

LIMITER_STATE_KEY: Final = "rate_limiter"
"""Where the process's limiter hangs off `app.state`, as `bid_runner` and `token_verifier`
do. Per app rather than per module, so a test's app starts with empty counters."""

MAX_TRACKED_KEYS: Final = 10_000
"""Keys held before idle ones are swept. Every distinct company that calls one of the two
routes creates an entry, and under `AUTH_MODE=dev` the company is whatever the header said,
so without a sweep the map is a memory leak an unauthenticated caller can drive. 10 000
entries of a few dozen floats is well under a megabyte, which is the point: sweep late and
rarely rather than on a timer."""

MIN_RETRY_AFTER_SECONDS: Final = 1
"""`Retry-After` is whole seconds (RFC 9110 §10.2.3). A remaining 0.2 s rounds up rather
than down: a client that obeys a `0` retries immediately and is refused again."""


@dataclass(frozen=True, slots=True)
class Quota:
    """How many calls fit in a window. Built per request from the settings in force."""

    limit: int
    window_seconds: float


class SlidingWindowLimiter:
    """Accepted-call timestamps per (route, company), pruned on the way past.

    `now` is injected so tests can roll a window without sleeping; production uses
    `time.monotonic`, which is immune to the clock being set backwards — a wall clock
    correction of an hour would otherwise forgive every window at once.
    """

    def __init__(
        self,
        *,
        now: Callable[[], float] = time.monotonic,
        max_tracked_keys: int = MAX_TRACKED_KEYS,
    ) -> None:
        self._now = now
        self._max_tracked_keys = max_tracked_keys
        self._calls: dict[tuple[str, str], deque[float]] = {}
        self._longest_window = 0.0

    def hit(self, *, scope: str, key: str, quota: Quota) -> float | None:
        """Record one accepted call, or return the seconds to wait when the quota is spent.

        `scope` separates the routes so that uploading a pack never eats the budget for
        starting a bid: the two cost different things and are limited by different numbers.
        """
        now = self._now()
        self._longest_window = max(self._longest_window, quota.window_seconds)
        window = self._calls.setdefault((scope, key), deque())

        cutoff = now - quota.window_seconds
        while window and window[0] <= cutoff:
            window.popleft()

        if len(window) >= quota.limit:
            # The oldest call still in the window is the one whose expiry frees a slot.
            return window[0] + quota.window_seconds - now

        window.append(now)
        if len(self._calls) > self._max_tracked_keys:
            self._sweep(now)
        return None

    def _sweep(self, now: float) -> None:
        """Drop keys whose newest call is older than any window this limiter serves.

        Rebuilt rather than mutated, so a caller holding a `deque` cannot see it emptied
        underneath them. A deque is never empty here: `hit` either appends to it or refuses
        with it full, so `[-1]` is the last accepted call and nothing else.
        """
        cutoff = now - self._longest_window
        self._calls = {
            key: window for key, window in self._calls.items() if window[-1] > cutoff
        }

    @property
    def tracked_keys(self) -> int:
        """How many (route, company) pairs are held. For the sweep's test, and for a log."""
        return len(self._calls)


def get_rate_limiter(request: Request) -> SlidingWindowLimiter:
    """One limiter per app, so every request in a process shares the same counters.

    Built on first use rather than in the lifespan: a limiter with no database and no
    configuration has nothing to fail at startup, and `create_app` is also what the OpenAPI
    generation boots with nothing behind it.
    """
    limiter: SlidingWindowLimiter | None = getattr(request.app.state, LIMITER_STATE_KEY, None)
    if limiter is None:
        limiter = SlidingWindowLimiter()
        setattr(request.app.state, LIMITER_STATE_KEY, limiter)
    return limiter


class RequestLimit:
    """One route's quota, ready to hang off it as `dependencies=[Depends(...)]`.

    A callable object rather than a closure so that the two instances below are importable
    identities: a test can assert that *this* limit is the one the route declares, which is
    the only cheap way to pin the wiring without driving the whole upload pipeline.
    """

    def __init__(
        self, *, scope: str, noun: str, limit_of: Callable[[LimitsSettings], int]
    ) -> None:
        self._scope = scope
        self._noun = noun
        self._limit_of = limit_of

    async def __call__(
        self,
        company: CompanyContext = Depends(current_company),
        settings: Settings = Depends(get_app_settings),
        limiter: SlidingWindowLimiter = Depends(get_rate_limiter),
    ) -> None:
        """Let the call through, or raise the 429 that says when to come back.

        The limit is read from the settings *per request*, not captured at import, so the
        developer panel's `app_settings` override (S4.6.2) reaches it the same way a model
        slug does. `current_company` runs first, so an unauthenticated caller still gets a
        401 rather than being counted against a company it did not prove it is.
        """
        quota = Quota(
            limit=self._limit_of(settings.runtime.limits), window_seconds=HOUR_SECONDS
        )
        wait = limiter.hit(scope=self._scope, key=company.company_id, quota=quota)
        if wait is None:
            return
        retry_after = max(MIN_RETRY_AFTER_SECONDS, math.ceil(wait))
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Rate limit reached for {self._noun}: at most {quota.limit} per hour for "
                f"one company. Try again in {retry_after} seconds — nothing you have "
                f"already uploaded or started is affected."
            ),
            headers={"Retry-After": str(retry_after)},
        )


document_upload_limit: Final = RequestLimit(
    scope="documents",
    noun="document uploads",
    limit_of=lambda limits: limits.document_uploads_per_hour,
)
"""`POST /documents`. Counted before the body is read, so an oversized upload from a caller
over its limit costs the server nothing; a file refused as a non-PDF still counts, because
the alternative is a free retry loop that only has to guess a valid header to get through."""

bid_start_limit: Final = RequestLimit(
    scope="bids",
    noun="bids started",
    limit_of=lambda limits: limits.bid_creations_per_hour,
)
"""`POST /bids`. The expensive one: this is the number that bounds the LLM bill."""

chat_question_limit: Final = RequestLimit(
    scope="chat",
    noun="questions asked about a bid",
    limit_of=lambda limits: limits.chat_questions_per_hour,
)
"""`POST /bids/{id}/chat` (S3.5.1). Its own scope, so a busy afternoon of questions can
never consume the budget for starting the bid they are about — and the other way round."""
