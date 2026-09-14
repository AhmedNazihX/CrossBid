"""S3.4.2 — `apply_review` and `finalize`: what happens after a human resumes the run.

The two nodes past the interrupt, and the product's safety boundary made concrete. The agent
is advisory (CLAUDE.md): it never submits, and no verdict is final until a person confirms or
overrides it. These are the nodes where that stops being a promise in a docstring.

Four decisions.

**1. The reviewer's statuses go back through the same scorer.** `apply_review` applies the
edits to the matrix and then calls `VerdictScorer.verdict_for` on the revised rows. Not a
copy of the rules, not a shortcut that trusts the reviewer's own decision — the same
function, so "the scorer re-runs on my statuses" is literally true and a reviewer's edit is
measured by the rule the agent was measured by.

**2. The reviewer's decision and the re-scored verdict are kept apart, deliberately.** They
are two different answers to two different questions: the verdict is what the rules say
about the matrix as the reviewer left it, and the decision is what the reviewer decided.
A reviewer who marks two rows `supported` and still says `no_go` is exercising judgement the
rules cannot encode, and that is the point of having them in the loop. So `finalize` records
both, plus the agent's original, and the difference between them *is* the override. Smoothing
it over would throw away the only signal a feedback loop could ever learn from — and would
also be impossible to express, because `Verdict` refuses a decision that contradicts its own
gaps and a human override frequently does.

**3. An unedited row is `confirmed`, not left `pending`.** The reviewer saw the whole matrix
and submitted it; silence on a row is assent to what the agent found, and recording it as
still pending would make a finished bid indistinguishable from an abandoned one. An edit
that changes the status is `overridden` (and `RowEdit` already refuses one without a
reason); an edit that only attaches a document or leaves a comment is `confirmed`, because
the agent's finding still stands.

**4. Every revised row is re-validated, never `model_copy`d into place.** Pydantic's
`model_copy(update=...)` skips validation, so a reviewer marking a row `supported` with
nothing cited would walk straight through `MatrixRow`'s central invariant — the one promise
the product makes. `routers/bids.py` checks the submission against the live matrix first and
answers 422, so a run should never reach the raise below; it is here because "should never"
is not an argument for leaving the bypass open.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Final, Optional

from langchain_core.runnables import RunnableConfig
from pydantic import ValidationError

from crossbid.agent.nodes.score_verdict import VerdictScorer, build_score_verdict
from crossbid.agent.state import AppliedReviewUpdate, BidState, FinalizeUpdate
from crossbid.models.matrix import MatrixRow, ReviewerStatus
from crossbid.models.review import ReviewSubmission, RowEdit
from crossbid.readmodel.bids import ConnectionSource

logger = logging.getLogger(__name__)

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    """The default clock. Timezone-aware, because `reviews.created_at` is `timestamptz`."""
    return datetime.now(UTC)


class ReviewError(RuntimeError):
    """A submitted review cannot be applied. Names the row, never the reviewer's text.

    The message reaches `StageError`, which drops it and keeps only the exception type
    (ADR-0008) — so it is written for the log, and the router is what tells the reviewer.
    """


NOTHING_TO_REVIEW: Final = "the run was resumed without a review"


# ------------------------------------------------------------------------- applying edits


def review_of(state: BidState) -> ReviewSubmission:
    """The review the interrupt was resumed with, or a `ReviewError` saying there was none.

    A resume with no payload is not a reviewer's mistake, it is a caller bypassing the
    router; failing loudly is the only honest answer, because the alternative is a bid that
    reports `complete` without a human ever having looked at it.
    """
    review = state.get("review")
    if review is None:
        raise ReviewError(NOTHING_TO_REVIEW)
    return review


def apply_edits(
    rows: Sequence[MatrixRow], review: ReviewSubmission, *, reviewed_at: datetime
) -> list[MatrixRow]:
    """`rows` with the reviewer's dispositions on them. Every row, edited or not.

    A new list of new rows — nothing here mutates what it was given, so the agent's original
    matrix stays exactly as the checkpoint recorded it and the workspace can keep showing
    what changed (S4.5.2).
    """
    edits = {edit.matrix_row_id: edit for edit in review.row_edits}
    unknown = sorted(set(edits) - {row.id for row in rows})
    if unknown:
        raise ReviewError(f"the review edits rows this bid has no matrix for: {unknown}")
    return [_reviewed(row, edits.get(row.id), reviewed_at=reviewed_at) for row in rows]


def _reviewed(row: MatrixRow, edit: RowEdit | None, *, reviewed_at: datetime) -> MatrixRow:
    """One row as the reviewer left it, re-validated. See decisions 3 and 4."""
    if edit is None:
        return _rebuilt(row, {"reviewer_status": ReviewerStatus.CONFIRMED}, reviewed_at)
    status = row.status if edit.status is None else edit.status
    overridden = edit.status is not None and edit.status is not row.status
    return _rebuilt(
        row,
        {
            "status": status,
            "reviewer_status": (
                ReviewerStatus.OVERRIDDEN if overridden else ReviewerStatus.CONFIRMED
            ),
            "override_reason": edit.override_reason,
            "attached_doc_ids": _merged_ids(row.attached_doc_ids, edit.attached_doc_ids),
        },
        reviewed_at,
    )


def _rebuilt(row: MatrixRow, changes: Mapping[str, Any], reviewed_at: datetime) -> MatrixRow:
    """`row` with `changes` applied, through the model's validators rather than around them.

    `model_copy(update=...)` is the obvious call here and is the wrong one: it assigns
    without validating, so a `supported` with nothing cited would be written to the database
    and rendered to a bidder as proof. Decision 4.
    """
    fields = row.model_dump() | dict(changes) | {"reviewed_at": reviewed_at}
    try:
        return MatrixRow.model_validate(fields)
    except ValidationError as exc:
        raise ReviewError(f"row {row.id} cannot be saved as the reviewer left it") from exc


def _merged_ids(existing: Sequence[str], added: Sequence[str]) -> tuple[str, ...]:
    """Attachments the row already had, plus the new ones, each once and in order."""
    return tuple(dict.fromkeys([*existing, *added]))


# -------------------------------------------------------------------------------- nodes


class ReviewApplier:
    """The `apply_review` node: the reviewer's edits, and the re-score they imply."""

    def __init__(self, scorer: VerdictScorer, *, clock: Clock = utc_now) -> None:
        self._scorer = scorer
        self._clock = clock

    async def __call__(
        self,
        state: BidState,
        # `Optional[...]`, not `RunnableConfig | None`: LangGraph matches this annotation as
        # a *string* under postponed annotations and the modern spelling is silently never
        # injected (CLAUDE.md).
        config: Optional[RunnableConfig] = None,  # noqa: UP045
    ) -> AppliedReviewUpdate:
        """The revised matrix, the agent's verdict preserved, and the re-scored one."""
        review = review_of(state)
        rows = apply_edits(state.get("matrix_rows", []), review, reviewed_at=self._clock())
        rescored = await self._scorer.verdict_for(state, rows)
        agent_verdict = state.get("verdict")
        logger.info(
            "Bid %s reviewed: %d row(s), %d edit(s), re-scored %s, reviewer said %s",
            state.get("bid_id", ""),
            len(rows),
            len(review.row_edits),
            rescored.decision.value,
            review.decision.value,
        )
        update: AppliedReviewUpdate = {"matrix_rows": rows, "verdict": rescored}
        if agent_verdict is not None:
            # Only when there is one to preserve: a bid resumed without ever having been
            # scored would otherwise record `null` as if the agent had declined to answer.
            update["agent_verdict"] = agent_verdict
        return update


async def finalize(
    state: BidState,
    config: Optional[RunnableConfig] = None,  # noqa: UP045
) -> FinalizeUpdate:
    """The `finalize` node: the reviewer's decision, which is what makes the bid final.

    Returning `decision` is also what tells the stage wrapper to write the audit record —
    `graph._project` reads the rest off the state, so the `reviews` row and `bids.decision`
    are written in one transaction under the `complete` stage rather than from a node
    reaching into the read model itself.
    """
    return {"decision": review_of(state).decision}


def build_apply_review(db: ConnectionSource) -> ReviewApplier:
    """The node as the graph wires it, over the same scorer `score_verdict` uses."""
    return ReviewApplier(build_score_verdict(db))
