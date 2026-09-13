"""S2.5.1 — a buyer's published ESPD request (DUME) read into typed criteria.

**Why this is worth a module of its own.** Crossbid's differentiator is cross-border
certificate equivalence through eCertis, and eCertis is keyed on the EU-level ESPD criterion
UUID. Nothing in a procurement PDF carries one — all 38 fixture PDFs across DE, FR and EN
were scanned and contain zero — and `prompts/extract.md` forbids inferring one from wording,
correctly (ADR-0007: a wrong id is worse than none). The **one** input that carries them is
the ESPD request the buyer publishes alongside the tender: the French fixture's
`DUME_acheteur.xml` declares 30 `ccv:Criterion` elements and every one is a member of the
generated register. So where a tender publishes a DUME, the criterion mapping needs no model
at all — it is a lookup, and this module is the lookup.

Four decisions.

**1. The register is the authority, not the file.** Every `cbc:ID` is checked against the
generated `EcertisCriterionId` and dropped if the register does not know it. ADR-0007's trap
is that `criteria?nationalEntity=de` returns the *same* 56 criteria under country-scoped
UUIDs which are disjoint from the EU-level ids and meaningless across a border, and a
national uuid is indistinguishable from an EU one by shape. Only membership tells them
apart, so only membership is trusted. A dropped criterion is logged with its id and counted,
never silently skipped: the caller turns the count into a problem the reviewer sees.

**2. The classification comes from `cbc:TypeCode`, and a criterion without one is dropped.**
The type code (`CRITERION.EXCLUSION.…` vs `CRITERION.SELECTION.…`) is the ESPD taxonomy in
machine-readable form; `agent/espd_requirements.py` maps it to a category with no model
involved. A criterion carrying no type code could only be classified by guessing at the
buyer's prose, which is the thing this whole path exists to avoid.

**3. The reader is faithful; the mapper decides.** `name` and `description` come back exactly
as the file wrote them, whitespace and all — one criterion in the French fixture has a
description of a single space — because which of the two becomes a citation is a product
decision and belongs where that decision is made. What the reader *does* decide is
uniqueness: a real DUME restates the same criterion for every lot (the fixture repeats each
`RequirementGroup` three times), and thirty identical matrix rows would be noise, so the
first occurrence of an id wins.

**4. Untrusted bytes go through `safe_xml` and nothing else.** This file is uploaded by a
bidder. `ingestion/safe_xml.py` states the attacks and the defence; everything here sees is
an already-parsed tree. The root element is checked before any criterion is read, so a file
that is well-formed XML but not an ESPD request is refused as one error rather than
returning an empty, plausible-looking result.

ESPD **1.0.2** namespaces are pinned, which is what the French fixture and every DUME issued
by the EU's own generator use. ESPD-EDM 2.x renames the elements outright
(`cac:TenderingCriterion`), so it would not be a tweak here but a second reader; a 2.x file
is refused with the same "not an ESPD request" message it deserves today.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Final, cast
from xml.etree.ElementTree import Element

from crossbid.ingestion.safe_xml import XmlRejectedError, parse_xml
from crossbid.models.ecertis_criteria import CRITERION_IDS, EcertisCriterionId

logger = logging.getLogger(__name__)

ESPD_REQUEST_NS: Final = "urn:grow:names:specification:ubl:schema:xsd:ESPDRequest-1"
CCV_NS: Final = "urn:isa:names:specification:ubl:schema:xsd:CCV-CommonAggregateComponents-1"
CBC_NS: Final = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"

ROOT_TAG: Final = f"{{{ESPD_REQUEST_NS}}}ESPDRequest"
CRITERION_TAG: Final = f"{{{CCV_NS}}}Criterion"
ID_TAG: Final = f"{{{CBC_NS}}}ID"
TYPE_CODE_TAG: Final = f"{{{CBC_NS}}}TypeCode"
NAME_TAG: Final = f"{{{CBC_NS}}}Name"
DESCRIPTION_TAG: Final = f"{{{CBC_NS}}}Description"

LANGUAGE_ATTRIBUTE: Final = "languageID"
LANGUAGE_PATTERN: Final = re.compile(r"^[a-z]{2}(-[a-z0-9]{2,4})?$")
"""BCP 47 as narrowly as `Requirement.source_lang` accepts it (2-5 characters). A value
outside it is treated as absent rather than repaired: a wrong language tag would label a
French quote as German for the rest of the run."""

KNOWN_CRITERION_IDS: Final = frozenset(CRITERION_IDS)
"""The generated register as a set, for membership. `extract_reqs` keeps its own copy of the
same derivation for the model's answers; both come from the one generated tuple, and neither
layer may import the other (`agent/` sits above `ingestion/`)."""


class EspdParseError(ValueError):
    """The bytes are not a readable ESPD request.

    Covers "not XML we will parse" (`safe_xml.XmlRejectedError`, re-raised) and "XML, but not
    an ESPD request". One type, because every caller answers both the same way: the upload
    boundary with 415, the pipeline with a failure the bidder can act on. The message never
    quotes the document (ADR-0008).
    """


@dataclass(frozen=True, slots=True)
class EspdCriterion:
    """One `ccv:Criterion`: the register's id, the ESPD taxonomy code, the buyer's words."""

    id: EcertisCriterionId
    type_code: str
    name: str
    description: str


@dataclass(frozen=True, slots=True)
class EspdRequest:
    """What one uploaded DUME says: its criteria, what was dropped, and its language."""

    criteria: tuple[EspdCriterion, ...] = ()
    dropped_criterion_count: int = 0
    """How many `ccv:Criterion` elements were read and thrown away — an id the register does
    not know, no type code, or no wording at all. Never quietly zero: the caller reports it
    to the reviewer, and the reason for each one is in the log."""

    language: str | None = None
    """The language the buyer wrote the criterion names in, if the file says so. ESPD 1.0.2
    has no language element and the French fixture sets none, so this is usually `None` and
    the caller falls back to the tender's own language."""


