"""The human review step — the product's safety boundary.

The agent is advisory: it never submits, and no verdict is final until a reviewer confirms or
overrides it. These are the shapes that cross the interrupt, resuming the graph with
`Command(resume=...)`.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from crossbid.models.matrix import MAX_QUOTE_CHARS, RowStatus
from crossbid.models.verdict import Decision

MAX_COMMENT_CHARS = 4000


def _blank_is_not_a_reason(value: str | None) -> str | None:
    """Whitespace is not an explanation.

    The browser already trims before it sends (`normalisedEdit` in
    `frontend/components/matrix/row-edit-rules.ts`), so a reason of spaces never reaches here
    from our own UI. The server is the authority and must not be the laxer of the two: without
    this, `"   "` is truthy and buys an unexplained override through the API, and the row is
    stored as `overridden` with a reason a human cannot read.
    """
    if value is None:
        return None
    return value.strip() or None


ReviewReason = Annotated[
    str | None, Field(max_length=MAX_COMMENT_CHARS), AfterValidator(_blank_is_not_a_reason)
]
"""A free-text reason, trimmed, with blank normalised to "no reason given"."""


class RowEdit(BaseModel):
    """A reviewer's change to one matrix row."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    matrix_row_id: str
    status: RowStatus | None = Field(default=None, description="None leaves the agent's status")
    override_reason: ReviewReason = None
    attached_doc_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _changing_a_status_needs_a_reason(self) -> Self:
        """Disagreeing with the agent has to be explained, or the override is unauditable."""
        if self.status is not None and not self.override_reason:
            raise ValueError(
                "changing a row's status requires override_reason, so the disagreement is "
                "recorded"
            )
        return self

    @model_validator(mode="after")
    def _edit_must_do_something(self) -> Self:
        if self.status is None and not self.override_reason and not self.attached_doc_ids:
            raise ValueError(
                "a row edit must change a status, give a reason, or attach a document"
            )
        return self


class ReviewSubmission(BaseModel):
    """What the reviewer sends back to resume the graph.

    `decision` is the reviewer's own call. It may disagree with the agent's, and when it does
    the disagreement is recorded rather than smoothed over — that record is what a feedback
    loop would later learn from.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: Decision
    row_edits: tuple[RowEdit, ...] = ()
    override_reason: ReviewReason = Field(
        default=None,
        description="Required when the reviewer's decision differs from the agent's",
    )

    @model_validator(mode="after")
    def _row_ids_are_unique(self) -> Self:
        """Two edits to one row would make the result depend on application order."""
        ids = [edit.matrix_row_id for edit in self.row_edits]
        duplicates = {i for i in ids if ids.count(i) > 1}
        if duplicates:
            raise ValueError(f"duplicate row edits for: {sorted(duplicates)}")
        return self


class Citation(BaseModel):
    """Where a chat answer got its facts. No uncited claims in chat either."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: str
    document_name: str
    page: int = Field(ge=1)
    quote: str | None = Field(default=None, max_length=MAX_QUOTE_CHARS)
    """Bounded like `Evidence.quote`, and for the same reason.

    Both producers already truncate -- `RagHit` caps what it returns and `get_matrix`
    truncates to this constant -- so this bound changes no behaviour today. It is here
    because the invariant belongs to the type: a quote is document text, and ADR-0008's rule
    is that untrusted input is constrained where it is *defined*, not at each place that
    happens to remember. The next producer of a `Citation` inherits the bound instead of
    having to rediscover it."""


class ChatRole(StrEnum):
    """Who said it."""

    USER = "user"
    ASSISTANT = "assistant"


class ChatTurn(BaseModel):
    """One turn of "ask the tender". Runs on its own thread, `bid:{id}:chat`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    role: ChatRole
    content: str
    citations: tuple[Citation, ...] = ()
