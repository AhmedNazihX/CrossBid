"""S3.4.4 — the notices a reviewer must not have to work out for themselves.

Two of the story's resilience criteria are not about surviving a failure at all. They are
about a row that came back looking settled while something about it needs a human's eye:

* **no eCertis entry.** The requirement maps to an EU criterion and eCertis records no
  national document for this bidder's country. Normal for many criteria — France has none for
  17 of the 56 (ADR-0007) — and it means the cross-border mapping, the product's whole wedge,
  had nothing to say about this row. `check_loop` already tells the *model* so; nobody told
  the reviewer.
* **an expired certificate used as evidence.** The bidder's own profile records when each
  certificate lapses, and a row citing a document that is one of them is citing something
  that has stopped being proof.

Pure, and applied once — by `score_verdict`, which already holds the profile and every row.
Three decisions.

**1. The warning goes in `agent_rationale`, not in a new column.** The reviewer reads the
rationale beside the row; a boolean in the database that no screen renders is not a flag. It
also needs no migration, and it follows the pattern `check_loop` already set: a notice is
appended and the model's own sentence gives way to it, never the other way round. The revised
row is rebuilt through `MatrixRow.model_validate` rather than `model_copy(update=...)`, for
the reason `nodes/review.py` gives at length: the copy skips validation, and two modules
revising the same model must not disagree about whether that is allowed.

**2. Nothing is downgraded.** The status stays exactly as checking left it. The story asks
for a warning, and the product is advisory: a reviewer told that the ISO 27001 certificate
behind a `supported` row expired in March is better served than one whose row silently became
`partially_supported` with the reason buried. Downgrading would also make the verdict move on
a fact the scorer never saw, which is the sort of action at a distance ADR-0024 keeps out of
the rules.

**3. A certificate is matched to evidence by shared name tokens, and the heuristic is
stated rather than hidden.** There is no join to make: `CertificateHeld` carries a name and
an expiry and no document id, `Evidence` carries a document id and a filename.

Substring matching was tried first and does not work on the real names. `ISO/IEC 27001:2022`
normalises to `isoiec270012022` and `ISO_27001_Zertifikat.pdf` to `iso27001zertifikatpdf`;
neither contains the other, so the one pairing that matters most would have been missed
silently. Tokens do work, because the signal in a certificate name is the standard *number*:
`{iso, iec, 27001, 2022}` against `{iso, 27001, zertifikat, pdf}` shares two, which is the
threshold. It is deliberately two and not one — `ISO 9001` against that same filename shares
only `iso`, and warning there would name the wrong certificate. A proper join wants
`document_id` on `CertificateHeld`, which is a profile story and not this one.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date
from typing import Final

from crossbid.models.company import CertificateHeld, CompanyProfile
from crossbid.models.matrix import MatrixRow

MAX_FLAGGED_RATIONALE_CHARS: Final = 2000
"""The working ceiling for a flagged rationale. `agent_rationale` has no length check in the
column, and `check_loop` caps the model's own half at 600; this bounds the whole cell so that
a document matching several expired certificates cannot grow a row without limit. Named apart
from `check_loop.MAX_RATIONALE_CHARS` because it is a different cap on a different half."""

MIN_TOKEN_CHARS: Final = 2
"""Shorter than this is noise — a version suffix, a language tag, an initial."""

MIN_SHARED_TOKENS: Final = 2
"""How many name tokens a certificate and a filename must share. See decision 3: one is the
vendor prefix every certificate of that family carries, and two is the number."""

ECERTIS_NOT_FOUND_NOTICE: Final = (
    "Reviewer note: eCertis records no national document for {country} against the EU "
    "criterion this requirement maps to, so the cross-border evidence mapping could not "
    "answer here. That is normal for many criteria and is not evidence either way — the "
    "equivalent paper has to be identified by hand."
)

EXPIRED_CERTIFICATE_NOTICE: Final = (
    "Reviewer note: {name} expired on {expires_on} and the evidence cited here comes from "
    "it. An expired certificate is not proof; a current one has to be attached before this "
    "row can be relied on."
)

_NON_ALPHANUMERIC: Final = re.compile(r"[^a-z0-9]+")


def flag_rows(
    rows: Sequence[MatrixRow], *, profile: CompanyProfile | None, today: date
) -> list[MatrixRow]:
    """`rows` with a reviewer notice on each one that needs it. A new list; nothing mutated.

    Returns the rows unchanged when nothing applies, which is the common case — the
    identity is by value, so the caller may write them back either way and the read model
    sees the same rows it already holds.
    """
    expired = _expired_certificates(profile, today)
    return [_flagged(row, expired=expired) for row in rows]


def _expired_certificates(
    profile: CompanyProfile | None, today: date
) -> tuple[CertificateHeld, ...]:
    """The bidder's lapsed certificates. Empty when the profile could not be read.

    A certificate with no recorded expiry is not here: `is_expired_on` is not the negation
    of `is_valid_on`, and warning about a certificate nobody dated would tell a reviewer
    something untrue.
    """
    if profile is None:
        return ()
    return tuple(held for held in profile.certificates if held.is_expired_on(today))


def _flagged(row: MatrixRow, *, expired: Sequence[CertificateHeld]) -> MatrixRow:
    """One row with whatever notices apply appended to its rationale.

    Truncation drops whole notices rather than cutting one in half: a reviewer must not be
    shown "…expired on 2026-0" and left to guess. The cap is generous enough that this only
    bites on a document matching a great many lapsed certificates at once.
    """
    notices = [*_ecertis_notices(row), *_certificate_notices(row, expired)]
    if not notices:
        return row
    rationale = row.agent_rationale.strip()
    for notice in notices:
        if len(rationale) + 1 + len(notice) > MAX_FLAGGED_RATIONALE_CHARS:
            break
        rationale = f"{rationale} {notice}"
    return MatrixRow.model_validate(row.model_dump() | {"agent_rationale": rationale})


def _ecertis_notices(row: MatrixRow) -> list[str]:
    """The eCertis notice, when this row has a criterion and the register had no answer."""
    evidence = row.ecertis_evidence
    if evidence is None or evidence.found:
        return []
    return [ECERTIS_NOT_FOUND_NOTICE.format(country=evidence.country.upper())]


def _certificate_notices(row: MatrixRow, expired: Sequence[CertificateHeld]) -> list[str]:
    """One notice per lapsed certificate this row's evidence appears to have come from."""
    documents = [_tokens(item.document_name) for item in row.evidence]
    return [
        EXPIRED_CERTIFICATE_NOTICE.format(name=held.name, expires_on=held.expires_on)
        for held in expired
        if any(_names_match(_tokens(held.name), document) for document in documents)
    ]


def _names_match(certificate: frozenset[str], document: frozenset[str]) -> bool:
    """`MIN_SHARED_TOKENS` tokens in common. See decision 3 for why it is that number."""
    return len(certificate & document) >= MIN_SHARED_TOKENS


def _tokens(name: str) -> frozenset[str]:
    """`ISO/IEC 27001:2022` → `{iso, iec, 27001, 2022}`; `ISO_27001_Zertifikat.pdf` →
    `{iso, 27001, zertifikat, pdf}`. Case folded, punctuation as the separator."""
    return frozenset(
        token
        for token in _NON_ALPHANUMERIC.split(name.casefold())
        if len(token) >= MIN_TOKEN_CHARS
    )
