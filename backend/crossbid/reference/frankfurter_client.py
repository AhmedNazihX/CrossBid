"""S1.3.1 — the ECB's reference rate for one currency pair, and what to serve when it is gone.

Frankfurter (`api.frankfurter.dev`) republishes central-bank reference rates as JSON. Public,
no key, no quota. Everything below was probed live on 2026-09-14; the parts that surprised us
are the parts worth writing down.

**The endpoint is `GET /v2/providers/ECB/rate/{base}/{quote}`, and the `providers/ECB` prefix
is load-bearing.** The API's root document calls v1 `frozen` and v2 `current`, and v1 answers
with a `deprecation` header pointing at v2 — so v2 it is. But v2's plain `/v2/rate/{base}/
{quote}` returns a *blend* of ~100 central banks (PLN→EUR came back 0.23069), while the story
asks for the ECB rate, which a European buyer's threshold is actually denominated in. Pinning
the provider in the path returns 0.23032 — byte-identical to what the frozen v1 endpoint
serves, which is the evidence that the prefix selects the ECB alone rather than a blend that
happens to include it.

**The answer is one flat object**, e.g. `{"date": "2026-09-14", "base": "PLN", "quote":
"EUR", "rate": 0.23032}` — no envelope, no nesting. `date` is the day the ECB published the
rate, not today: asked on a Monday for a weekend date it answers with the Friday, which is
why `rate_date` is returned to the bidder rather than assumed to be the day of the call.

**A rate arrives rounded to what the ECB publishes** (five or so significant figures), so the
converted amount is `amount * rate` on that published figure and nothing more precise is
available to us. That is the right number to show anyway: it is the one a bidder can
reproduce from the two fields printed beside it.

**404 and 422 are not outages.** `XXX` (not a currency at all) is `422 invalid currency: XXX`;
`AFN` (a real currency the ECB does not quote) is `404 not found`. Neither is retryable and
neither can be papered over with a cached rate, so they raise `UnknownCurrencyPairError`,
separately from the `RateUnavailableError` that means "the service is down". A tool that
merged the two would tell a bidder to try again later about a currency that will never exist.

**Where the cache lives, and why there.** `RATE_CACHE` is a module-level object, so the last
good rate per pair survives for the life of the API process and no longer.

* *Not on the client instance*, because there would be nothing left to cache: like
  `search_ted`, the tool builds a fresh client (and a fresh `httpx.Client`) per call, so an
  instance-scoped cache would be empty every single time and the story's second criterion
  could never be met.
* *Not in Postgres*, because a reference rate is not a tenant's fact. It would need a table,
  a migration and an answer to "whose rate is this?" for a public number that is identical
  for every company — and the story asks for a fallback for one failing call, not for a rate
  history. The cost of the in-process choice is stated plainly in the tool: a process that
  has never reached Frankfurter has nothing to fall back on and says `unavailable` rather
  than inventing a rate.
* *Unbounded on purpose*: the key space is the pairs the ECB publishes against the euro,
  which is about thirty. There is nothing here to evict.
* *Unlocked on purpose*: the only write is rebinding one dict key to a frozen record, which
  is atomic under CPython, and the worst interleaving is two concurrent successes for the
  same pair where one wins — both being correct answers for the same day.

Cached records are never mutated. `rate()` returns `model_copy(update={"stale": True})`, so
the flag describes *this* answer and the remembered rate stays what it was when it was good.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from datetime import date
from typing import Annotated, Any, Final

import httpx
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

logger = logging.getLogger(__name__)

RATE_URL_TEMPLATE: Final = "https://api.frankfurter.dev/v2/providers/ECB/rate/{base}/{quote}"
"""The ECB alone, not the multi-provider blend. See the module docstring."""

REQUEST_TIMEOUT_S: Final = 10.0
"""Half of TED's: this is one CDN-cached object of about seventy bytes, and a tool call that
hangs is a per-requirement ReAct loop that hangs."""

MAX_ATTEMPTS: Final = 2
"""One retry, matching `ted_client`. A rate that is down twice in a row is down."""

NOT_A_PUBLISHED_PAIR: Final = frozenset({404, 422})
"""Statuses that mean "the ECB does not quote this", which no retry and no cache can fix."""

_CURRENCY_CODE: Final = re.compile(r"^[A-Za-z]{3}$")
"""Checked before a code is interpolated into the URL *path*, so a code carrying `../` can
never walk out of the endpoint it was meant for. That it also catches typos is secondary."""

CurrencyCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
"""ISO 4217, upper case by the time it reaches a model: the API echoes codes upper-cased
whatever it was asked, and one casing in the answer means no caller has to fold it."""


class RateUnavailableError(RuntimeError):
    """Frankfurter could not be reached, or answered with something unusable, and no rate for
    the pair was ever cached. Distinct from `UnknownCurrencyPairError` because "try later" and
    "that pair does not exist" are different things to tell a bidder."""


class UnknownCurrencyPairError(ValueError):
    """The ECB does not publish this pair — a bad code, or a currency it does not quote. A
    `ValueError` rather than a runtime failure: the input is wrong, not the service."""


class ExchangeRate(BaseModel):
    """One rate as published, and whether it is today's.

    `rate_date` is the ECB's publication date, which on a Monday is usually Friday's — the
    bidder is shown it rather than being left to assume the rate is of the moment.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    base: CurrencyCode
    quote: CurrencyCode
    rate: float = Field(gt=0)
    """Units of `quote` for one unit of `base`. `gt=0` because a zero or negative rate is not
    a rate, and dividing a threshold by one would be worse than refusing it."""
    rate_date: date
    stale: bool = False
    """True only when this came out of the cache because the service was unreachable. The
    date says how stale; this says that it is."""


