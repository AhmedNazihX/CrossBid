"""`currency_convert` — a threshold in zloty against a company that counts in euro (S1.3.1).

The requirement a bidder trips over is the one that reads "annual turnover of at least
2 000 000 PLN". The company profile carries euro, the tender carries the buyer's currency,
and `agent/scoring.py` refuses to compare two amounts that are not in the same one — so
without this tool that requirement can only ever be `insufficient_evidence`. This is the
conversion that makes it answerable.

**`external=True`, and it is enabled by default because `settings.default.yaml` lists it**;
the manifest describes the file, not this process's configuration (see `ToolManifest`). It
is the second of the five tools that opens a socket, and an operator who wants a run that
cannot stall on a third party has the panel to turn it off.

**Three statuses, because there are three genuinely different answers.** `ok` — a rate, and
`stale` says whether it is today's. `unknown_currency` — the ECB does not quote this pair,
which no retry will change, so the model should stop asking rather than back off. Both
`unavailable` and a stale `ok` exist because "we could not reach the service at all" and
"here is Friday's rate" are worth different amounts to a bidder sizing a bid bond.

**The converted amount is `amount * rate`, rounded to cents, and the rate and its date are
returned beside it.** That is the whole citation: a reviewer can redo the arithmetic from
what is on the row, which is the same standard every other cell on the matrix is held to.

**The currency codes are a pattern, not an enum** — unlike `ecertis_evidence_lookup`, whose
criterion ids come from a Literal generated out of the committed cache. The ECB's list is
live data (it has both added and dropped currencies), so a Literal here would be a stale
copy that refused a real currency at the schema, before the service could be asked. A code
the ECB does not quote comes back as `unknown_currency` instead, which is the honest shape
of that answer.
"""

from __future__ import annotations

from typing import Annotated, Any

import httpx
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from crossbid.reference.frankfurter_client import (
    FRANKFURTER_REQUEST_TIMEOUT_S,
    ExchangeRate,
    FrankfurterClient,
    RateUnavailableError,
    UnknownCurrencyPairError,
)
from crossbid.tools import ToolContext, ToolManifest

CurrencyArg = Annotated[str, StringConstraints(pattern=r"^[A-Za-z]{3}$")]

EURO = "EUR"
"""The default target: every threshold on the matrix is compared in euro, because that is
what the company profile's turnover is recorded in."""

MONEY_PLACES = 2
"""Cents. Rounding further would imply a precision the published rate does not carry."""

DESCRIPTION = """\
Convert a money amount from one currency to another at the European Central Bank's \
reference rate.

Use this whenever a tender states a threshold, a turnover requirement or a bid bond in a \
currency other than the one the company's figures are in — a Polish tender asking for \
2 000 000 PLN of annual turnover against a company that reports in euro, for example. \
Comparing the two numbers without converting them is meaningless.

Give the amount as a number, and the currencies as three-letter ISO 4217 codes (PLN, CZK, \
HUF, RON, SEK, DKK, NOK, CHF, GBP, USD and about twenty more). The target defaults to EUR.

The answer carries the converted amount, the exact rate used and the date the ECB published \
it, so the figure can be checked. It also carries "stale": when true, the rate service was \
unreachable and the last rate this process saw was used instead — say so if the number \
decides anything.

Status "unknown_currency" means the ECB does not publish that pair; do not retry it with \
the same codes. Status "unavailable" means the rate service could not be reached and \
nothing was cached to fall back on — the amounts cannot be compared, and that is a reason \
for partial support, not for a guess.\
"""


MANIFEST = ToolManifest(
    name="currency_convert",
    description=DESCRIPTION,
    external=True,
    default_enabled=True,
)


class CurrencyConvertArgs(BaseModel):
    """What the model must supply. `from` is a Python keyword, hence `from_currency`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    amount: float = Field(
        gt=0,
        description="The amount to convert, as stated in the tender (e.g. 2000000).",
    )
    from_currency: CurrencyArg = Field(
        description="The currency the amount is stated in, ISO 4217 (e.g. 'PLN')."
    )
    to_currency: CurrencyArg = Field(
        default=EURO,
        description="The currency to convert into, ISO 4217. Defaults to EUR.",
    )


def build_tool(context: ToolContext) -> BaseTool:
    """The bound tool. `context` is unused: an ECB rate is the same for every tenant."""
    del context

    def run(amount: float, from_currency: str, to_currency: str = EURO) -> dict[str, Any]:
        # Closed on the way out (M22). This is the worst of the four leaks the audit found:
        # the tool is built per call inside a loop that runs once per requirement, so a
        # 350-requirement pack left 350 connection pools to the garbage collector.
        try:
            with httpx.Client(timeout=FRANKFURTER_REQUEST_TIMEOUT_S) as http:
                rate = FrankfurterClient(http).rate(from_currency, to_currency)
        except UnknownCurrencyPairError as error:
            return {"status": "unknown_currency", "detail": str(error)}
        except RateUnavailableError as error:
            # Total, like every tool the ReAct loop calls: a third party being down must not
            # end a run that has already cost money (S3.3.1's rule for `ecertis_evidence`).
            return {"status": "unavailable", "detail": str(error)}
        return _converted(amount, rate)

    return StructuredTool.from_function(
        func=run,
        name=MANIFEST.name,
        description=MANIFEST.description,
        args_schema=CurrencyConvertArgs,
    )


def _converted(amount: float, rate: ExchangeRate) -> dict[str, Any]:
    """The answer, with everything a reviewer needs to redo the sum by hand."""
    return {
        "status": "ok",
        "amount": amount,
        "from": rate.base,
        "to": rate.quote,
        "converted": round(amount * rate.rate, MONEY_PLACES),
        "rate": rate.rate,
        "rate_date": rate.rate_date.isoformat(),
        "stale": rate.stale,
    }
