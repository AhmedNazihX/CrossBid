"""S3.4.2 — `apply_review` and `finalize`: what a reviewer's submission does to the matrix.

Offline and clock-injected, so `reviewed_at` is an assertable value rather than "recent".
The scorer underneath is the real one (`test_scoring.py` is its specification); only the
company lookup is faked, because a re-score that used a different rules engine from the
agent's would make "the scorer re-runs on my statuses" false in exactly the way that
matters.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from crossbid.agent.nodes.review import (
    NOTHING_TO_REVIEW,
    ReviewApplier,
    ReviewError,
    apply_edits,
    build_apply_review,
    finalize,
    review_of,
    utc_now,
)
from crossbid.agent.nodes.score_verdict import VerdictScorer
from crossbid.agent.state import BidState
from crossbid.models.company import CompanyProfile, LegalForm, Tone
from crossbid.models.matrix import Evidence, MatrixRow, ReviewerStatus, RowStatus
from crossbid.models.requirement import Requirement
from crossbid.models.review import ReviewSubmission, RowEdit
from crossbid.models.verdict import Decision, Gap, GapSeverity, Verdict
from tests.conftest import requirement

pytestmark = pytest.mark.anyio

COMPANY_ID = str(uuid.uuid4())
BID_ID = str(uuid.uuid4())
REVIEWED_AT = datetime(2026, 9, 14, 9, 30, tzinfo=UTC)
DOC_ID = str(uuid.uuid4())

PROFILE = CompanyProfile(
    name="Musterfirma IT-Dienstleistungen GmbH",
    country="de",
    legal_form=LegalForm.GMBH,
    language="de",
    tone=Tone.PLAIN,
)


# ------------------------------------------------------------------------ hand-built input


class FakeCompanies:
    async def get(self, *, company_id: uuid.UUID) -> CompanyProfile | None:
        return PROFILE


def row(
    req: Requirement, status: RowStatus = RowStatus.UNSUPPORTED, **overrides: Any
) -> MatrixRow:
    values: dict[str, Any] = {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, req.id)),
        "requirement_id": req.id,
        "status": status,
        "agent_rationale": "Kein Nachweis im Bestand gefunden.",
    }
    return MatrixRow(**(values | overrides))


def cited(req: Requirement) -> MatrixRow:
    return row(
        req,
        RowStatus.SUPPORTED,
        evidence=(
            Evidence(
                document_id=DOC_ID,
                document_name="Jahresabschluss_2025.pdf",
                page=2,
                quote="7,4 Mio. EUR",
            ),
        ),
    )


def state(**overrides: Any) -> BidState:
    reqs = [requirement("Umsatz", identifier="a"), requirement("Personal", identifier="b")]
    values: dict[str, Any] = {
        "bid_id": BID_ID,
        "company_id": COMPANY_ID,
        "bidder_language": "de",
        "requirements": reqs,
        "matrix_rows": [cited(reqs[0]), row(reqs[1])],
        "verdict": Verdict(
            decision=Decision.NO_GO,
            gaps=(
                Gap(
                    requirement_id=reqs[1].id,
                    severity=GapSeverity.BLOCKING,
                    summary="Personal",
                ),
            ),
            rationale="Dieses Angebot wird nicht empfohlen.",
            mandatory_total=2,
            mandatory_supported=1,
            partially_supported_rows=0,
        ),
    }
    return values | overrides  # type: ignore[return-value]


def applier() -> ReviewApplier:
    return ReviewApplier(VerdictScorer(FakeCompanies()), clock=lambda: REVIEWED_AT)


# ------------------------------------------------------------------------- applying edits


def test_a_row_nobody_edited_is_confirmed_rather_than_left_pending() -> None:
    """Silence on a row is assent; leaving it `pending` would make a finished bid look
    abandoned."""
    # Arrange
    reqs = [requirement("Umsatz", identifier="a")]
    rows = [cited(reqs[0])]

    # Act
    applied = apply_edits(rows, ReviewSubmission(decision=Decision.GO), reviewed_at=REVIEWED_AT)

    # Assert
    assert applied[0].reviewer_status is ReviewerStatus.CONFIRMED
    assert applied[0].reviewed_at == REVIEWED_AT
    assert applied[0].status is RowStatus.SUPPORTED


def test_changing_a_status_records_the_row_as_overridden_with_its_reason() -> None:
    # Arrange
    reqs = [requirement("Umsatz", identifier="a")]
    rows = [row(reqs[0], RowStatus.UNSUPPORTED)]
    review = ReviewSubmission(
        decision=Decision.GO,
        row_edits=(
            RowEdit(
                matrix_row_id=rows[0].id,
                status=RowStatus.NOT_APPLICABLE,
                override_reason="Gilt nur für Bietergemeinschaften.",
            ),
        ),
    )

    # Act
    applied = apply_edits(rows, review, reviewed_at=REVIEWED_AT)

    # Assert
    assert applied[0].status is RowStatus.NOT_APPLICABLE
    assert applied[0].reviewer_status is ReviewerStatus.OVERRIDDEN
    assert applied[0].override_reason == "Gilt nur für Bietergemeinschaften."


def test_an_edit_that_restates_the_agents_status_is_a_confirmation_not_an_override() -> None:
    # Arrange
    reqs = [requirement("Umsatz", identifier="a")]
    rows = [row(reqs[0], RowStatus.UNSUPPORTED)]
    review = ReviewSubmission(
        decision=Decision.NO_GO,
        row_edits=(
            RowEdit(
                matrix_row_id=rows[0].id,
                status=RowStatus.UNSUPPORTED,
                override_reason="Bestätigt, der Nachweis fehlt tatsächlich.",
            ),
        ),
    )

    # Act
    applied = apply_edits(rows, review, reviewed_at=REVIEWED_AT)

    # Assert
    assert applied[0].reviewer_status is ReviewerStatus.CONFIRMED
    assert applied[0].override_reason == "Bestätigt, der Nachweis fehlt tatsächlich."


def test_attaching_a_document_leaves_the_agents_finding_standing() -> None:
    """An attachment is new evidence for the reviewer's own eyes, not a disagreement."""
    # Arrange
    reqs = [requirement("Umsatz", identifier="a")]
    rows = [row(reqs[0], RowStatus.UNSUPPORTED)]
    review = ReviewSubmission(
        decision=Decision.CONDITIONAL,
        row_edits=(RowEdit(matrix_row_id=rows[0].id, attached_doc_ids=(DOC_ID,)),),
    )

    # Act
    applied = apply_edits(rows, review, reviewed_at=REVIEWED_AT)

    # Assert
    assert applied[0].reviewer_status is ReviewerStatus.CONFIRMED
    assert applied[0].attached_doc_ids == (DOC_ID,)


