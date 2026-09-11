"""Pydantic schemas for eCertis: the wire shape we distrust, the cache shape we own.

Two families live here on purpose.

`Wire*` models mirror the eCertis REST payloads (spec v0.6, 2023) exactly as they
arrive. Every eCertis scalar is wrapped in an object -- `{"value": ..., "languageID":
"en"}` -- and the service happily sends that object empty (`"FeeAmount": {}`), so every
field is optional and `extra="ignore"` keeps a future field from breaking a build. These
models exist to fail loudly on a *structural* surprise, not to assert completeness.

`Cached*` models are our own flat shape, the one that gets committed under
`data/ecertis/` and loaded at run time. They are strict: a missing id or name means the
cache is corrupt.

The two are joined by `crossbid.reference.ecertis_client`, which normalises wire into
cache. Nothing here imports anything else from `crossbid`.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_serializer,
    field_validator,
)

CACHE_SCHEMA_VERSION = 1
"""Bumped when the `Cached*` shape changes, so a stale committed file is detectable.

Deliberately *not* bumped by S1.1.2. The bidder-language overlay is a separate file
(`LocalisationCache`) precisely so that `criteria.json`, `evidence_de.json` and
`evidence_fr.json` stay byte-identical: `criteria.json` is what the generated
`EcertisCriterionId` Literal is rendered from, and every one of the three carries a
`content_sha256` that a schema bump would churn for text none of their readers use.
"""

ECERTIS_SPEC_VERSION = "0.6"

NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]
CountryCode = Annotated[str, StringConstraints(pattern=r"^[a-z]{2}$")]
LanguageCode = Annotated[str, StringConstraints(pattern=r"^[a-z]{2}$")]
"""ISO 639-1. Same shape as a country code, a different thing — `de` the language is the
bidder's words, `de` the country is whose registry issues the paper, and S1.1.2 crosses
them (a German firm reading a French tender asks for `country=fr, language=de`)."""

# --------------------------------------------------------------------------- wire


class WireLenient(BaseModel):
    """Base for the untrusted half: unknown fields are dropped, nothing is required."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True, frozen=True)


class WireText(WireLenient):
    """eCertis's universal scalar wrapper. Sent as `{}` when the value is absent."""

    value: str | None = None
    language_id: str | None = Field(default=None, alias="languageID")


class WirePartyName(WireLenient):
    name: WireText | None = Field(default=None, alias="Name")


class WireParty(WireLenient):
    party_name: list[WirePartyName] = Field(default_factory=list, alias="PartyName")
    website_uri: WireText | None = Field(default=None, alias="WebsiteURI")


class WireExternalReference(WireLenient):
    uri: WireText | None = Field(default=None, alias="URI")


class WireAttachment(WireLenient):
    external_reference: WireExternalReference | None = Field(
        default=None, alias="ExternalReference"
    )


class WirePeriod(WireLenient):
    """`ValidityPeriod`. Note the lowercase key, and that it may be a list or an object."""

    description: list[WireText] | WireText | None = None


class WireDocumentReference(WireLenient):
    attachment: WireAttachment | None = Field(default=None, alias="Attachment")
    validity_period: WirePeriod | None = Field(default=None, alias="ValidityPeriod")


class WireIntendedUse(WireLenient):
    description: list[WireText] | WireText | None = None


class WireEvidence(WireLenient):
    """One `TypeOfEvidence`: the national document that proves a criterion."""

    id: WireText | None = Field(default=None, alias="Id")
    type_code: WireText | None = Field(default=None, alias="TypeCode")
    name: WireText | None = Field(default=None, alias="Name")
    description: WireText | None = Field(default=None, alias="Description")
    version_id: WireText | None = Field(default=None, alias="VersionID")
    addressee_description: WireText | None = Field(default=None, alias="AddresseeDescription")
    issuer_party: list[WireParty] = Field(default_factory=list, alias="EvidenceIssuerParty")
    jurisdiction_level_code: list[WireText] = Field(
        default_factory=list, alias="JurisdictionLevelCode"
    )
    document_reference: list[WireDocumentReference] = Field(
        default_factory=list, alias="EvidenceDocumentReference"
    )
    intended_use: WireIntendedUse | None = Field(default=None, alias="EvidenceIntendedUse")


class WireRequirementGroup(WireLenient):
    id: WireText | None = Field(default=None, alias="Id")
    type_of_evidence: list[WireEvidence] = Field(default_factory=list, alias="TypeOfEvidence")


class WireLegislation(WireLenient):
    title: WireText | None = Field(default=None, alias="Title")
    description: WireText | None = Field(default=None, alias="Description")
    jurisdiction_level_code: WireText | None = Field(
        default=None, alias="JurisdictionLevelCode"
    )
    article: WireText | None = Field(default=None, alias="Article")
    uri: WireText | None = Field(default=None, alias="URI")


class WireSubCriterion(WireLenient):
    """A national instance of an EU criterion. Its `Id` is country-scoped, not EU-wide."""

    id: WireText | None = Field(default=None, alias="Id")
    type_code: WireText | None = Field(default=None, alias="TypeCode")
    name: WireText | None = Field(default=None, alias="Name")
    description: WireText | None = Field(default=None, alias="Description")
    version_id: WireText | None = Field(default=None, alias="VersionID")
    legislation_reference: list[WireLegislation] = Field(
        default_factory=list, alias="LegislationReference"
    )
    requirement_group: list[WireRequirementGroup] = Field(
        default_factory=list, alias="RequirementGroup"
    )


