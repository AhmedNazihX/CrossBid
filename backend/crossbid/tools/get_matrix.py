"""S3.5.1 — `get_matrix`: what this bid's compliance matrix already says, as citable rows.

The third tool "ask the tender" is made of (`docs/project-plan.md`, F3.5). The two RAG tools
read documents; this one reads the answer the run has already produced, so that "why is the
turnover row not supported?" is answered from the matrix rather than by checking the
requirement a second time at the bidder's expense.

Four decisions.

**1. One citable passage per row, and it is the buyer's clause — never the agent's words.**
A chat answer may only cite a passage a tool returned (`agent/chat_graph.py`), so a tool
that returned nothing citable could only ever produce an uncited answer about the matrix.
What this returns as citable is the requirement's own verbatim clause with the document and
page it was quoted from — the same triple `Evidence` carries, because it is the same kind of
fact. The row's *evidence* quotes are deliberately not re-offered here: they live in the
bidder's own documents, `company_rag_search` is the tool that reads those, and one passage
reachable through two tools is one passage a single answer can cite twice.

**2. A row whose requirement has no page contributes a `None` slot, not a missing one.**
A requirement read from a published DUME or from TED's structured fields has `page is None`
by construction (migration 0008), and `Citation` requires a page because a citation a
reviewer cannot open is not a citation. Dropping such rows from the numbering would make
the `[n]` the model reads and the `[n]` resolved here mean different rows — the exact drift
`check_loop` keeps its empty tuples to prevent. So the slot stays and holds `None`; the
model is told in the rendering that the passage cannot be cited, and a reference to it is
dropped the same way a reference to a passage nobody retrieved is.

**3. The agent's rationale is stated plainly, outside the data block.** It is Crossbid's own
sentence about the row, already bounded to 600 characters when it was written and already
shown to a human on the matrix; it has no document and no page, so wrapping it as a
`DOCUMENT` would claim a citable location it does not have. That is the same call
`check_loop` makes for the eCertis lines, for the same reason. The buyer's clause — the one
thing here that *is* document text — goes inside the block like every other quoted passage.

**4. `external=False`, although the call leaves the process.** The flag exists to tell an
operator which tools open a socket to somebody else: something slow, costed, or rate
limited, and therefore something they may want to switch off. This reads the deployment's
own Postgres, which every other route is already reading and without which the API does not
serve a request at all. Calling it external would put it in the same category as a TED
search and invite an operator to turn off the only way the agent can see its own answer.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, ConfigDict, Field

from crossbid.guards.wrap import DataBlock, wrap_as_data
from crossbid.models.matrix import MAX_QUOTE_CHARS, MatrixRow, ReviewerStatus, RowStatus
from crossbid.models.requirement import Requirement
from crossbid.models.review import Citation
from crossbid.readmodel.matrix import fetch_matrix_rows
from crossbid.readmodel.requirements import fetch_requirements
from crossbid.tools.manifest import ToolContext, ToolManifest
from crossbid.tools.rag import RagToolError, require_connection_source, scope_uuid

DEFAULT_ROWS: Final = 10
"""How many rows one call returns when the model does not ask. The DE pack's matrix is 258
rows (ADR-0012), so "the matrix" is never a thing that fits in a tool message; ten rows plus
their clauses is already a page of German."""

MAX_ROWS: Final = 25
"""The most one call may return. Above this the block is longer than the answer it supports,
and the model is better served by asking again with a status filter."""

MAX_NOTE_CHARS: Final = 300
"""How much of `agent_rationale` is repeated here. The column is capped at 600 when it is
written (`check_loop.MAX_RATIONALE_CHARS`); this is the half of it that fits beside ten other
rows, and it is a *second* cap on a different consumer rather than the same one restated."""

DESCRIPTION: Final = """\
Read this bid's compliance matrix: the status Crossbid gave each extracted requirement, the \
buyer's own clause behind it, and whether a human has reviewed the row yet.

Use it for questions about the answer rather than about the documents — "which requirements \
are not supported?", "how many rows still need me?", "why is the turnover requirement only \
partially supported?". Filter by status to ask about one group; the counts for the whole \
matrix are returned whatever the filter, so a question about totals needs one call.

