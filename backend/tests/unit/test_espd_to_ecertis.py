"""S2.5.1 — the whole cross-border path, end to end, offline: DUME → criterion → eCertis.

This file exists because every piece of the differentiator worked in isolation and the chain
did not exist. The cached eCertis register (S1.1.1), the bidder-language lookup (S1.1.2), the
`ecertis_evidence_lookup` tool, `check_reqs` calling it and the workspace card (S4.5.1) were
all in place, but `check_reqs` only looks eCertis up when a requirement carries an
`ecertis_criterion_id`, and **nothing in the running system ever set one**: no fixture PDF
contains an ESPD UUID and `prompts/extract.md` forbids inferring one (ADR-0007).

So the assertion below is the story's acceptance criterion, and it needs neither a model nor
a socket: the committed French DUME is read, its criteria become requirements, and one of
them is checked into a matrix row that names the **German** paper which satisfies the
**French** buyer's criterion. The eCertis register is cached in the repository, and an
exclusion ground never reaches the model (`check_loop` answers it before the loop begins),
so the most valuable path in the product is also the cheapest one to pin.
"""

from __future__ import annotations

import pytest

from crossbid.agent.espd_requirements import requirements_from_espd
from crossbid.agent.nodes.check_loop import Bidder, check_requirement
from crossbid.ingestion.espd import parse_espd_request
from crossbid.models.matrix import RowStatus
from crossbid.models.requirement import Checkability, Requirement, RequirementSource
from tests.conftest import ScriptedModel, check_context, espd_request_bytes

pytestmark = pytest.mark.anyio

BID_ID = "bid-fr-1"
DOCUMENT = "DUME_acheteur.xml"
TAXES = "b61bbeb7-690e-4a40-bc68-d6d4ecfaa3d4"
"""`CRITERION.EXCLUSION.CONTRIBUTIONS.PAYMENT_OF_TAXES`, declared by the French buyer."""

GERMAN_BIDDER = Bidder(country="de", language="de")


def french_tender_requirements() -> tuple[Requirement, ...]:
    """The committed DUME, read and mapped exactly as `parse_docs` does it."""
    return requirements_from_espd(
        parse_espd_request(espd_request_bytes()),
        bid_id=BID_ID,
        document_name=DOCUMENT,
        source_lang="fr",
    )


async def test_a_french_buyers_criterion_becomes_a_row_naming_the_german_paper() -> None:
    """The wedge in one test: French criterion in, German evidence out, no model asked."""
    # Arrange — the tax-payment exclusion ground, as the French buyer declared it.
    requirement = next(
        row for row in french_tender_requirements() if row.ecertis_criterion_id == TAXES
    )
    assert requirement.checkable is Checkability.DOCUMENT_SUBMISSION
    model = ScriptedModel([])

    # Act
    row = await check_requirement(requirement, check_context(model, bidder=GERMAN_BIDDER))

    # Assert
    assert model.prompts == [] and model.verdict_prompts == []
    assert row.ecertis_evidence is not None
    assert row.ecertis_evidence.criterion_id == TAXES
    assert row.ecertis_evidence.country == "de"
    assert row.ecertis_evidence.found is True
    assert row.ecertis_evidence.evidence_names != ()
    # The reviewer is told to attach a paper rather than being sold an unevidenced pass.
    assert row.status is RowStatus.PARTIALLY_SUPPORTED
    assert row.requirement_id == requirement.id


async def test_every_criterion_of_the_fixture_resolves_to_an_ecertis_answer() -> None:
    """`lookup_evidence` is total, so 30 criteria produce 30 cards — some with no national
    entry, which is a legitimate answer and not a failure (ADR-0007)."""
    # Arrange
    requirements = french_tender_requirements()

    # Act
    rows = [
        await check_requirement(
            requirement, check_context(ScriptedModel([]), bidder=GERMAN_BIDDER)
        )
        for requirement in requirements
        if requirement.checkable is Checkability.DOCUMENT_SUBMISSION
    ]

    # Assert
    assert len(rows) == 24
    assert all(row.ecertis_evidence is not None for row in rows)
    assert sum(1 for row in rows if row.ecertis_evidence and row.ecertis_evidence.found) > 0


async def test_the_rows_that_reach_the_matrix_are_marked_as_coming_from_the_dume() -> None:
    """A reviewer must never mistake a criterion the buyer declared for a quote we found."""
    # Act
    requirements = french_tender_requirements()

    # Assert
    assert {row.source for row in requirements} == {RequirementSource.ESPD_REQUEST}
    assert {row.page for row in requirements} == {None}
    assert {row.document_name for row in requirements} == {DOCUMENT}
