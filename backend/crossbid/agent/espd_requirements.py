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
description of a single space. `translation` is the **eCertis register's own name for the
criterion in the bidder's language** (S1.1.2), looked up by the canonical UUID the DUME
declares — a dictionary hit against a cached file, no model and no network. It used to stay
`None` on the grounds that the eCertis card already said it; see `_translations` for why that
was not enough (M3, ADR-0082).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping
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
from crossbid.reference.ecertis_client import EcertisCacheError, load_localisation
from crossbid.reference.ecertis_schema import CachedLocalisation

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
    request: EspdRequest,
    *,
    bid_id: str,
    document_name: str,
    source_lang: str,
    bidder_language: str,
) -> tuple[Requirement, ...]:
    """`request`'s criteria as requirements of `bid_id`, in the order the buyer declared them.

    `source_lang` is the tender's own language, used when the file declares none — ESPD
    1.0.2 has no language element, so that is the normal case (see `ingestion/espd.py`).
    `bidder_language` is what the rows are translated *into*; see `_translations`.
    """
    language = request.language or source_lang
    translations = _translations(bidder_language)
    rows = (
        _requirement(
            criterion,
            bid_id=bid_id,
            document_name=document_name,
            source_lang=language,
            translations=translations,
        )
        for criterion in request.criteria
    )
    return tuple(row for row in rows if row is not None)


def _translations(bidder_language: str) -> Mapping[str, CachedLocalisation]:
    """The eCertis overlay for `bidder_language`, or an empty one meaning "no translation".

    **This is where an ESPD row's bidder-language wording comes from, and it costs nothing**
    (M3). A DUME declares each criterion under its canonical ESPD UUID, which is the same id
    eCertis is keyed on (CLAUDE.md, verified on real data), and S1.1.2 already cached that
    register's words in the bidder's language. So the translation is a dictionary lookup
    against a file in the repository: no model call, no network, and exact rather than
    inferred.

    Before this, `translation` was left `None` on every ESPD row on the grounds that the
    eCertis *card* names the criterion in the bidder's language. That was true and it was
    not enough: the card is on the matrix row, and nothing else reads it. The verdict's gap
    list falls back to `source_text`, so a German bidder reading a French tender got a German
    recommendation followed by a gap list in French — 30 of the FR pack's 144 rows, every one
    of them from the DUME. The paragraph a non-lawyer actually reads changed language halfway
    down.

    A language with no cached overlay gets an empty mapping and the old behaviour, which is
    the honest answer: `de` is cached, and inventing the rest is not something a lookup can
    do.
    """
    try:
        return load_localisation(bidder_language).entries
    except EcertisCacheError:
        logger.info(
            "No eCertis overlay for %s; ESPD rows keep the buyer's own wording",
            bidder_language,
        )
        return {}


def _requirement(
    criterion: EspdCriterion,
    *,
    bid_id: str,
    document_name: str,
    source_lang: str,
    translations: Mapping[str, CachedLocalisation],
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
            translation=_translation(criterion, translations),
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


def _translation(
    criterion: EspdCriterion, translations: Mapping[str, CachedLocalisation]
) -> str | None:
    """The register's bidder-language name for this criterion, or `None`.

    The register's *name*, not its description: the description is a paragraph of directive
    text and `source_text` is already the buyer's own wording of the same duty. What a gap
    line needs is the criterion said once, in the reader's language.
    """
    entry = translations.get(criterion.id)
    if entry is None or not entry.name.strip():
        return None
    return entry.name.strip()


def _requirement_id(bid_id: str, document_name: str, criterion_id: str) -> str:
    """A `uuid5` over bid, file and criterion — deterministic, so a re-run upserts.

    The same namespace as extraction's ids (`REQUIREMENT_ID_NAMESPACE`), because these rows
    live in the same table under the same primary key and two namespaces would be two id
    spaces nobody asked for. The key cannot collide with an extracted row's: that one is
    bid, file, *page number* and quote, and a criterion UUID is neither a page nor a quote.
    """
    key = "\x1f".join((bid_id, document_name, criterion_id))
    return str(uuid.uuid5(REQUIREMENT_ID_NAMESPACE, key))
