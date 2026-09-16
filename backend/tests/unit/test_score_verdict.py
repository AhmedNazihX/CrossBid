"""S3.4.1 — `score_verdict`, the node: the wiring, not the rules.

Every rule the scorer applies is asserted in `test_scoring.py` against a pure function.
What is left for the node is the seam it exists for — fetching the bidder's profile, using
its `tone` and its figures, and surviving a profile it cannot read — and that is all this
module tests. Duplicating a decision table here would mean two places to update when a rule
changes, and the second one would be the one that rots.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import pytest
from langgraph.store.memory import InMemoryStore

from crossbid.agent.nodes.score_verdict import (
    DEFAULT_TONE,
    VerdictScorer,
    build_score_verdict,
)
from crossbid.agent.state import BidState
from crossbid.memory.profile import RememberedProfile
from crossbid.models.company import CompanyProfile, LegalForm, Tone
from crossbid.models.matrix import MatrixRow, RowStatus
from crossbid.models.requirement import (
    Requirement,
    Threshold,
    ThresholdComparator,
    ThresholdUnit,
)
from crossbid.models.verdict import Decision
from crossbid.readmodel.companies import CompanyReadModelError
from tests.conftest import requirement

pytestmark = pytest.mark.anyio

COMPANY_ID = str(uuid.uuid4())
BID_ID = str(uuid.uuid4())

FTE_MINIMUM = Threshold(
    comparator=ThresholdComparator.AT_LEAST, value=29, unit=ThresholdUnit.FTE
)


# ------------------------------------------------------------------------ hand-built input


def profile(**overrides: Any) -> CompanyProfile:
    values: dict[str, Any] = {
        "name": "Musterfirma IT-Dienstleistungen GmbH",
        "country": "de",
        "legal_form": LegalForm.GMBH,
        "language": "de",
        "tone": Tone.PLAIN,
    }
    return CompanyProfile(**(values | overrides))


class FakeCompanies:
    """The `CompanyLookup` seam, scripted. Records the id it was asked for."""

    def __init__(self, answer: CompanyProfile | None = None, *, raises: bool = False) -> None:
        self.answer = answer
        self.asked: list[uuid.UUID] = []
        self._raises = raises

    async def get(self, *, company_id: uuid.UUID) -> CompanyProfile | None:
        self.asked.append(company_id)
        if self._raises:
            raise CompanyReadModelError("the profile column no longer validates")
        return self.answer


def row(req: Requirement, status: RowStatus = RowStatus.UNSUPPORTED) -> MatrixRow:
    return MatrixRow(
        id=str(uuid.uuid5(uuid.NAMESPACE_URL, req.id)),
        requirement_id=req.id,
        status=status,
        agent_rationale="checked by a fake",
    )


def state(**overrides: Any) -> BidState:
    req = requirement(
        "Mindestens 29 Vollzeitäquivalente", identifier="a", threshold=FTE_MINIMUM
    )
    values: dict[str, Any] = {
        "bid_id": BID_ID,
        "company_id": COMPANY_ID,
        "bidder_language": "de",
        "requirements": [req],
        "matrix_rows": [row(req)],
    }
    return values | overrides  # type: ignore[return-value]


# --------------------------------------------------------------------------------- tests


async def test_the_node_scores_the_states_own_requirements_and_rows() -> None:
    # Arrange
    scorer = VerdictScorer(FakeCompanies(profile()))

    # Act
    update = await scorer(state())

    # Assert
    assert update["verdict"].decision is Decision.NO_GO
    assert len(update["verdict"].gaps) == 1


async def test_the_profile_is_read_once_for_the_state_s_company() -> None:
    # Arrange
    companies = FakeCompanies(profile())

    # Act
    await VerdictScorer(companies)(state())

    # Assert
    assert companies.asked == [uuid.UUID(COMPANY_ID)]


async def test_the_companys_tone_decides_how_the_verdict_is_written() -> None:
    """Graded Easy 2: the setting is on the company row, and this is where it is honoured."""
    # Arrange
    plain = VerdictScorer(FakeCompanies(profile(tone=Tone.PLAIN)))
    brief = VerdictScorer(FakeCompanies(profile(tone=Tone.BRIEF)))

    # Act
    plain_verdict = (await plain(state()))["verdict"]
    brief_verdict = (await brief(state()))["verdict"]

    # Assert
    assert brief_verdict.rationale != plain_verdict.rationale
    assert len(brief_verdict.rationale) < len(plain_verdict.rationale)


async def test_the_bids_language_decides_which_words_are_used_not_the_companys() -> None:
    """A German company bidding in French reads the verdict in the bid's language: the
    state's `bidder_language` is the run's decision and the profile's is only a default."""
    # Arrange
    scorer = VerdictScorer(FakeCompanies(profile(language="de")))

    # Act
    verdict = (await scorer(state(bidder_language="fr")))["verdict"]

    # Assert
    assert verdict.rationale.startswith("Cette offre n'est pas recommandée.")