def test_attachments_accumulate_without_repeating_themselves() -> None:
    # Arrange
    reqs = [requirement("Umsatz", identifier="a")]
    other = str(uuid.uuid4())
    rows = [row(reqs[0], RowStatus.UNSUPPORTED, attached_doc_ids=(DOC_ID,))]
    review = ReviewSubmission(
        decision=Decision.CONDITIONAL,
        row_edits=(RowEdit(matrix_row_id=rows[0].id, attached_doc_ids=(DOC_ID, other)),),
    )

    # Act
    applied = apply_edits(rows, review, reviewed_at=REVIEWED_AT)

    # Assert
    assert applied[0].attached_doc_ids == (DOC_ID, other)


def test_applying_a_review_never_touches_the_rows_it_was_given() -> None:
    """The agent's original has to stay visible beside the reviewer's version (S4.5.2)."""
    # Arrange
    reqs = [requirement("Umsatz", identifier="a")]
    rows = [row(reqs[0], RowStatus.UNSUPPORTED)]
    review = ReviewSubmission(
        decision=Decision.GO,
        row_edits=(
            RowEdit(
                matrix_row_id=rows[0].id,
                status=RowStatus.NOT_APPLICABLE,
                override_reason="Nicht einschlägig.",
            ),
        ),
    )

    # Act
    applied = apply_edits(rows, review, reviewed_at=REVIEWED_AT)

    # Assert
    assert rows[0].status is RowStatus.UNSUPPORTED
    assert rows[0].reviewer_status is ReviewerStatus.PENDING
    assert applied[0] is not rows[0]


def test_an_edit_naming_a_row_this_bid_has_no_matrix_for_is_refused() -> None:
    # Arrange
    reqs = [requirement("Umsatz", identifier="a")]
    review = ReviewSubmission(
        decision=Decision.GO,
        row_edits=(RowEdit(matrix_row_id="ghost", override_reason="x"),),
    )

    # Act / Assert
    with pytest.raises(ReviewError, match="ghost"):
        apply_edits([cited(reqs[0])], review, reviewed_at=REVIEWED_AT)


def test_a_reviewer_cannot_mark_a_row_supported_with_nothing_cited() -> None:
    """The product's central promise, and `model_copy(update=...)` would have skipped it."""
    # Arrange
    reqs = [requirement("Umsatz", identifier="a")]
    rows = [row(reqs[0], RowStatus.UNSUPPORTED)]
    review = ReviewSubmission(
        decision=Decision.GO,
        row_edits=(
            RowEdit(
                matrix_row_id=rows[0].id,
                status=RowStatus.SUPPORTED,
                override_reason="Wir erfüllen das.",
            ),
        ),
    )

    # Act / Assert
    with pytest.raises(ReviewError, match=rows[0].id):
        apply_edits(rows, review, reviewed_at=REVIEWED_AT)


