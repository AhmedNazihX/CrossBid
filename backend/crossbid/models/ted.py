"""What a TED search asks for and what it answers (story S1.2.1).

TED's own JSON is not a shape a screen can render: a title arrives as a mapping of 24
language codes, a buyer as a mapping of language codes to *lists*, a deadline as a list with
one entry per lot, and a country as a three-letter code. These models are the shape after
that has been resolved, so a router, a tool and a React table all read the same thing and
the resolution rules live in exactly one place (`reference/ted_client.py`).

Everything here is verified against the live API rather than against documentation — the
notes in `CLAUDE.md` under *TED Search API v3* record what a query may and may not say, and
every constraint below traces to one of them.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

CPV_LENGTH: Final = 8
"""A CPV value must be the full eight digits: `IN (72)` is HTTP 400
`QUERY_UNSUPPORTED_FIELD_VALUE`, `IN (72000000)` matches. Probed 2026-09-14."""

MAX_RESULTS_PER_PAGE: Final = 100
MAX_REACHABLE_RESULTS: Final = 600
"""Pagination stops here: `limit=100, page=7` is HTTP 400 even when `totalNoticeCount` is
far higher. Narrowing the query is the only way past it, so the answer says so rather than
offering a page that cannot be fetched."""

CONTRACT_NOTICE_TYPE: Final = "cn-standard"
"""The notice type a bidder acts on. Deadline fill rate is **84 %** here against 44 % across
a mixed sample — award notices have no deadline by nature, so filtering by type first is
what makes a coverage figure mean anything."""

Cpv = Annotated[str, StringConstraints(pattern=r"^\d{8}$")]
Alpha2 = Annotated[str, StringConstraints(pattern=r"^[a-z]{2}$")]


class TedSearchQuery(BaseModel):
    """What the bidder is looking for, before it becomes expert-query syntax."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    cpv: tuple[Cpv, ...] = Field(
        default=(),
        description="CPV codes, full eight digits. Several are a union, never an `OR`.",
    )
    countries: tuple[Alpha2, ...] = Field(
        default=(),
        description=(
            "Where the contract is performed, ISO 3166-1 alpha-2 as the rest of the app "
            "writes it."
        ),
    )
    keyword: str | None = Field(
        default=None,
        description=(
            "Free text, matched across the notice. One phrase, not a boolean expression."
        ),
    )
    contract_notices_only: bool = Field(
        default=True,
        description=(
            "Restrict to `cn-standard`. On by default: the others are award and prior "
            "information notices, which a bidder cannot act on and which carry no deadline."
        ),
    )
    limit: int = Field(default=20, ge=1, le=MAX_RESULTS_PER_PAGE)
    page: int = Field(default=1, ge=1)


class TedNotice(BaseModel):
    """One published notice, with every language-keyed field already resolved."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    publication_number: str = Field(description="TED's own id, e.g. '629621-2026'")
    title: str = Field(
        description="The notice title, in the bidder's language where TED has one"
    )
    buyer: str | None = Field(
        description="The contracting authority, or null when the notice names none"
    )
    buyer_countries: tuple[str, ...] = Field(
        default=(),
        description=(
            "Where the contracting authority sits, ISO 3166-1 alpha-3 exactly as TED writes "
            "it, deduplicated. **Not the same thing as the country searched on**, which is "
            "`place-of-performance`: a pan-European framework is performed in France and "
            "bought in London, and answers a France search honestly (ADR-0111). Verbatim "
            "rather than mapped to alpha-2, because a non-EU buyer has no alpha-2 here."
        ),
    )
    description: str | None = Field(
        description="The procedure's own summary, in its source language"
    )
    deadline: date | None = Field(
        description=(
            "The earliest lot deadline. A DATE and never a time: across 58 sampled lot "
            "deadlines not one carried an hour, so the hour comes from the notice PDF or "
            "from the bidder (S4.4.1), never from here."
        )
    )
    deadline_utc_offset_minutes: int | None = Field(
        description="The offset TED published with that date, which is the buyer's wall clock."
    )
    official_languages: tuple[str, ...] = Field(description="ISO 639-3, as TED writes them")
    submission_languages: tuple[str, ...] = Field(
        description="Languages a tender may be submitted in"
    )
    cpv: tuple[str, ...] = Field(description="CPV codes on the notice, deduplicated")
    selection_criteria: tuple[str, ...] = Field(
        default=(),
        description=(
            "The selection criteria the buyer stated on the notice, in the notice's own "
            "language. Empty on most notices — populated on 14-17 % of CPV-72 ones, which "
            "is the measurement the upload-the-pack design rests on (S3.2.2)."
        ),
    )
    notice_pdf_url: str | None = Field(
        description="The notice as published, in its own language. S1.2.2 opens this."
    )
    documents_url: str | None = Field(
        description=(
            "The national platform hosting the procurement documents. Almost never TED "
            "itself, which is why the bidder uploads the pack by hand (no-scraping rule)."
        )
    )
    published_on: date | None = None


class TedSearchPage(BaseModel):
    """One page of results, and enough context to know what is not on it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    notices: tuple[TedNotice, ...]
    total: int = Field(
        description="What TED says matched, which may exceed what can be paged to"
    )
    page: int
    limit: int
    reachable_total: int = Field(
        description=(
            f"Results actually fetchable: `min(total, {MAX_REACHABLE_RESULTS})`. TED refuses "
            "to page beyond that, so a screen offering more would offer a 400."
        )
    )