async def test_the_profiles_figures_turn_a_gap_into_a_shortfall() -> None:
    # Arrange
    scorer = VerdictScorer(FakeCompanies(profile(staff_fte_relevant=21)))

    # Act
    verdict = (await scorer(state()))["verdict"]

    # Assert
    assert (verdict.gaps[0].required, verdict.gaps[0].actual) == ("29 FTE", "21 FTE")


async def test_a_profile_that_cannot_be_read_costs_the_numbers_and_not_the_verdict(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Arrange
    scorer = VerdictScorer(FakeCompanies(raises=True))

    # Act
    with caplog.at_level(logging.WARNING, logger="crossbid.agent.nodes.score_verdict"):
        verdict = (await scorer(state()))["verdict"]

    # Assert
    assert verdict.decision is Decision.NO_GO
    assert verdict.gaps[0].actual is None
    assert "CompanyReadModelError" in caplog.text


async def test_a_company_id_that_is_not_a_uuid_is_survived_the_same_way() -> None:
    # Arrange
    scorer = VerdictScorer(FakeCompanies(profile()))

    # Act
    verdict = (await scorer(state(company_id="not-a-uuid")))["verdict"]

    # Assert
    assert verdict.decision is Decision.NO_GO


async def test_a_company_with_no_row_falls_back_to_the_default_tone() -> None:
    # Arrange
    scorer = VerdictScorer(FakeCompanies(None))
    expected = VerdictScorer(FakeCompanies(profile(tone=DEFAULT_TONE)))

    # Act
    without = (await scorer(state()))["verdict"]
    with_profile = (await expected(state()))["verdict"]

    # Assert
    assert without.rationale == with_profile.rationale


async def test_a_database_that_is_down_fails_the_stage_rather_than_scoring_blind() -> None:
    """Only the two failures a *run* should survive are caught; an outage is not one."""

    class Unreachable:
        async def get(self, *, company_id: uuid.UUID) -> CompanyProfile | None:
            raise OSError("connection refused")

    with pytest.raises(OSError, match="connection refused"):
        await VerdictScorer(Unreachable())(state())


async def test_the_node_logs_what_it_decided(caplog: pytest.LogCaptureFixture) -> None:
    # Arrange
    scorer = VerdictScorer(FakeCompanies(profile()))

    # Act
    with caplog.at_level(logging.INFO, logger="crossbid.agent.nodes.score_verdict"):
        await scorer(state())

    # Assert
    assert f"Bid {BID_ID} scored no_go" in caplog.text


def test_the_builder_wires_the_agents_memory_over_the_read_model() -> None:
    """ADR-0077. The verdict states the bidder's figures, so it states the remembered ones."""

    # Arrange
    class FakeDatabase:
        def connection(self) -> Any:  # pragma: no cover -- never borrowed here
            raise AssertionError("building the node must not borrow a connection")

    # Act
    scorer = build_score_verdict(FakeDatabase(), InMemoryStore())  # type: ignore[arg-type]

    # Assert
    assert isinstance(scorer, VerdictScorer)
    assert isinstance(scorer._companies, RememberedProfile)
