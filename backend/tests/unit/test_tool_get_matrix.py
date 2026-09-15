"""S3.5.1 — `get_matrix`: the matrix as rows a chat answer can cite.

Offline, and in two halves. `digest_of` is a pure function of two projections, so the
counting, the filter, the numbering and the `None` slot for a page-less clause are asserted
directly on it; the built tool is then driven over `conftest`'s recording connection source,
which is what proves the two statements it sends carry the tenant predicate rather than
trusting the fake that stands in for them (ADR-0009).

The assertion that matters most is `test_a_clause_with_no_page_keeps_its_place_in_the_line`.
A requirement read from a published DUME or from TED's structured fields has no page, so it
cannot become a `Citation`; dropping it from the numbering would make the `[n]` the model
reads and the `[n]` the chat graph resolves mean different rows, which is a citation pointing
at the wrong clause — the one failure a citation exists to prevent.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import pytest

from crossbid.guards.wrap import DATA_BLOCK_PREAMBLE
from crossbid.models.matrix import MatrixRow, ReviewerStatus, RowStatus
from crossbid.models.requirement import Checkability, Requirement, RequirementSource
from crossbid.settings import Settings
from crossbid.tools.get_matrix import (
    DEFAULT_ROWS,
    MANIFEST,
    MAX_NOTE_CHARS,
    MAX_ROWS,
    NO_ROWS,
    NOT_CITABLE,
    MatrixDigest,
    MatrixQueryArgs,
    build_tool,
    digest_of,
)
from crossbid.tools.manifest import ToolContext
from crossbid.tools.rag import RagToolError
from tests.conftest import BID_ID, COMPANY_ID, DOCUMENT_NAME, FakeConnectionSource, requirement

pytestmark = pytest.mark.anyio

CLAUSE = "Der Umsatz muss mindestens 3.000.000,00 EUR pro Jahr betragen."
DUME_CLAUSE = "Chiffre d'affaires annuel général"
NOTE = "Der Jahresabschluss weist 7,4 Mio. EUR aus."


DOCUMENT_ID = "d1d1d1d1-1111-4111-8111-111111111111"
DOCUMENTS = {DOCUMENT_NAME: DOCUMENT_ID}
"""The bid's documents by name, which is how a requirement names the file it was quoted
from. A `Requirement` carries no document id -- the column does not exist -- so `digest_of`
has to resolve the name against the bid before a citation can point at anything the
workspace can open. The tool used to put the *requirement's* id there instead."""


def matrix_digest(
    rows: Sequence[MatrixRow],
    requirements: Sequence[Requirement],
    *,
    status: RowStatus | None,
    limit: int,
) -> MatrixDigest:
    """`digest_of` over a bid whose documents are all present, which is the ordinary case.

    The tests that care about a *missing* document call `digest_of` directly with the map
    they mean, so the default here cannot hide the branch it exists to make convenient.
    """
    return digest_of(rows, requirements, status=status, limit=limit, document_ids=DOCUMENTS)


def row(
    requirement_id: str,
    *,
    status: RowStatus = RowStatus.SUPPORTED,
    reviewer_status: ReviewerStatus = ReviewerStatus.PENDING,
    note: str = NOTE,
) -> MatrixRow:
    """One matrix row. `supported` carries an attachment so the model's own invariant holds
    without this file having to invent an `Evidence` it never reads."""
    return MatrixRow(
        id=str(uuid.uuid5(uuid.NAMESPACE_URL, requirement_id)),
        requirement_id=requirement_id,
        status=status,
        attached_doc_ids=("11111111-1111-4111-8111-111111111111",),
        reviewer_status=reviewer_status,
        agent_rationale=note,
    )


def clause(
    text: str = CLAUSE, *, page: int | None = 4, identifier: str = "req-1"
) -> Requirement:
    """One requirement, page-bearing by default and DUME-shaped when `page` is None."""
    if page is None:
        return requirement(
            text,
            page=None,
            identifier=identifier,
            source=RequirementSource.ESPD_REQUEST,
            checkable=Checkability.COMPANY_PROPERTY,
        )
    return requirement(text, page=page, identifier=identifier)


# ------------------------------------------------------------------------- the manifest


def test_the_manifest_matches_the_settings_file(offline_settings: Settings) -> None:
    """The relation `test_tool_manifests.py` asserts over every tool, stated once here too
    because this is the story that adds the name to `enabled_tools`."""
    assert MANIFEST.name in offline_settings.runtime.enabled_tools
    assert MANIFEST.default_enabled is True


def test_reading_the_matrix_is_not_an_external_call() -> None:
    """The flag says "this opens a socket to somebody else"; Postgres is not somebody else,
    and an operator who switched this off would blind the agent to its own answer."""
    assert MANIFEST.external is False


def test_the_model_may_not_widen_the_scope(offline_settings: Settings) -> None:
    """Two arguments and nothing that names a company or a bid: both are closed over."""
    assert set(MatrixQueryArgs.model_fields) == {"status", "limit"}


