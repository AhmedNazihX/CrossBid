"""S3.4.1 — `score_verdict`: the node that turns a finished matrix into a recommendation.

Thin by design. Every rule lives in `agent/scoring.py`, which is pure and tested as such;
this module is the seam that fetches the one thing the rules need and the state does not
carry — the bidder's own profile. Keeping the split means the story's criteria are asserted
against a function with no database in it, and what is tested here is only the wiring.

**The profile is fetched rather than kept in state, and it supplies two different things.**
`tone` decides how the explanation is written (graded Easy 2), and the typed facts —
headcount, turnover — are what let a gap say "29 FTE required, 21 recorded" instead of
repeating the clause. `plan_checks` already reads the same row for `bidder_country`, so this
is a second read of one row per run; the alternative, widening the state with the whole
profile, would push it through every checkpoint and every lane's `Send` payload for the
benefit of one node.

**A profile that cannot be read costs the numbers, never the verdict.** Same choice
`plan_checks` makes about the country, and for the same reason: a company row that has
drifted out of its schema must not lose a bidder the matrix they paid for. The rules run
unchanged, `actual` goes unstated, the tone falls back to `plain`, and the log says why.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from typing import Optional

from langchain_core.runnables import RunnableConfig

from crossbid.agent.nodes.check_reqs import CompanyLookup
from crossbid.agent.scoring import score
from crossbid.agent.state import BidState, ScoreUpdate, bidder_language_of
from crossbid.models.company import CompanyProfile, Tone
from crossbid.models.matrix import MatrixRow
from crossbid.models.verdict import Verdict
from crossbid.readmodel.bids import ConnectionSource
from crossbid.readmodel.companies import CompaniesReadModel, CompanyReadModelError

logger = logging.getLogger(__name__)

DEFAULT_TONE = Tone.PLAIN
"""How the explanation is written when the company's own setting cannot be read."""


class VerdictScorer:
    """The `score_verdict` node: the matrix, the profile, and the rules. No model.

    A callable object for the reason every node here is one — the graph calls
    `(state, config)` and the lookup has to be injected from somewhere. Holds no per-run
    state, so one instance serves every bid.
    """

    def __init__(self, companies: CompanyLookup) -> None:
        self._companies = companies

    async def __call__(
        self,
        state: BidState,
        # `Optional[...]`, not `RunnableConfig | None`: LangGraph matches this annotation as
        # a *string* under postponed annotations and the modern spelling is silently never
        # injected (CLAUDE.md).
        config: Optional[RunnableConfig] = None,  # noqa: UP045
    ) -> ScoreUpdate:
        """The bid's verdict, scored from the state's own requirements and matrix rows."""
        return {"verdict": await self.verdict_for(state)}

    async def verdict_for(
        self, state: BidState, rows: Sequence[MatrixRow] | None = None
    ) -> Verdict:
        """Score `state`, optionally against `rows` instead of the matrix it carries.

        The override is what S3.4.2 re-scores the reviewer's statuses through. It is a
        parameter rather than a second scoring path because "the scorer re-runs on my
        statuses" is only a true sentence if it is the *same* scorer: a copy would be free
        to drift, and the rule a reviewer's edit is measured against would stop being the
        rule the agent was measured against.
        """
        profile = await self._profile(state.get("company_id", ""))
        verdict = score(
            state.get("requirements", []),
            state.get("matrix_rows", []) if rows is None else rows,
            language=bidder_language_of(state),
            tone=profile.tone if profile is not None else DEFAULT_TONE,
            profile=profile,
        )
        logger.info(
            "Bid %s scored %s: %d gap(s), %d of %d mandatory supported",
            state.get("bid_id", ""),
            verdict.decision.value,
            len(verdict.gaps),
            verdict.mandatory_supported,
            verdict.mandatory_total,
        )
        return verdict

    async def _profile(self, company_id: str) -> CompanyProfile | None:
        """The bidder's profile, or `None` and a line in the log. See the module docstring.

        The two caught failures are the two a *run* should survive: a `profile` jsonb that
        no longer validates, and a company id that is not a UUID. A database that is down is
        neither and raises, so the stage wrapper reports `scoring failed` rather than
        scoring the bid against a bidder from nowhere.
        """
        try:
            return await self._companies.get(company_id=uuid.UUID(company_id))
        except (CompanyReadModelError, ValueError) as exc:
            logger.warning(
                "No profile for company %s (%s): the verdict states no recorded figures",
                company_id,
                type(exc).__name__,
            )
            return None


def build_score_verdict(db: ConnectionSource) -> VerdictScorer:
    """The node as the graph wires it: the real companies read model over the pool."""
    return VerdictScorer(CompaniesReadModel(db))