class RateCache:
    """The last good rate per pair. One instance is the process's; tests make their own.

    Deliberately tiny: remember and read back, no expiry and no eviction. Expiry would mean
    choosing how old is too old, and the honest answer is that a bidder reading `rate_date`
    decides that far better than a constant in here can.
    """

    def __init__(self) -> None:
        self._rates: dict[tuple[str, str], ExchangeRate] = {}

    def remember(self, rate: ExchangeRate) -> None:
        """Replace the entry for this pair. Only ever called with a rate fetched live."""
        self._rates[(rate.base, rate.quote)] = rate

    def last_good(self, base: str, quote: str) -> ExchangeRate | None:
        """The rate as it was remembered — not marked stale here.

        Staleness is the *caller's* observation: this object does not know whether the live
        call just failed, and a cache that pre-flagged its contents would be asserting
        something it cannot see.
        """
        return self._rates.get((base.upper(), quote.upper()))


RATE_CACHE: Final = RateCache()
"""The process-wide cache. See the module docstring for why it is here and not on a client."""


class FrankfurterClient:
    """Reads one rate at a time. Construct with an `httpx.Client`; a test passes a
    `MockTransport`.

    `cache` defaults to the module singleton rather than to `None`-then-fallback, because the
    shared cache *is* the intended default and a per-instance one would never be warm. A test
    passes its own so that one test's rate cannot answer another's.
    """

    def __init__(
        self,
        http: httpx.Client,
        *,
        max_attempts: int = MAX_ATTEMPTS,
        cache: RateCache = RATE_CACHE,
    ) -> None:
        self._http = http
        self._max_attempts = max_attempts
        self._cache = cache

    def rate(self, base: str, quote: str) -> ExchangeRate:
        """Today's published rate, or the last good one marked `stale` when the service is
        down.

        The story's second criterion lives here. An unknown pair is *not* caught: a cached
        rate cannot make a currency exist, and if the ECB stops quoting one, saying so beats
        serving last week's number forever.
        """
        pair = (_checked(base), _checked(quote))
        try:
            fresh = self._fetch(*pair)
        except RateUnavailableError:
            cached = self._cache.last_good(*pair)
            if cached is None:
                raise
            logger.warning(
                "Frankfurter is unreachable; serving the cached %s/%s rate of %s",
                *pair,
                cached.rate_date.isoformat(),
            )
            return cached.model_copy(update={"stale": True})
        self._cache.remember(fresh)
        return fresh

    def _fetch(self, base: str, quote: str) -> ExchangeRate:
        """One live rate, retried once on a transport or server failure."""
        url = RATE_URL_TEMPLATE.format(base=base, quote=quote)
        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = self._http.get(url)
                response.raise_for_status()
            except httpx.HTTPError as error:
                _refuse_unpublished_pair(error, base, quote)
                last_error = error
                logger.warning("Frankfurter attempt %s for %s failed: %s", attempt, url, error)
            else:
                return _parsed(_decoded(response), base, quote)
        raise RateUnavailableError(
            f"Frankfurter failed after {self._max_attempts} attempts: {last_error}"
        ) from last_error


def _checked(code: str) -> str:
    """An upper-cased ISO 4217 code, or a refusal before anything is interpolated into a URL."""
    if not _CURRENCY_CODE.match(code.strip()):
        raise UnknownCurrencyPairError(f"{code!r} is not a three-letter currency code")
    return code.strip().upper()


def _refuse_unpublished_pair(error: httpx.HTTPError, base: str, quote: str) -> None:
    """Turn a 404 or a 422 into the typed refusal, and let every other failure be retried.

    Peeled out of the loop rather than checked inline because it is the one failure that must
    *not* go round again: the pair does not exist, so a second identical request would only
    cost a bidder another second before the same answer.
    """
    status = error.response.status_code if isinstance(error, httpx.HTTPStatusError) else None
    if status in NOT_A_PUBLISHED_PAIR:
        raise UnknownCurrencyPairError(
            f"the ECB publishes no {base}/{quote} rate (HTTP {status})"
        ) from error


def _decoded(response: httpx.Response) -> Any:
    """The JSON body, or a typed failure. A gateway's HTML error page lands here."""
    try:
        return response.json()
    except ValueError as error:
        raise RateUnavailableError(
            "Frankfurter answered with something that is not JSON"
        ) from error


def _parsed(decoded: Any, base: str, quote: str) -> ExchangeRate:
    """The flat body as a rate, checked against the pair that was asked for.

    The echo check is the one that matters: a proxy or a future routing change that answered
    with a *different* pair's rate would otherwise be applied to the bidder's amount under our
    own label — a wrong number no reviewer could spot, which is the failure mode worth two
    lines here. Everything else is ordinary boundary validation.
    """
    if not isinstance(decoded, Mapping):
        raise RateUnavailableError("Frankfurter answered with a body that is not an object")
    echoed = (str(decoded.get("base", "")).upper(), str(decoded.get("quote", "")).upper())
    if echoed != (base, quote):
        raise RateUnavailableError(
            f"asked Frankfurter for {base}/{quote} and it answered about "
            f"{echoed[0]}/{echoed[1]}"
        )
    try:
        return ExchangeRate(
            base=base,
            quote=quote,
            rate=float(decoded["rate"]),
            rate_date=date.fromisoformat(str(decoded["date"])),
        )
    except (KeyError, TypeError, ValueError, ValidationError) as error:
        raise RateUnavailableError(
            f"Frankfurter sent a rate this client cannot read: {error}"
        ) from error