@pytest.mark.parametrize("limit", [0, MAX_ROWS + 1])
def test_a_limit_outside_the_bounds_is_refused_by_the_schema(limit: int) -> None:
    """The bound is in the tool schema, so the model is refused before a query is built."""
    with pytest.raises(ValueError, match="limit"):
        MatrixQueryArgs(limit=limit)


# ----------------------------------------------------------------------------- the digest


def test_the_counts_describe_the_whole_matrix_and_not_the_page_shown() -> None:
    """A bidder asking "how many still need me?" gets one call, not a paging exercise."""
    # Arrange
    rows = [
        row("req-1", status=RowStatus.SUPPORTED),
        row("req-2", status=RowStatus.PARTIALLY_SUPPORTED),
        row("req-3", status=RowStatus.PARTIALLY_SUPPORTED),
    ]
    requirements = [clause(identifier=f"req-{index}") for index in (1, 2, 3)]

    # Act
    digest = matrix_digest(rows, requirements, status=RowStatus.PARTIALLY_SUPPORTED, limit=1)

    # Assert
    assert digest.total == 3
    assert digest.counts[RowStatus.PARTIALLY_SUPPORTED.value] == 2
    assert len(digest.lines) == 1


def test_a_status_filter_shows_only_that_group() -> None:
    rows = [
        row("req-1", status=RowStatus.SUPPORTED),
        row("req-2", status=RowStatus.UNSUPPORTED),
    ]
    requirements = [clause(identifier="req-1"), clause(identifier="req-2")]

    digest = matrix_digest(rows, requirements, status=RowStatus.UNSUPPORTED, limit=DEFAULT_ROWS)

    assert [line.status for line in digest.lines] == [RowStatus.UNSUPPORTED]


def test_a_clause_with_no_page_keeps_its_place_in_the_line() -> None:
    """The numbering must not shift. A DUME row is shown, counted, and not citable."""
    # Arrange
    rows = [row("req-1"), row("req-2")]
    requirements = [clause(identifier="req-1", page=None), clause(identifier="req-2", page=7)]

    # Act
    digest = matrix_digest(rows, requirements, status=None, limit=DEFAULT_ROWS)

    # Assert -- slot one is the un-citable clause; the citable one is still number two
    assert digest.citations[0] is None
    assert digest.lines[0].citation is None
    assert digest.lines[1].citation == 2
    citation = digest.citations[1]
    assert citation is not None and citation.page == 7


def test_a_row_whose_requirement_is_missing_is_not_described_at_all() -> None:
    """The two projections are written by one graph; a row without its clause is a writer
    bug, and prose about a row nobody can name is worse than a shorter answer."""
    digest = matrix_digest([row("req-1")], [], status=None, limit=DEFAULT_ROWS)

    assert digest.total == 1
    assert digest.lines == ()


def test_the_note_is_bounded_where_it_is_repeated() -> None:
    """A second cap on a second consumer: the column is already capped at 600 when written."""
    digest = matrix_digest(
        [row("req-1", note="x" * 900)], [clause(identifier="req-1")], status=None, limit=1
    )

    assert len(digest.lines[0].note) == MAX_NOTE_CHARS


# --------------------------------------------------------------------------- the rendering


def test_an_empty_matrix_says_so_in_words_the_model_can_repeat() -> None:
    """ "The check has not got there" and "nothing matched" are one honest answer."""
    rendered = matrix_digest([], [], status=None, limit=DEFAULT_ROWS).render()

    assert rendered == NO_ROWS.format(filter="")


def test_an_empty_filtered_matrix_names_the_filter() -> None:
    rendered = matrix_digest([], [], status=RowStatus.UNSUPPORTED, limit=DEFAULT_ROWS).render()

    assert "with status 'unsupported'" in rendered


def test_the_clauses_are_rendered_inside_a_data_block() -> None:
    """Requirement text is a verbatim quote out of a tender PDF: untrusted, so wrapped."""
    digest = matrix_digest([row("req-1")], [clause(identifier="req-1")], status=None, limit=1)

    rendered = digest.render()

    assert DATA_BLOCK_PREAMBLE.split("{nonce}")[0] in rendered
    assert CLAUSE in rendered
    assert "[1] supported" in rendered


def test_a_reviewed_row_says_who_last_touched_it() -> None:
    digest = matrix_digest(
        [row("req-1", reviewer_status=ReviewerStatus.CONFIRMED)],
        [clause(identifier="req-1")],
        status=None,
        limit=1,
    )

    assert "confirmed by the reviewer" in digest.render()


def test_every_status_is_counted_even_at_zero() -> None:
    """ "No unsupported rows" is an answer; a status missing from the list is not."""
    rendered = matrix_digest(
        [row("req-1")], [clause(identifier="req-1")], status=None, limit=1
    ).render()

    for status in RowStatus:
        assert f"0 {status.value}" in rendered or f"1 {status.value}" in rendered


