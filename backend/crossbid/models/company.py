"""Facts the bidder controls, checked against what a tender demands.

The bidder owns these — the agent never infers them from documents (LLM profile extraction was
cut from scope). Turnover and headcount are typed as numbers so the scorer can compare them
with a `Threshold` rather than asking a model to judge.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

COUNTRY_PATTERN: Final = r"^[a-z]{2}$"
"""`companies.country`'s check constraint, restated so Pydantic refuses what Postgres would.

Mirrored by hand rather than derived: `migrations/0001_init.sql` is applied by a script that
never imports this package, so the regex has to be written twice. `test_migrations.py` reads
the constraint out of the SQL and compares the two texts, next to the enum parity checks that
do the same job for the check-constraint columns.
"""


class LegalForm(StrEnum):
    """Common EU legal forms. `OTHER` keeps the enum closed without losing real companies."""

    GMBH = "gmbh"
    UG = "ug"
    AG = "ag"
    SARL = "sarl"
    SAS = "sas"
    SA = "sa"
    BV = "bv"
    SP_ZOO = "sp_zoo"
    SOLE_TRADER = "sole_trader"
    OTHER = "other"


class Tone(StrEnum):
    """How explanations are written. Graded Easy 2 (personality / tone)."""

    PLAIN = "plain"
    FORMAL = "formal"
    BRIEF = "brief"


class CertificateHeld(BaseModel):
    """A certificate the company holds, with the expiry the matrix must respect.

    An expired certificate is not evidence, which is why `expires_on` is not optional
    decoration: `GET /companies/me` flags it on the profile form, and `agent/flags.py` warns
    on any matrix row that cites one (S3.4.4).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(description="e.g. 'ISO/IEC 27001:2022'")
    issuer: str | None = None
    number: str | None = None
    issued_on: date | None = None
    expires_on: date | None = None
    scope: str | None = Field(default=None, description="What the certificate actually covers")

    def is_valid_on(self, when: date) -> bool:
        """No expiry recorded means we cannot claim validity, so this returns False."""
        if self.expires_on is None:
            return False
        return self.expires_on >= when

    def is_expired_on(self, when: date) -> bool:
        """Expired, which is **not** the negation of `is_valid_on`.

        A certificate with no recorded expiry is neither valid nor expired: the profile
        cannot claim validity without a date, and it cannot claim lapse either. Keeping the
        two as separate questions is what lets `GET /companies/me` warn about the first
        group and S3.4.4 flag only the second — a row cited by an undated certificate is not
        a row to warn a reviewer about.
        """
        return self.expires_on is not None and self.expires_on < when


class TurnoverYear(BaseModel):
    """One fiscal year's turnover in the contract's field of activity.

    Tenders ask for the last three years in *the field of the contract*, not total revenue,
    so `field_of_activity` is part of the fact.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    year: int = Field(ge=1900, le=2200)
    amount: float = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3, description="ISO 4217")
    field_of_activity: str | None = None


class CompanyProfile(BaseModel):
    """The bidder, as the matrix sees them."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    country: str = Field(
        pattern=COUNTRY_PATTERN,
        description=(
            "ISO 3166-1 alpha-2, lower case. The pattern is `companies.country`'s own check "
            "constraint, so the same value the column would refuse is refused here — as a "
            "422 naming the field rather than a CheckViolation surfacing as a 500. 'DE' is "
            "rejected, not lower-cased: a PUT that rewrote its own body would answer with "
            "something the caller never sent, and the pattern reaches the generated client, "
            "so the form can say so before the request leaves the browser."
        ),
    )
    legal_form: LegalForm
    registration_number: str | None = Field(default=None, description="e.g. 'HRB 84512'")
    registration_court: str | None = None

    language: str = Field(default="de", min_length=2, max_length=5, description="BCP 47")
    tone: Tone = Tone.PLAIN

    staff_fte: float | None = Field(
        default=None, ge=0, description="Total full-time equivalents"
    )
    staff_fte_relevant: float | None = Field(
        default=None,
        ge=0,
        description="FTE in the field of the contract, which is what tenders ask for",
    )
    turnover: tuple[TurnoverYear, ...] = ()
    certificates: tuple[CertificateHeld, ...] = ()
