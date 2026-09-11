"""`ecertis_evidence_lookup` — the tool that answers "which paper proves this, here?".

S1.1.2. Reads the committed eCertis cache, so `external=False`: no socket, no cost, no rate
limit, and it works with the network unplugged. That is why the description can afford to
encourage the model to call it for every criterion-shaped requirement.

Three choices in here are worth the ink.

**The criterion id is typed on the generated `EcertisCriterionId` Literal.** That puts all
56 legal UUIDs in the tool schema the model is bound with, so an invented id is rejected by
the schema instead of becoming a plausible-looking miss. It is the payoff for S1.1.3
generating the enum in the first place. The underlying `lookup_evidence` still takes a
plain string and still never raises — `check_reqs` calls it directly, and a run must not
die because a cache file moved.

**The tool returns a dict, not a model and not prose.** langchain-core 1.6.2 stringifies
tool output with `json.dumps(..., ensure_ascii=False)` and only falls back to `str()` when
that raises, so a dict arrives as JSON with `zuständiges Finanzamt` intact, where a model
instance would arrive as a Python repr.

**`ToolContext` is accepted and unused.** The eCertis answer depends on the criterion and
the bidder's country, never on the tenant, so there is nothing to scope. Taking the context
anyway keeps every tool's `build_tool` the same shape for the registry (S1.4.1).
"""

from __future__ import annotations

from typing import Annotated, Any

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from crossbid.models.ecertis_criteria import EcertisCriterionId
from crossbid.models.matrix import EcertisEvidence
from crossbid.reference.ecertis_lookup import (
    DEFAULT_BIDDER_LANGUAGE,
    EvidenceAnswer,
    EvidenceStatus,
    lookup_evidence,
)
from crossbid.tools import ToolContext, ToolManifest

Alpha2 = Annotated[str, StringConstraints(pattern=r"^[A-Za-z]{2}$")]

DESCRIPTION = """\
Look up which national document proves one EU procurement criterion (an ESPD exclusion \
ground or selection criterion) for a bidder established in a given country, in the \
bidder's own language and in English.

Use this whenever a tender requirement maps to an ESPD criterion and you need to name the \
paper the bidder should attach — for example, a French tender asking about payment of \
taxes, where a German bidder must attach a Freistellungsbescheinigung rather than the \
French attestation. Cached from the European Commission's eCertis register; it costs \
nothing and needs no network.

Only Germany (DE) and France (FR) are cached; any other bidder country returns \
status "not_found". "not_found" is also the honest answer when eCertis records no \
national document for that criterion in that country — it is not an error, and it does \
not mean the requirement is unmet.\
"""


MANIFEST = ToolManifest(
    name="ecertis_evidence_lookup",
    description=DESCRIPTION,
    external=False,
    default_enabled=True,
)


class EcertisEvidenceArgs(BaseModel):
    """What the model must supply. Nothing free-text, so nothing to sanitise."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    criterion_id: EcertisCriterionId = Field(
        description="The EU-level eCertis criterion UUID, from the requirement being checked"
    )
    bidder_country: Alpha2 = Field(
        description=(
            "Where the bidder is established, ISO 3166-1 alpha-2 (e.g. 'de'). This is the "
            "bidder's country, NOT the country running the tender."
        )
    )
    language: Alpha2 = Field(
        default=DEFAULT_BIDDER_LANGUAGE,
        description=(
            "The bidder's language, ISO 639-1. Falls back to English text when eCertis "
            "has no translation."
        ),
    )


def build_tool(context: ToolContext) -> BaseTool:
    """The bound tool. `context` is unused here — see the module docstring."""
    del context

    def run(
        criterion_id: str, bidder_country: str, language: str = DEFAULT_BIDDER_LANGUAGE
    ) -> dict[str, Any]:
        answer = lookup_evidence(criterion_id, bidder_country, language)
        return answer.model_dump(mode="json")

    return StructuredTool.from_function(
        func=run,
        name=MANIFEST.name,
        description=MANIFEST.description,
        args_schema=EcertisEvidenceArgs,
    )


def to_matrix_evidence(
    criterion_id: EcertisCriterionId, answer: EvidenceAnswer
) -> EcertisEvidence:
    """The answer as the object a matrix row carries (S3.3.1).

    `criterion_id` is passed separately rather than read off `answer`: the caller already
    holds it narrowed to the Literal, while the answer keeps a plain string so that
    `lookup_evidence` can stay total over ids the cache does not know.

    Names and issuers are taken in the **bidder's** language, because the matrix is what
    the bidder reads; the English names stay one call away in `answer`. `description`
    carries the criterion's own name in that language — the one thing in the answer that
    has no dedicated field on the row, and the thing a reviewer needs to recognise which
    ESPD question they are looking at.
    """
    return EcertisEvidence(
        criterion_id=criterion_id,
        criterion_name=answer.criterion_name,
        country=answer.country,
        found=answer.status is EvidenceStatus.FOUND,
        evidence_names=tuple(evidence.name_localised for evidence in answer.evidences),
        issuers=tuple(
            sorted(
                {
                    issuer
                    for evidence in answer.evidences
                    for issuer in evidence.issuers_localised
                }
            )
        ),
        description=answer.criterion_name_localised or None,
    )