def test_a_matrix_of_only_uncitable_clauses_still_renders_its_rows() -> None:
    """No block, because there is nothing to quote — and still a list of rows and counts."""
    digest = matrix_digest(
        [row("req-1")],
        [clause(DUME_CLAUSE, page=None, identifier="req-1")],
        status=None,
        limit=1,
    )

    rendered = digest.render()

    assert NOT_CITABLE in rendered
    assert DATA_BLOCK_PREAMBLE.split("{nonce}")[0] not in rendered


def test_a_row_with_no_rationale_says_so_rather_than_trailing_off() -> None:
    digest = matrix_digest(
        [row("req-1", note="")], [clause(identifier="req-1")], status=None, limit=1
    )

    assert "none recorded" in digest.render()


# -------------------------------------------------------------------------- the built tool


def test_the_tool_refuses_to_be_built_without_a_bid(offline_settings: Settings) -> None:
    """A matrix read with no bid would answer this tender's question with another's rows."""
    context = ToolContext(
        settings=offline_settings, company_id=COMPANY_ID, db=FakeConnectionSource()
    )

    with pytest.raises(RagToolError, match="no bid_id"):
        build_tool(context)


def test_the_tool_refuses_to_be_built_without_a_database(offline_settings: Settings) -> None:
    """Skipping it would leave a tool that can only ever answer "the matrix is empty"."""
    context = ToolContext(settings=offline_settings, company_id=COMPANY_ID, bid_id=BID_ID)

    with pytest.raises(RagToolError, match="connection source"):
        build_tool(context)


def test_a_scope_that_is_not_a_uuid_fails_at_the_call_that_built_the_tool(
    offline_settings: Settings,
) -> None:
    """psycopg would send a malformed scope as text against a `uuid` column — inside the
    chat loop, rather than at the call that got it wrong."""
    context = ToolContext(
        settings=offline_settings,
        company_id="nope",
        bid_id=BID_ID,
        db=FakeConnectionSource(),
    )

    with pytest.raises(RagToolError, match="not a UUID"):
        build_tool(context)


async def test_both_statements_carry_the_tenant_and_the_bid(offline_settings: Settings) -> None:
    """Application-level isolation (ADR-0009): the predicate is in the SQL, not in the fake."""
    # Arrange
    source = FakeConnectionSource(())
    tool = build_tool(
        ToolContext(settings=offline_settings, company_id=COMPANY_ID, bid_id=BID_ID, db=source)
    )

    # Act
    await tool.ainvoke({"status": None, "limit": 5})

    # Assert -- `matrix_rows`, `requirements` and the bid's documents, every one scoped.
    # The documents read is what makes a citation followable; it must not be the statement
    # that forgets the tenant.
    assert len(source.log) == 3
    for statement in source.log:
        assert "company_id = %(company_id)s" in statement.sql
        assert statement.params["company_id"] == COMPANY_ID
        assert statement.params["bid_id"] == BID_ID


async def test_the_built_tool_puts_the_digest_on_the_artifact(
    offline_settings: Settings,
) -> None:
    """`content_and_artifact`: the model reads the rendering, `chat_graph` reads the object,
    and the citation a bidder is shown comes off the object (S2.4.2's contract)."""
    # Arrange
    source = FakeConnectionSource(())
    tool = build_tool(
        ToolContext(settings=offline_settings, company_id=COMPANY_ID, bid_id=BID_ID, db=source)
    )

    # Act -- invoked as a tool call, which is how `ToolNode` invokes it
    message = await tool.ainvoke(
        {"name": MANIFEST.name, "args": {}, "id": "call-1", "type": "tool_call"}
    )

    # Assert
    assert isinstance(message.artifact, MatrixDigest)
    assert message.artifact.total == 0
    assert message.content == NO_ROWS.format(filter="")


def test_a_citation_names_the_document_the_clause_came_from() -> None:
    """The id has to be the *document's*, because that is what the workspace opens.

    It used to be the requirement's. The browser then invented a document from that id and
    asked `GET /documents/{id}/url` for it, which could only ever 404 — a duplicate tab with
    the right filename and "the document could not be opened" behind it.
    """
    digested = matrix_digest([row("req-1")], [clause(identifier="req-1")], status=None, limit=1)

    [citation] = [item for item in digested.citations if item is not None]
    assert citation.document_id == DOCUMENT_ID
    assert citation.document_name == DOCUMENT_NAME


def test_a_clause_whose_document_the_bid_no_longer_holds_is_not_cited() -> None:
    """A citation the reader cannot follow is worse than none — the rule ADR-0055 already
    settled for chat, applied to the one producer that was not obeying it."""
    digested = digest_of(
        [row("req-1")],
        [clause(identifier="req-1")],
        status=None,
        limit=1,
        document_ids={},
    )

    assert digested.citations == (None,)
    assert digested.lines[0].citation is None
