"""S1.1.2 — one criterion, one bidder country, one bidder language, one answer.

The cross-border wedge in a function: a German firm reading a French tender asks
`lookup_evidence(criterion, country="de", language="de")` and gets back the German papers
that satisfy the criterion the French buyer invoked, named in German *and* in English. Both
languages, always — the English name is what the tender, the notice and the ESPD form call
the thing, and the German name is what the bidder will find in their own filing cabinet.

Two halves are joined here, which is why this is its own module rather than more of
`ecertis_client`:

* `evidence_{cc}.json` — the structure (which paper, whose registry, which national law),
  in English, keyed on the EU criterion UUID.
* `l10n_{lang}.json` — the same entities' words in the bidder's language, keyed on the
  entity UUID. Machine-translated by eCertis and marked as such.

**Nothing here raises, and nothing it returns makes a caller raise either.** It is called
from inside a per-requirement ReAct loop, where an exception costs a whole turn and teaches
the model nothing. There are five different ways to have nothing to say — an id eCertis never
heard of, a country whose evidence was never built, a country that registers no national
entry for this criterion, a broken cache directory, and a "country" that is not a country
code at all — and all five come back as `status="not_found"` with an empty document list. The
last one is why `country` is typed, not merely echoed: the answer travels on to a matrix row
whose own country field is two letters, so an unchecked echo would only push the exception
one frame downstream (see `_country_code`). A language with no overlay is *not* one of them:
that answer degrades to the English text, because the right document in the wrong language is
still the right document.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from crossbid.reference.ecertis_client import (
    EcertisCacheError,
    find_evidence,
    load_localisation,
)
from crossbid.reference.ecertis_schema import CachedCriterionEvidence, CachedLocalisation

DEFAULT_BIDDER_LANGUAGE: Final = "de"
"""The one overlay v1 builds. See `DEFAULT_LANGUAGES` in the cache build script."""

Alpha2 = Annotated[str, StringConstraints(pattern=r"^[a-z]{2}$")]
"""ISO 3166-1 alpha-2, already normalised — the shape `EcertisEvidence.country` demands."""

UNKNOWN_COUNTRY: Final = "zz"
"""What the answer reports when the caller's country is not a country code at all.

`zz` is ISO 3166-1's user-assigned range and CLDR's "Unknown Region", so it is a code that
can never collide with a real bidder country and never name a cache file.
"""

_NO_LOCALISATION: Final[Mapping[str, CachedLocalisation]] = {}


class EvidenceStatus(StrEnum):
    """Whether eCertis names a document, in the vocabulary the tool hands to the model."""

    FOUND = "found"
    NOT_FOUND = "not_found"


class LocalisedEvidence(BaseModel):
    """One national document, in English and in the bidder's language side by side.

    The `*_localised` fields fall back to the English value rather than to an empty string:
    a reviewer comparing the two columns should see the same words when there is no
    translation, not a blank where the paper's name should be. `detail_url` is the way out
    of a bad machine translation — it is the eCertis page the text was taken from.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str
    name_localised: str
    description: str
    description_localised: str
    issuers: tuple[str, ...]
    issuers_localised: tuple[str, ...]
    detail_url: str