def test_a_reviewer_may_mark_a_row_supported_by_attaching_the_document() -> None:
    """The same invariant, satisfied the way a reviewer actually satisfies it."""
    # Arrange
    reqs = [requirement("Umsatz", identifier="a")]
    rows = [row(reqs[0], RowStatus.UNSUPPORTED)]
    review = ReviewSubmission(
        decision=Decision.GO,
        row_edits=(
            RowEdit(
                matrix_row_id=rows[0].id,
                status=RowStatus.SUPPORTED,
                override_reason="Jahresabschluss liegt bei.",
                attached_doc_ids=(DOC_ID,),
            ),
        ),
    )

    # Act
    applied = apply_edits(rows, review, reviewed_at=REVIEWED_AT)

    # Assert
    assert applied[0].status is RowStatus.SUPPORTED


# --------------------------------------------------------------------------- the two nodes


async def test_the_scorer_re_runs_on_the_reviewers_statuses() -> None:
    """The story's criterion: the reviewer marks the failing row `not_applicable`, and the
    verdict moves off `no_go` because the rules say so -- not because they asked."""
    # Arrange
    current = state()
    rows = current["matrix_rows"]
    review = ReviewSubmission(
        decision=Decision.GO,
        row_edits=(
            RowEdit(
                matrix_row_id=rows[1].id,
                status=RowStatus.NOT_APPLICABLE,
                override_reason="Gilt nur für Bietergemeinschaften.",
            ),
        ),
    )

    # Act
    update = await applier()(current | {"review": review})  # type: ignore[operator]

    # Assert
    assert update["verdict"].decision is Decision.GO
    assert update["matrix_rows"][1].status is RowStatus.NOT_APPLICABLE


async def test_the_agents_verdict_is_preserved_beside_the_re_scored_one() -> None:
    # Arrange
    current = state()
    review = ReviewSubmission(decision=Decision.NO_GO)

    # Act
    update = await applier()(current | {"review": review})  # type: ignore[operator]

    # Assert
    assert update["agent_verdict"] is current["verdict"]
    assert update["verdict"] is not current["verdict"]


async def test_a_reviewers_decision_does_not_move_the_re_scored_verdict() -> None:
    """They are two answers to two questions, and the difference is the override."""
    # Arrange
    current = state()
    review = ReviewSubmission(decision=Decision.GO, override_reason="Ich kenne den Bestand.")

    # Act
    update = await applier()(current | {"review": review})  # type: ignore[operator]

    # Assert
    assert update["verdict"].decision is Decision.NO_GO


async def test_a_bid_that_was_never_scored_records_no_agent_verdict() -> None:
    """`null` would read as the agent having declined, which is a different answer."""
    # Arrange
    current = state()
    del current["verdict"]  # type: ignore[misc]

    # Act
    update = await applier()(current | {"review": ReviewSubmission(decision=Decision.NO_GO)})  # type: ignore[operator]

    # Assert
    assert "agent_verdict" not in update


async def test_a_resume_with_no_review_at_all_is_refused_rather_than_completed() -> None:
    """A bid must never reach `complete` without a human having been here."""
    with pytest.raises(ReviewError, match=NOTHING_TO_REVIEW):
        await applier()(state())


async def test_finalize_reports_the_reviewers_own_decision() -> None:
    # Arrange
    review = ReviewSubmission(decision=Decision.CONDITIONAL)

    # Act
    update = await finalize(state() | {"review": review})  # type: ignore[operator]

    # Assert
    assert update["decision"] is Decision.CONDITIONAL


async def test_finalize_refuses_a_state_with_no_review_on_it() -> None:
    with pytest.raises(ReviewError, match=NOTHING_TO_REVIEW):
        await finalize(state())


def test_review_of_reads_the_submission_the_interrupt_returned() -> None:
    review = ReviewSubmission(decision=Decision.GO)
    assert review_of({"review": review}) is review


def test_the_default_clock_is_timezone_aware() -> None:
    """`reviews.created_at` and `matrix_rows.reviewed_at` are both `timestamptz`."""
    assert utc_now().tzinfo is not None


def test_the_builder_wires_the_real_scorer() -> None:
    class FakeDatabase:
        def connection(self) -> Any:  # pragma: no cover -- never borrowed here
            raise AssertionError("building the node must not borrow a connection")

    assert isinstance(build_apply_review(FakeDatabase()), ReviewApplier)  # type: ignore[arg-type]