It returns the buyer's clause for each row as a quoted passage with its document and page, \
so an answer about a row can cite the clause the row is about. It does NOT return the \
bidder's own evidence documents: use company_rag_search for those, and tender_rag_search to \
read more of the tender than the clause itself.\
"""

MANIFEST: Final = ToolManifest(
    name="get_matrix",
    description=DESCRIPTION,
    external=False,
    default_enabled=True,
)

NO_ROWS: Final = (
    "This bid's compliance matrix has no rows{filter}. That is an answer about the run, not "
    "an error: either the check has not finished yet, or nothing matched. Say so rather than "
    "describing rows you have not seen."
)

HEADER: Final = (
    "This bid's compliance matrix holds {total} row(s): {counts}.\n"
    "Showing {shown} of them{filter}, in document and page order. Each row names the buyer's "
    "clause behind it by a number in square brackets, and those clauses follow in one data "
    "block in the same order. The DOCUMENT header above a clause is the only authority for "
    "the file name and page you cite it by.\n{lines}\n"
    "A row marked (not citable) came from the buyer's published ESPD request or from TED's "
    "structured fields rather than from a page of a PDF, so it has no page to cite: name it "
    "in words instead of citing it."
)

ROW_LINE: Final = "  {clause} {status}{reviewed} — {document} — Crossbid's note: {note}"
NOT_CITABLE: Final = "(not citable)"
REVIEWED_SUFFIX: Final = ", {reviewer_status} by the reviewer"
NO_NOTE: Final = "none recorded"
PAGE_SUFFIX: Final = " page {page}"


class MatrixQueryArgs(BaseModel):
    """What the model may choose: which group of rows, and how many. Nothing that widens
    the scope — the company and the bid are closed over when the tool is built."""

    model_config = ConfigDict(extra="forbid")

    status: RowStatus | None = Field(
        default=None,
        description=(
            "Only rows Crossbid gave this status. Omit for all of them. 'supported' is a "
            "cited finding, 'partially_supported' the honest answer when the documents do "
            "not settle it, 'unsupported' evidence against, 'not_applicable' a requirement "
            "addressed to somebody else."
        ),
    )
    limit: int = Field(
        default=DEFAULT_ROWS,
        ge=1,
        le=MAX_ROWS,
        description="How many rows to return, in document and page order.",
    )


class MatrixLine(BaseModel):
    """One row as the model is shown it. Carries no quote: the clause is in the block."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: RowStatus
    reviewer_status: ReviewerStatus
    document_name: str
    page: int | None
    citation: int | None = Field(
        default=None,
        description="1-based index into the result's clauses, or None when it has no page",
    )
    note: str


class MatrixDigest(BaseModel):
    """What one `get_matrix` call found, and the passages an answer may cite from it.

    This rides on the `ToolMessage.artifact` exactly as `RagSearchResult` does, and
    `chat_graph` reads `citations` off it rather than off the model's prose. `citations` is
    positional: index `n - 1` is the passage the rendering numbered `[n]`, and a `None` there
    is a clause with no page rather than a gap in the numbering (decision 2).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    total: int = Field(ge=0, description="Rows in the whole matrix, before any filter")
    counts: dict[str, int] = Field(default_factory=dict, description="Rows per status")
    status_filter: RowStatus | None = None
    lines: tuple[MatrixLine, ...] = ()
    citations: tuple[Citation | None, ...] = ()

    def render(self) -> str:
        """The tool message the model reads: the counts and the rows, then one data block."""
        if not self.lines:
            return NO_ROWS.format(filter=self._filter_phrase())
        rendered = "\n".join(self._line(line) for line in self.lines)
        blocks = [
            _clause_block(citation) for citation in self.citations if citation is not None
        ]
        header = HEADER.format(
            total=self.total,
            counts=self._counts_phrase(),
            shown=len(self.lines),
            filter=self._filter_phrase(),
            lines=rendered,
        )
        if not blocks:
            return header
        return f"{header}\n{wrap_as_data(blocks).text}"

    def _filter_phrase(self) -> str:
        return (
            "" if self.status_filter is None else f" with status '{self.status_filter.value}'"
        )

    def _counts_phrase(self) -> str:
        """Every status, including the ones at zero: "no unsupported rows" is an answer, and
        a status missing from the list reads as a status nobody has counted."""
        return ", ".join(
            f"{self.counts.get(status.value, 0)} {status.value}" for status in RowStatus
        )

    def _line(self, line: MatrixLine) -> str:
        clause = NOT_CITABLE if line.citation is None else f"[{line.citation}]"
        page = "" if line.page is None else PAGE_SUFFIX.format(page=line.page)
        reviewed = (
            ""
            if line.reviewer_status is ReviewerStatus.PENDING
            else REVIEWED_SUFFIX.format(reviewer_status=line.reviewer_status.value)
        )
        return ROW_LINE.format(
            clause=clause,
            status=line.status.value,
            reviewed=reviewed,
            document=f"{line.document_name}{page}",
            note=line.note or NO_NOTE,
        )


def _clause_block(citation: Citation) -> DataBlock:
    """The buyer's clause as untrusted data, headed with the name a citation will carry."""
    return DataBlock(
        text=citation.quote or "",
        label=citation.document_name,
        pages=(citation.page,),
    )