class EvidenceAnswer(BaseModel):
    """What eCertis can prove about one criterion for one bidder, or that it cannot.

    Flat on purpose. eCertis nests criterion → national sub-criterion → requirement group →
    document, and the group layer genuinely means "any one of these will do" (ADR-0007) —
    but a bidder asks "what do I attach?", so the answer is a document list, de-duplicated
    across sub-criteria and ordered by name. The nesting stays in the cache for anything
    that needs it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: EvidenceStatus
    criterion_id: str
    criterion_name: str = Field(description="The EU-level ESPD name, in English")
    criterion_name_localised: str
    country: Alpha2 = Field(
        description=(
            "Whose registry issues the papers; ISO 3166-1 alpha-2, or 'zz' when the caller "
            "named no country this module could look up"
        )
    )
    language: str = Field(description="The language `*_localised` is in; ISO 639-1")
    evidences: tuple[LocalisedEvidence, ...] = ()


def lookup_evidence(
    criterion_id: str, country: str, language: str = DEFAULT_BIDDER_LANGUAGE
) -> EvidenceAnswer:
    """Which document proves `criterion_id` in `country`, named in `language` and English.

    Total by construction: every failure mode is a `not_found` answer. See the module
    docstring for which ones and why.
    """
    country = _country_code(country)
    language = language.strip().lower()
    row = _find_row(criterion_id, country)
    if row is None:
        return EvidenceAnswer(
            status=EvidenceStatus.NOT_FOUND,
            criterion_id=criterion_id,
            criterion_name="",
            criterion_name_localised="",
            country=country,
            language=language,
        )

    entries = _localisations(language)
    evidences = _localised_documents(row, entries)
    localised_name = _localised(entries, row.criterion_id, row.criterion_name)
    return EvidenceAnswer(
        status=EvidenceStatus.FOUND if evidences else EvidenceStatus.NOT_FOUND,
        criterion_id=row.criterion_id,
        criterion_name=row.criterion_name,
        criterion_name_localised=localised_name,
        country=country,
        language=language,
        evidences=evidences,
    )


def _country_code(raw: str) -> str:
    """The bidder country as a code the answer may carry, or `UNKNOWN_COUNTRY`.

    The field is two letters because `EcertisEvidence.country` is two letters: the answer is
    handed to `tools.ecertis_evidence.to_matrix_evidence` unchanged, and a `ValidationError`
    raised *there* would go off inside the per-requirement ReAct loop this module's totality
    exists to protect — in a call S3.3.1 was told needs no `try`. Echoing `"deu"` back only
    moved the failure one frame downstream, so it is caught at the door instead.

    The tool's argument schema already refuses anything but two letters; `check_reqs` calls
    `lookup_evidence` directly, with whatever the requirement row carries. That makes this
    also the one guard on the only caller-controlled string that becomes a file name:
    `find_evidence` reads `evidence_{country}.json`.

    `zz` then takes the ordinary "no cache for that country" route — one fewer branch, and
    the same honest `not_found` a bidder in Italy gets.
    """
    code = raw.strip().lower()
    return code if len(code) == 2 and code.isascii() and code.isalpha() else UNKNOWN_COUNTRY


def _find_row(criterion_id: str, country: str) -> CachedCriterionEvidence | None:
    """`find_evidence`, minus the two ways it can raise on a cache that is not there."""
    try:
        return find_evidence(criterion_id, country)
    except EcertisCacheError:
        return None


def _localisations(language: str) -> Mapping[str, CachedLocalisation]:
    """The bidder-language overlay, or an empty one — which means "answer in English"."""
    try:
        return load_localisation(language).entries
    except EcertisCacheError:
        return _NO_LOCALISATION


def _localised(entries: Mapping[str, CachedLocalisation], entity_id: str, fallback: str) -> str:
    entry = entries.get(entity_id)
    return entry.name if entry and entry.name else fallback


def _localised_documents(
    row: CachedCriterionEvidence, entries: Mapping[str, CachedLocalisation]
) -> tuple[LocalisedEvidence, ...]:
    """Flatten the sub-criteria into one document list, de-duplicated by evidence id.

    The cache already folds an evidence that appears in several `RequirementGroup`s into
    one row, but only *within* a sub-criterion — it has no reason to look across them. No
    criterion in the committed DE or FR cache currently lists one document under two
    sub-criteria, so the de-duplication is defensive rather than load-bearing; it is here
    because eCertis makes no promise about that, and telling a reviewer to attach the same
    Führungszeugnis twice is the kind of small wrongness that costs trust in the whole
    matrix.
    """
    seen: dict[str, LocalisedEvidence] = {}
    for sub in row.sub_criteria:
        for evidence in sub.evidences:
            if evidence.id in seen:
                continue
            entry = entries.get(evidence.id)
            seen[evidence.id] = LocalisedEvidence(
                id=evidence.id,
                name=evidence.name,
                name_localised=entry.name if entry and entry.name else evidence.name,
                description=evidence.description,
                description_localised=(
                    entry.description if entry and entry.description else evidence.description
                ),
                issuers=evidence.issuers,
                issuers_localised=(
                    entry.issuers if entry and entry.issuers else evidence.issuers
                ),
                detail_url=evidence.detail_url,
            )
    return tuple(sorted(seen.values(), key=lambda e: (e.name, e.id)))