class WireCriterionDetail(WireLenient):
    """`GET criteria/{uuid}?countryFilter=xx` -- one EU criterion with national children."""

    id: WireText | None = Field(default=None, alias="Id")
    type_code: WireText | None = Field(default=None, alias="TypeCode")
    name: WireText | None = Field(default=None, alias="Name")
    description: WireText | None = Field(default=None, alias="Description")
    version_id: WireText | None = Field(default=None, alias="VersionID")
    legislation_reference: list[WireLegislation] = Field(
        default_factory=list, alias="LegislationReference"
    )
    sub_criterion: list[WireSubCriterion] = Field(default_factory=list, alias="SubCriterion")


class WireCriterionSummary(WireLenient):
    """One row of `GET criteria` -- no evidence, just identity and taxonomy."""

    id: WireText | None = Field(default=None, alias="Id")
    criteria_type_id: WireText | None = Field(default=None, alias="CriteriaTypeID")
    criteria_type_name: WireText | None = Field(default=None, alias="CriteriaTypeName")
    name: WireText | None = Field(default=None, alias="Name")
    description: WireText | None = Field(default=None, alias="Description")
    version_id: WireText | None = Field(default=None, alias="VersionID")


class WireCriteriaList(WireLenient):
    """`GET criteria` -- note the lowercase envelope key."""

    criterion: list[WireCriterionSummary] = Field(default_factory=list)


# --------------------------------------------------------------------------- cache


class CacheStrict(BaseModel):
    """Base for the half we generate: no unknown fields, frozen, so it cannot drift."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class CachedCriterion(CacheStrict):
    """One EU-level ESPD criterion. `id` is the enum member in `models.ecertis_criteria`.

    `type_name` is the ESPD taxonomy label ("Exclusion Ground / Criminal convictions" and
    seven others). The bare `criteria` listing omits it -- see `EcertisRestClient.
    fetch_criteria` for where it is picked up instead.
    """

    id: NonEmptyStr
    name: NonEmptyStr
    description: str
    type_name: str
    version: str


class CachedLegislation(CacheStrict):
    title: str
    description: str
    jurisdiction: str
    article: str
    uri: str


class CachedEvidence(CacheStrict):
    """One national document a bidder submits. `groups` are the alternatives it belongs to."""

    id: NonEmptyStr
    type_code: str
    name: str
    description: str
    issuers: tuple[str, ...]
    addressee: str
    jurisdictions: tuple[str, ...]
    validity_period: str
    intended_use: str
    detail_url: str
    groups: tuple[str, ...]


class CachedSubCriterion(CacheStrict):
    """The country's own version of the criterion, with the papers that satisfy it."""

    id: NonEmptyStr
    name: str
    description: str
    legislation: tuple[CachedLegislation, ...]
    evidences: tuple[CachedEvidence, ...]


class CachedCriterionEvidence(CacheStrict):
    """Evidence for one EU criterion in one country. Empty `sub_criteria` is normal."""

    criterion_id: NonEmptyStr
    criterion_name: str
    sub_criteria: tuple[CachedSubCriterion, ...]


class CacheHeader(CacheStrict):
    """Provenance every cache file carries. `source_date` only moves when the data does."""

    source: NonEmptyStr
    source_date: NonEmptyStr
    ecertis_spec_version: NonEmptyStr
    schema_version: int
    content_sha256: NonEmptyStr


class CriteriaCache(CacheHeader):
    """`criteria.json` -- the EU-level criterion list the extraction enum is built from."""

    criteria: tuple[CachedCriterion, ...]


class EvidenceCache(CacheHeader):
    """`evidence_{cc}.json` -- every EU criterion, with that country's evidence or none."""

    country: CountryCode
    criteria: tuple[CachedCriterionEvidence, ...]


class CachedLocalisation(CacheStrict):
    """One eCertis entity's text in a bidder language, as eCertis itself sends it.

    Only the three fields a bidder reads off the answer: what the paper is called, what it
    says it is for, and who issues it. Everything structural -- ids, type codes,
    jurisdictions, validity, URLs -- is language-independent and already in the English
    cache, so repeating it here would only be a second thing to keep in step.

    The text is kept **verbatim**, machine-translation marker and all. eCertis appends
    `(Automatische Übersetzung)` to strings it translated rather than sourced, and that is
    exactly what a reviewer deciding whether to trust a term needs to see.
    """

    name: str
    description: str
    issuers: tuple[str, ...]


class LocalisationCache(CacheHeader):
    """`l10n_{lang}.json` -- one flat overlay keyed on the eCertis UUID.

    Flat because all three eCertis id spaces are UUIDs and none of them collide (56 EU
    criteria, 172 national sub-criteria and 89 evidences across DE and FR, zero overlap,
    measured 2026-09-11), so one map serves criterion, sub-criterion and evidence alike and
    a lookup never has to know which kind of thing it is holding.

    Separate from `EvidenceCache` rather than a field on it: the English files are what the
    generated criterion Literal and the content hashes are pinned to, and a language is
    something you add later without reopening them.
    """

    language: LanguageCode
    entries: Mapping[str, CachedLocalisation]

    @field_validator("entries", mode="after")
    @classmethod
    def _freeze_entries(
        cls, value: Mapping[str, CachedLocalisation]
    ) -> Mapping[str, CachedLocalisation]:
        """The loaded cache is memoised and shared, so the map has to be read-only too.

        `frozen=True` only stops the *field* being reassigned; the dict behind it would
        still be editable by anyone holding the shared instance.
        """
        return MappingProxyType(dict(value))

    @field_serializer("entries")
    def _dump_entries(
        self, value: Mapping[str, CachedLocalisation]
    ) -> dict[str, CachedLocalisation]:
        """pydantic-core cannot serialise a `mappingproxy`; hand it the dict underneath."""
        return dict(value)