def digest_of(
    rows: Sequence[MatrixRow],
    requirements: Sequence[Requirement],
    *,
    status: RowStatus | None,
    limit: int,
) -> MatrixDigest:
    """Join the matrix to its requirements and take the first `limit` of the filtered rows.

    Pure, so every branch below is testable without a database. Rows whose requirement is
    missing are dropped rather than shown without a clause: the two projections are written
    by the same graph and a row without its requirement is a bug in the writer, not a row a
    bidder should be told about in prose that could not name what it is about.
    """
    by_id: Mapping[str, Requirement] = {item.id: item for item in requirements}
    counts = {value.value: 0 for value in RowStatus}
    lines: list[MatrixLine] = []
    citations: list[Citation | None] = []

    for row in rows:
        counts[row.status.value] = counts.get(row.status.value, 0) + 1
        requirement = by_id.get(row.requirement_id)
        if requirement is None or (status is not None and row.status is not status):
            continue
        if len(lines) >= limit:
            continue
        citations.append(_citation_of(requirement))
        lines.append(
            MatrixLine(
                status=row.status,
                reviewer_status=row.reviewer_status,
                document_name=requirement.document_name,
                page=requirement.page,
                citation=len(citations) if citations[-1] is not None else None,
                note=row.agent_rationale.strip()[:MAX_NOTE_CHARS],
            )
        )

    return MatrixDigest(
        total=len(rows),
        counts=counts,
        status_filter=status,
        lines=tuple(lines),
        citations=tuple(citations),
    )


def _citation_of(requirement: Requirement) -> Citation | None:
    """The requirement's clause as a citation, or `None` when it has no page (decision 2)."""
    if requirement.page is None:
        return None
    return Citation(
        document_id=requirement.id,
        document_name=requirement.document_name,
        page=requirement.page,
        quote=requirement.source_text[:MAX_QUOTE_CHARS],
    )


def build_tool(context: ToolContext) -> BaseTool:
    """Bind the tool to one company and one bid, or refuse to build it at all.

    The refusals are `tender_rag_search`'s, for the same reason: a matrix read with no bid
    would answer a question about this tender with another tender's rows, and one with no
    connection source could only ever answer "the matrix is empty" — a wrong answer that
    looks exactly like a right one.
    """
    if context.bid_id is None:
        raise RagToolError(
            f"'{MANIFEST.name}' was built with no bid_id. A matrix read without one would "
            "return every bid's rows in the company, so it is refused rather than widened."
        )
    db = require_connection_source(context, tool=MANIFEST.name)
    # Parsed rather than passed through: the read model binds these as text against a
    # `uuid` column, so a malformed scope would fail inside the chat loop instead of at
    # the call that built the tool. The strings are what the statements take.
    company_id = str(scope_uuid(context.company_id, field="company_id", tool=MANIFEST.name))
    bid_id = str(scope_uuid(context.bid_id, field="bid_id", tool=MANIFEST.name))

    async def run(
        status: RowStatus | None = None, limit: int = DEFAULT_ROWS
    ) -> tuple[str, MatrixDigest]:
        """Two scoped reads and a join in memory.

        Two statements rather than a third join written for this tool: both already exist,
        both already carry the tenant predicate in their text (ADR-0011), and a new query
        would be a fourth place that has to remember it. A chat turn makes at most a handful
        of these calls, so the round trip is not the cost worth optimising.
        """
        rows = await fetch_matrix_rows(db, company_id=company_id, bid_id=bid_id)
        requirements = await fetch_requirements(db, company_id=company_id, bid_id=bid_id)
        digest = digest_of(rows, requirements, status=status, limit=limit)
        return digest.render(), digest

    return StructuredTool.from_function(
        coroutine=run,
        name=MANIFEST.name,
        description=MANIFEST.description,
        args_schema=MatrixQueryArgs,
        response_format="content_and_artifact",
    )