def parse_espd_request(data: bytes) -> EspdRequest:
    """Read `data` as an ESPD request, or raise `EspdParseError` saying why it is not one."""
    try:
        root = parse_xml(data)
    except XmlRejectedError as exc:
        # `XmlRejectedError`'s message names the refusal, never the document's content.
        raise EspdParseError(f"the file could not be read as XML: {exc}") from exc

    if root.tag != ROOT_TAG:
        raise EspdParseError(
            "the file is XML but not an ESPD request: its root element is not "
            f"{{{ESPD_REQUEST_NS}}}ESPDRequest (ESPD 1.0.2)"
        )

    criteria: list[EspdCriterion] = []
    seen: set[str] = set()
    dropped = 0
    for element in root.iterfind(CRITERION_TAG):
        criterion = _criterion(element)
        if criterion is None:
            dropped += 1
            continue
        if criterion.id in seen:
            continue  # the same criterion restated for another lot
        seen.add(criterion.id)
        criteria.append(criterion)
    return EspdRequest(
        criteria=tuple(criteria),
        dropped_criterion_count=dropped,
        language=_language_of(root),
    )


def _criterion(element: Element) -> EspdCriterion | None:
    """One criterion, or `None` and a log line saying which one was dropped and why."""
    identifier = _criterion_id(_text_of(element, ID_TAG))
    if identifier is None:
        logger.warning(
            "ESPD criterion dropped: %r is not an EU-level eCertis criterion id",
            _text_of(element, ID_TAG),
        )
        return None

    type_code = _text_of(element, TYPE_CODE_TAG).strip()
    if not type_code:
        logger.warning("ESPD criterion %s dropped: it carries no cbc:TypeCode", identifier)
        return None

    name = _text_of(element, NAME_TAG)
    description = _text_of(element, DESCRIPTION_TAG)
    if not name.strip() and not description.strip():
        logger.warning(
            "ESPD criterion %s dropped: it states no name or description", identifier
        )
        return None

    return EspdCriterion(id=identifier, type_code=type_code, name=name, description=description)


def _criterion_id(raw: str) -> EcertisCriterionId | None:
    """The id if the generated register knows it, lower-cased; otherwise `None`.

    Case is normalised because a DUME may print the UUID either way, and nothing else is:
    an id the register does not hold is refused, not repaired. `cast` is unavoidable —
    membership of a set built from the `Literal` is exactly the check the type wants, and no
    type checker can see that.
    """
    candidate = raw.strip().lower()
    if candidate not in KNOWN_CRITERION_IDS:
        return None
    return cast(EcertisCriterionId, candidate)


def _text_of(element: Element, tag: str) -> str:
    """The child's text as written, or `""` when the child or its text is absent."""
    child = element.find(tag)
    if child is None or child.text is None:
        return ""
    return child.text


def _language_of(root: Element) -> str | None:
    """The first usable UBL `languageID` in the document, lower-cased.

    UBL lets a buyer tag each `cbc:Name`/`cbc:Description` with the language it is written
    in. ESPD 1.0.2 does not require it and the French fixture omits it entirely, so this is
    a bonus when present rather than something to depend on.
    """
    for element in root.iter():
        declared = element.get(LANGUAGE_ATTRIBUTE, "").strip().lower()
        if LANGUAGE_PATTERN.match(declared):
            return declared
    return None
