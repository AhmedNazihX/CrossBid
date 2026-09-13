"""S2.5.1 — a published DUME's criteria as `Requirement`s, decided by rule and not by model.

This is the shortest path in the system from an input to a matrix row, and that is the
point. `extract_reqs` spends a model call per five pages to turn prose into cited rows and
still may not name an eCertis criterion, because ADR-0007 forbids inferring one from wording.
A DUME states them: the buyer has already said, in machine-readable form, which of the 56 EU
criteria this procedure invokes. Everything below is therefore a lookup or a table, and a
model is never asked anything — asking one here could only make the answer worse.

**What the ESPD type code decides.** `cbc:TypeCode` is the ESPD taxonomy
(`CRITERION.EXCLUSION.CONVICTIONS.CORRUPTION`,
`CRITERION.SELECTION.ECONOMIC_FINANCIAL_STANDING.TURNOVER.GENERAL_YEARLY`), and its first
two segments are exactly the distinction the matrix wants. The table below is the whole
classifier; a code outside it lands on the `OTHER` row rather than being guessed at.

**Why exclusion grounds are `DOCUMENT_SUBMISSION` and selection criteria are not.** SP.1
measured what happens when the checking loop is asked to settle a duty no corpus of company
facts can establish: every row came back `unclear` after spending tool calls (ADR-0003). An
exclusion ground is exactly that shape — "the operator has not been convicted", a negative
that the bidder's own documents cannot prove and that is settled in the real world by a
national certificate, which is precisely what the eCertis card on the row names
(`Führungszeugnis` for a German bidder, `Bulletin n°2` for a French one). So the row goes to
the reviewer as "attach this", carrying its eCertis evidence, and costs no tool call.
Selection criteria are the opposite: turnover, headcount, references and quality-assurance
certificates are facts about the company that its evidence pack can and should settle, so
they run the checking loop. `check_loop.ecertis_evidence_for` attaches the eCertis mapping
**before** the `COMPANY_PROPERTY` gate, so both kinds of row show it.

**Every row is `bid_eligibility`.** The ESPD *is* the qualification form — it is answered to
decide whether a bidder may be considered at all, never to govern performance after award —
so the discriminator that cost ADR-0003 so much to establish is free here.

**The citation is the criterion, not a page.** A DUME is XML. `Requirement.page` is `None`
and `Requirement.source` is `ESPD_REQUEST`, which the model refuses to let disagree; the
reviewer follows the citation by opening the named file and searching for the criterion id,
which is the identifier the file itself is keyed on. `source_text` is the buyer's own
wording, preferring `cbc:Description` (the operative question) and falling back to
`cbc:Name` when the description is blank — one criterion in the French fixture has a
description of a single space. `translation` stays `None`: nothing translated it, and the
eCertis lookup already names the criterion in the bidder's language (S1.1.2).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Final

from pydantic import ValidationError

from crossbid.agent.nodes.extract_reqs import REQUIREMENT_ID_NAMESPACE
from crossbid.ingestion.espd import EspdCriterion, EspdRequest
from crossbid.models.requirement import (
    Checkability,
    Requirement,
    RequirementCategory,
    RequirementKind,
    RequirementSource,
    RequirementStage,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _Mapping:
    """One row of the table below. Named fields rather than a tuple, so a reader can see
    that "mandatory" belongs to the kind and not to the category."""

    category: RequirementCategory
    kind: RequirementKind
    checkable: Checkability


EXCLUSION: Final = _Mapping(
    RequirementCategory.EXCLUSION_GROUND,
    RequirementKind.MANDATORY,
    Checkability.DOCUMENT_SUBMISSION,
)
UNCLASSIFIED: Final = _Mapping(
    RequirementCategory.OTHER, RequirementKind.INFORMATIONAL, Checkability.NEITHER
)
"""Where a code the table does not know lands. Informational and settled by nothing, so it
reaches the reviewer as a line to read rather than a claim the agent made about it."""

TYPE_CODE_MAPPINGS: Final[tuple[tuple[str, _Mapping], ...]] = (
    ("CRITERION.EXCLUSION.", EXCLUSION),
    (
        "CRITERION.SELECTION.ECONOMIC_FINANCIAL_STANDING.",
        _Mapping(
            RequirementCategory.ECONOMIC_FINANCIAL,
            RequirementKind.MANDATORY,
            Checkability.COMPANY_PROPERTY,
        ),
    ),
    (
        "CRITERION.SELECTION.TECHNICAL_PROFESSIONAL_ABILITY.",
        _Mapping(
            RequirementCategory.TECHNICAL_PROFESSIONAL,
            RequirementKind.MANDATORY,
            Checkability.COMPANY_PROPERTY,
        ),
    ),
    (
        "CRITERION.SELECTION.SUITABILITY.",
        _Mapping(
            RequirementCategory.FORMAL,
            RequirementKind.MANDATORY,
            Checkability.COMPANY_PROPERTY,
        ),
    ),
)
"""The ESPD taxonomy's four families that the matrix distinguishes, longest-prefix first in
spirit: the codes are disjoint, so the first match wins and the order is only readability.
`CRITERION.SELECTION.SUITABILITY.*` is enrolment in a professional or trade register, which
is a formal qualification rather than a measure of capacity, hence `FORMAL`."""

ESPD_STAGE: Final = RequirementStage.BID_ELIGIBILITY
"""See the module docstring: an ESPD criterion is by definition a qualification question."""


def requirements_from_espd(
    request: EspdRequest, *, bid_id: str, document_name: str, source_lang: str
) -> tuple[Requirement, ...]:
    """`request`'s criteria as requirements of `bid_id`, in the order the buyer declared them.

    `source_lang` is the tender's own language, used when the file declares none — ESPD
    1.0.2 has no language element, so that is the normal case (see `ingestion/espd.py`).
    """
    language = request.language or source_lang
    rows = (
        _requirement(
            criterion, bid_id=bid_id, document_name=document_name, source_lang=language
        )
        for criterion in request.criteria
    )
    return tuple(row for row in rows if row is not None)


def _requirement(
    criterion: EspdCriterion, *, bid_id: str, document_name: str, source_lang: str
) -> Requirement | None:
    """One criterion as a requirement, or `None` plus a log line naming what stopped it.

    The only way this returns `None` is a `Requirement` contract the criterion cannot
    satisfy — in practice wording longer than the quote cap. Truncating it would turn the
    buyer's words into ours, so the row is dropped instead, and the log names the *field*
    and never the value: the value is document-derived text (ADR-0008).
    """
    mapping = _mapping_for(criterion.type_code)
    try:
        return Requirement(
            id=_requirement_id(bid_id, document_name, criterion.id),
            bid_id=bid_id,
            category=mapping.category,
            kind=mapping.kind,
            stage=ESPD_STAGE,
            checkable=mapping.checkable,
            source=RequirementSource.ESPD_REQUEST,
            source_text=_wording(criterion),
            source_lang=source_lang,
            document_name=document_name,
            page=None,
            ecertis_criterion_id=criterion.id,
        )
    except ValidationError as exc:
        fields = sorted({".".join(str(part) for part in e["loc"]) for e in exc.errors()})
        logger.warning(
            "ESPD criterion %s dropped: it cannot satisfy the requirement contract (%s)",
            criterion.id,
            ", ".join(fields),
        )
        return None


def _mapping_for(type_code: str) -> _Mapping:
    """The table row for a type code, or `UNCLASSIFIED`. Case-insensitive by prefix."""
    code = type_code.strip().upper()
    for prefix, mapping in TYPE_CODE_MAPPINGS:
        if code.startswith(prefix):
            return mapping
    return UNCLASSIFIED


def _wording(criterion: EspdCriterion) -> str:
    """The buyer's own words: the description if it says anything, otherwise the name.

    Stripped of surrounding whitespace and nothing else — a quote keeps the buyer's words,
    their case and their punctuation. `ingestion/espd.py` has already refused a criterion
    where both are blank, so this always returns something.
    """
    return criterion.description.strip() or criterion.name.strip()


def _requirement_id(bid_id: str, document_name: str, criterion_id: str) -> str:
    """A `uuid5` over bid, file and criterion — deterministic, so a re-run upserts.

    The same namespace as extraction's ids (`REQUIREMENT_ID_NAMESPACE`), because these rows
    live in the same table under the same primary key and two namespaces would be two id
    spaces nobody asked for. The key cannot collide with an extracted row's: that one is
    bid, file, *page number* and quote, and a criterion UUID is neither a page nor a quote.
    """
    key = "\x1f".join((bid_id, document_name, criterion_id))
    return str(uuid.uuid5(REQUIREMENT_ID_NAMESPACE, key))
