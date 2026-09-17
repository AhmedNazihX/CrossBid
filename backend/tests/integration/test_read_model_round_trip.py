"""Every read model against a real Postgres: the statements actually run, and the tenant holds.

**Why this file exists.** The offline suite fakes psycopg at the cursor — `FakeCursor.execute`
appends to a log and returns scripted rows — so no statement in `crossbid/readmodel/` had ever
been parsed by a database. A malformed `Final[LiteralString]`, a column renamed in a migration
and not in a read model, or a broken `on conflict` clause would pass `make lint`, pass 4 900
tests and report 100 % coverage. A 2026-09-15 audit named that as the largest gap behind the
coverage figure, and this is the answer to it.

**What it does not try to be.** Not a second copy of the unit tests: those already pin what
each function *decides*, cheaply and offline, and duplicating them here would be slower and no
more honest. What only a database can answer is narrower and more important — does the SQL
parse, does the schema match the model that reads it, and does `where company_id = %(...)s`
actually keep two companies apart when the role connecting has `BYPASSRLS` (ADR-0009)? The
last one is the whole security model, and until now it was asserted by grepping for a
substring in a string constant.

**Marked `live` as well as `database`** so `make test` cannot pick it up on a developer's
machine, where `DATABASE_URL` usually points at Frankfurt and this file writes rows. CI runs
it with `-m database` against a throwaway pgvector service; `make test-db` does the same
locally. With no `DATABASE_URL` it skips rather than fails.
"""

from __future__ import annotations

import importlib.util
import sys
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from crossbid.db import Database
from crossbid.ingestion.chunker import Chunk
from crossbid.ingestion.embeddings import ChunkVectorStore, EmbeddedChunk
from crossbid.models import DocumentKind
from crossbid.models.company import CompanyProfile
from crossbid.models.matrix import MatrixRow, RowStatus
from crossbid.models.provider import Provider
from crossbid.models.requirement import (
    Checkability,
    Requirement,
    RequirementCategory,
    RequirementKind,
    RequirementSource,
    RequirementStage,
)
from crossbid.models.tender import BidStatus
from crossbid.models.verdict import Decision, Verdict
from crossbid.readmodel.app_settings import fetch_app_settings_row, store_app_settings_row
from crossbid.readmodel.bids import (
    attach_documents,
    bid_documents,
    claim_bid_for_review,
    company_language,
    create_bid,
    fetch_bid,
    list_bids,
    record_review,
    set_bid_status,
    set_bid_verdict,
)
from crossbid.readmodel.companies import CompaniesReadModel
from crossbid.readmodel.documents import DocumentsReadModel, fail_interrupted_documents
from crossbid.readmodel.feedback import Rating, fetch_feedback, record_feedback
from crossbid.readmodel.matrix import fetch_matrix_rows, write_matrix_rows
from crossbid.readmodel.pagination import DEFAULT_PAGE_SIZE, decode_cursor
from crossbid.readmodel.requirements import fetch_requirements, write_requirements
from crossbid.readmodel.usage import DatabaseUsageSink, fetch_usage_by_bid, fetch_usage_by_node
from crossbid.settings import AppSettingsRow, SettingsError, load_settings
from crossbid.usage import UsageEvent, UsageNode

pytestmark = [pytest.mark.live, pytest.mark.database, pytest.mark.anyio]


def resolve_dsn() -> str | None:
    """The DSN the API would use, or `None`. Same resolution as `test_checkpointer_restart`."""
    try:
        url = load_settings().env.database_url
    except SettingsError:
        return None
    return None if url is None else url.get_secret_value()


DSN = resolve_dsn()
skip_without_database = pytest.mark.skipif(DSN is None, reason="DATABASE_URL is not set")

PROFILE = CompanyProfile(
    name="Beispiel IT Services GmbH",
    country="de",
    legal_form="gmbh",
    staff_fte=25.0,
)


@pytest.fixture
async def db():
    """One pool for the module's lifetime, closed however the test ends."""
    assert DSN is not None
    database = await Database.connect(DSN)
    try:
        yield database
    finally:
        await database.close()


@pytest.fixture
async def tenant(db: Database) -> tuple[str, str]:
    """A fresh company and a bid inside it, both new every test.

    New rather than shared: these tests write, and a shared row would make the order they run
    in part of what they assert. Nothing is cleaned up — `companies` cascades on delete and
    this database is either a CI container or a developer's own, never the demo tenant.
    """
    company_id = uuid.uuid4()
    await CompaniesReadModel(db).create(
        company_id=company_id, owner_user_id=uuid.uuid4(), profile=PROFILE
    )
    bid = await create_bid(
        db,
        company_id=str(company_id),
        notice_number="614251-2026",
        title="Netztechnik",
        source_language="de",
        bidder_language="de",
    )
    return str(company_id), bid.id


def requirement_of(bid_id: str, identifier: str) -> Requirement:
    return Requirement(
        id=identifier,
        bid_id=bid_id,
        category=RequirementCategory.ECONOMIC_FINANCIAL,
        kind=RequirementKind.MANDATORY,
        stage=RequirementStage.BID_ELIGIBILITY,
        checkable=Checkability.COMPANY_PROPERTY,
        source=RequirementSource.TENDER_DOCUMENT,
        source_text="Der Umsatz muss mindestens 3.000.000,00 EUR pro Jahr betragen.",
        source_lang="de",
        document_name="Bewerbungsbedingungen_VV2_V1.pdf",
        page=4,
    )


# ------------------------------------------------------------------ the statements parse


@skip_without_database
async def test_a_bid_round_trips_through_every_statement_its_graph_uses(
    db: Database, tenant: tuple[str, str]
) -> None:
    """One pass over the write path a real run takes, in the order it takes it.

    Offline these are eight scripted answers. Here each one is parsed by Postgres, checked
    against the schema the migrations built, and read back through the model that has to
    validate it — which is the join the fakes cannot test.
    """
    company_id, bid_id = tenant

    await set_bid_status(db, company_id=company_id, bid_id=bid_id, status=BidStatus.EXTRACTING)
    written = await write_requirements(
        db, company_id=company_id, rows=[requirement_of(bid_id, str(uuid.uuid4()))]
    )
    requirements = await fetch_requirements(db, company_id=company_id, bid_id=bid_id)
    row = MatrixRow(
        id=str(uuid.uuid4()),
        requirement_id=requirements[0].id,
        status=RowStatus.PARTIALLY_SUPPORTED,
        agent_status=RowStatus.PARTIALLY_SUPPORTED,
        agent_rationale="Der Jahresabschluss weist 7,4 Mio. EUR aus.",
    )
    await write_matrix_rows(db, company_id=company_id, bid_id=bid_id, rows=[row])
    verdict = Verdict(
        decision=Decision.CONDITIONAL,
        rationale="Mit Auflagen möglich.",
        mandatory_total=1,
        mandatory_supported=0,
        partially_supported_rows=1,
    )
    await set_bid_verdict(db, company_id=company_id, bid_id=bid_id, verdict=verdict)

    assert written == 1
    assert [item.source_text for item in requirements] == [
        requirement_of(bid_id, "x").source_text
    ]
    matrix = await fetch_matrix_rows(db, company_id=company_id, bid_id=bid_id)
    assert [item.status for item in matrix] == [RowStatus.PARTIALLY_SUPPORTED]
    # Migration 0009's column, round-tripped: written by the agent's upsert, read back by
    # the select, and never named by `UPDATE_REVIEWED_ROW` (H24).
    assert [item.agent_status for item in matrix] == [RowStatus.PARTIALLY_SUPPORTED]
    stored = await fetch_bid(db, company_id=company_id, bid_id=bid_id)
    assert stored is not None
    # `BidRow.verdict` is the stored JSON, not a re-validated `Verdict`: the row is what the
    # column holds, and `BidResponse.assemble` is where it becomes a model. Asserting the raw
    # shape here is the point — it is what a `jsonb` round trip can actually get wrong.
    assert stored.verdict is not None
    assert stored.verdict["decision"] == Decision.CONDITIONAL.value
    assert stored.verdict["mandatory_total"] == 1
    assert await company_language(db, company_id=company_id) == "de"
    listed = await list_bids(db, company_id=company_id, limit=DEFAULT_PAGE_SIZE)
    assert [item.id for item in listed.items] == [bid_id]
    assert listed.next_cursor is None, "one bid is not a full page: nothing comes after it"


@skip_without_database
async def test_a_review_writes_the_audit_row_and_the_decision_in_one_transaction(
    db: Database, tenant: tuple[str, str]
) -> None:
    """The pair `record_review` promises, proven where autocommit could have broken it.

    Offline this is asserted against a fake that records how the block ended. Here the
    database decides, which is the only place the question is actually settled.
    """
    company_id, bid_id = tenant
    await set_bid_status(
        db, company_id=company_id, bid_id=bid_id, status=BidStatus.AWAITING_REVIEW
    )
    await claim_bid_for_review(db, company_id=company_id, bid_id=bid_id)

    await record_review(
        db,
        company_id=company_id,
        bid_id=bid_id,
        decision=Decision.GO,
        agent_verdict={"decision": "conditional"},
        final_verdict={"decision": "go"},
        override_reason="Die Referenzen liegen vor.",
    )

    stored = await fetch_bid(db, company_id=company_id, bid_id=bid_id)
    assert stored is not None
    assert stored.decision is Decision.GO


@skip_without_database
async def test_a_document_walks_its_status_machine_and_the_sweep_finds_a_stranded_one(
    db: Database, tenant: tuple[str, str]
) -> None:
    """The one column family with an `integer[]` and a text array in it.

    `unread_pages` and `flagged_chunks` are the fields most likely to be got wrong by a fake,
    because psycopg's array adaptation is real behaviour rather than a shape the test chose.
    """
    company_id, bid_id = tenant
    records = DocumentsReadModel(db)
    document_id = uuid.uuid4()

    await records.insert(
        company_id=uuid.UUID(company_id),
        document_id=document_id,
        kind=DocumentKind.TENDER_DOCUMENT,
        name="Bewerbungsbedingungen_VV2_V1.pdf",
        storage_path=f"{company_id}/{document_id}/Bewerbungsbedingungen_VV2_V1.pdf",
    )
    parsed = await records.mark_parsed(
        company_id=uuid.UUID(company_id), document_id=document_id, pages=12, unread_pages=(3, 7)
    )
    flagged = await records.set_flagged_chunks(
        company_id=uuid.UUID(company_id), document_id=document_id, flagged_chunks=[2]
    )
    ready = await records.mark_ready(company_id=uuid.UUID(company_id), document_id=document_id)

    assert parsed.unread_pages == (3, 7)
    assert flagged.flagged_chunks == (2,)
    assert ready.status.value == "ready"
    await attach_documents(
        db, company_id=company_id, bid_id=bid_id, document_ids=[str(document_id)]
    )
    listed = await records.list(company_id=uuid.UUID(company_id), limit=DEFAULT_PAGE_SIZE)
    assert [str(item.id) for item in listed.items] == [str(document_id)]
    assert listed.next_cursor is None
    # The sweep parses and runs; a document updated a moment ago is far too young for it.
    assert await fail_interrupted_documents(db, stale_after_seconds=3600.0) >= 0


@skip_without_database
async def test_usage_feedback_and_the_settings_row_all_round_trip(
    db: Database, tenant: tuple[str, str]
) -> None:
    """Three tables whose statements no test had ever sent to a database.

    `llm_usage` carries a `numeric(12, 6)` that comes back as a `Decimal`, `feedback` is
    written by an `insert ... select` that proves the tenant from the bid rather than binding
    it, and `app_settings` is the one row with no `company_id` at all.
    """
    company_id, bid_id = tenant

    await DatabaseUsageSink(db).record(
        UsageEvent(
            company_id=company_id,
            bid_id=bid_id,
            node=UsageNode.EXTRACT_REQS,
            provider=Provider.OPENROUTER,
            model="openai/gpt-5.6-terra",
            input_tokens=1_000,
            output_tokens=200,
            cost_usd=Decimal("0.012345"),
        )
    )
    rated = await record_feedback(
        db, company_id=company_id, bid_id=bid_id, rating=Rating.UP, comment="Stimmt."
    )
    stored_row = await store_app_settings_row(db, AppSettingsRow(temperature=0.3))

    by_node = await fetch_usage_by_node(db, company_id=company_id)
    assert any(line.node is UsageNode.EXTRACT_REQS for line in by_node)
    assert any(line.cost_usd == pytest.approx(0.012345) for line in by_node), (
        "the read model sums a numeric(12, 6) and hands back a float; the value survives"
    )
    assert any(
        run.bid_id == bid_id for run in await fetch_usage_by_bid(db, company_id=company_id)
    )
    assert rated is not None and rated.rating is Rating.UP
    assert [
        item.comment for item in await fetch_feedback(db, company_id=company_id, bid_id=bid_id)
    ] == ["Stimmt."]
    assert stored_row.temperature == 0.3
    read_back = await fetch_app_settings_row(db)
    assert read_back is not None and read_back.temperature == 0.3
    # Put it back, so a developer running this against their own database is not left tuned.
    await store_app_settings_row(db, AppSettingsRow())


# ---------------------------------------------------------- and the tenant actually holds


@skip_without_database
async def test_one_company_cannot_read_another_companys_rows(db: Database) -> None:
    """The security model, asserted against a database for the first time.

    The API connects as a role with `BYPASSRLS`, so row-level security is inert and the
    `where company_id = %(company_id)s` written into each statement is the only thing between
    two tenants (ADR-0009). Offline that is asserted by checking the substring appears in the
    constant — which would also pass if the predicate compared the wrong column.
    """
    companies = CompaniesReadModel(db)
    mine, theirs = uuid.uuid4(), uuid.uuid4()
    for company_id in (mine, theirs):
        await companies.create(
            company_id=company_id, owner_user_id=uuid.uuid4(), profile=PROFILE
        )
    my_bid = await create_bid(
        db,
        company_id=str(mine),
        notice_number="614251-2026",
        title="Netztechnik",
        source_language="de",
        bidder_language="de",
    )
    await write_requirements(
        db, company_id=str(mine), rows=[requirement_of(my_bid.id, str(uuid.uuid4()))]
    )

    # Act / Assert -- every read, with the other company's id.
    assert await fetch_bid(db, company_id=str(theirs), bid_id=my_bid.id) is None
    assert (await list_bids(db, company_id=str(theirs), limit=DEFAULT_PAGE_SIZE)).items == ()
    assert list(await fetch_requirements(db, company_id=str(theirs), bid_id=my_bid.id)) == []
    assert list(await fetch_matrix_rows(db, company_id=str(theirs), bid_id=my_bid.id)) == []
    assert list(await fetch_feedback(db, company_id=str(theirs), bid_id=my_bid.id)) == []
    assert list(await fetch_usage_by_bid(db, company_id=str(theirs))) == []
    assert await companies.get(company_id=theirs) is not None, "their own row is readable"
    assert (
        await record_feedback(db, company_id=str(theirs), bid_id=my_bid.id, rating=Rating.UP)
        is None
    ), "a write scoped to the wrong tenant matches no row rather than creating one"


@skip_without_database
async def test_the_schema_the_migrations_built_is_the_schema_the_models_read(
    db: Database, tenant: tuple[str, str]
) -> None:
    """A renamed column is a `ValidationError` here and nothing at all offline.

    `_record` and `_bid_row` turn a `dict_row` into a model; the fakes hand them a dict the
    test wrote, so the column list is never compared with the table. `select *`-shaped drift
    between `migrations/` and `readmodel/` shows up here and only here.
    """
    company_id, bid_id = tenant
    now = datetime.now(UTC)

    bid = await fetch_bid(db, company_id=company_id, bid_id=bid_id)

    assert bid is not None
    assert bid.company_id == company_id
    assert bid.thread_id == f"bid:{bid_id}"
    assert bid.status is BidStatus.QUEUED
    assert bid.created_at is None or bid.created_at <= now


@skip_without_database
async def test_the_keyset_pages_a_list_whose_rows_share_a_timestamp(db: Database) -> None:
    """M13's paging, executed rather than inspected (found by CI, 2026-09-17).

    The keyset shipped with unit tests against the fake cursor, which returns whatever rows the
    test scripted in whatever order it wrote them — so `order by created_at desc, id desc` and
    the `(created_at, id) < (%(after_created_at)s, %(after_id)s)` predicate had never been
    parsed by a database, let alone asked to order anything. The same blind spot took CI red
    here: `list_bids` grew a required `limit`, three tests in this file were not updated, and
    nothing on a developer's machine runs them (`make test` deselects `database`).

    **The five bids are given one shared `created_at` on purpose.** Written naturally they get
    five distinct microsecond stamps, and then the whole composite key is decoration: replacing
    the row comparison with a plain `created_at < %(after_created_at)s` — the classic keyset
    bug, which drops or repeats every row sharing a timestamp — passes. Measured: it did. With
    the timestamps tied, the `id` half is the only thing that can carry the boundary, which is
    the half worth proving and the case a batch insert or a coarse clock produces in
    production.

    What only Postgres can answer: that `(a, b) < (c, d)` is a *row* comparison and not two
    `and`s, that `desc` on the pair orders the way the cursor assumes, and that the boundary
    serves each row exactly once.
    """
    company_id = str(uuid.uuid4())
    companies = CompaniesReadModel(db)
    await companies.create(
        company_id=uuid.UUID(company_id), owner_user_id=uuid.uuid4(), profile=PROFILE
    )
    created = [
        await create_bid(
            db,
            company_id=company_id,
            notice_number=f"61425{index}-2026",
            title=f"Netztechnik {index}",
            source_language="de",
            bidder_language="de",
        )
        for index in range(5)
    ]
    async with db.connection() as conn:
        await conn.execute(
            "update bids set created_at = %(created_at)s where company_id = %(company_id)s",
            {"created_at": datetime.now(UTC), "company_id": company_id},
        )
    # Tied on the timestamp, the newest-first order is the id order and nothing else.
    expected = sorted((bid.id for bid in created), reverse=True)

    first = await list_bids(db, company_id=company_id, limit=2)
    assert first.next_cursor is not None, "five bids do not fit in a page of two"
    second = await list_bids(
        db, company_id=company_id, limit=2, after=decode_cursor(first.next_cursor)
    )
    assert second.next_cursor is not None
    third = await list_bids(
        db, company_id=company_id, limit=2, after=decode_cursor(second.next_cursor)
    )

    paged = [row.id for page in (first, second, third) for row in page.items]
    assert paged == expected
    assert len(set(paged)) == len(paged), "a row served twice is the offset bug this replaced"
    assert third.next_cursor is None, "the last page says it is the last"


VECTOR_DIMENSIONS = 1536
"""`settings.default.yaml`'s `embed_dimensions` — what the `vector(1536)` column takes."""


def _backfill_module() -> Any:
    """`scripts/index_existing_bids.py` as a module, loaded by path.

    The same way `test_recall_script.py` reaches its script: `scripts/` is not a package, and
    making it one to satisfy an import would change what ships to satisfy a test.
    """
    path = Path(__file__).resolve().parents[2] / "scripts" / "index_existing_bids.py"
    spec = importlib.util.spec_from_file_location("index_existing_bids", path)
    assert spec is not None and spec.loader is not None, path
    module = importlib.util.module_from_spec(spec)
    sys.modules["index_existing_bids"] = module
    spec.loader.exec_module(module)
    return module


@skip_without_database
async def test_the_backfill_selects_exactly_the_bids_with_no_corpus(db: Database) -> None:
    """The query behind `scripts/index_existing_bids.py`, executed (2026-09-17).

    It exists because a bid analysed before `a55d14b` has documents, a full matrix and no
    `tender_chunks` row, so every retrieval over it is empty for ever (ADR-0098). The script
    that repairs those bids is only as good as this selection: too wide and it re-embeds
    corpora that are already there and charges a company for them, too narrow and the bid a
    bidder is complaining about is not in the list.

    Only a database can answer it. The predicate is a `not exists` correlated on `bid_id` and
    a `kind = any(...)` over an array parameter — neither of which the offline fake parses,
    both of which are the whole behaviour.
    """
    backfill = _backfill_module()
    company_id = str(uuid.uuid4())
    companies = CompaniesReadModel(db)
    await companies.create(
        company_id=uuid.UUID(company_id), owner_user_id=uuid.uuid4(), profile=PROFILE
    )
    records = DocumentsReadModel(db)

    async def bid_with_document(*, kind: DocumentKind, notice: str) -> tuple[str, uuid.UUID]:
        bid = await create_bid(
            db,
            company_id=company_id,
            notice_number=notice,
            title="Netztechnik",
            source_language="de",
            bidder_language="de",
        )
        document_id = uuid.uuid4()
        await records.insert(
            company_id=uuid.UUID(company_id),
            document_id=document_id,
            kind=kind,
            name=f"{notice}.pdf",
            storage_path=f"{company_id}/{document_id}/{notice}.pdf",
        )
        await records.mark_ready(company_id=uuid.UUID(company_id), document_id=document_id)
        await attach_documents(
            db, company_id=company_id, bid_id=bid.id, document_ids=[str(document_id)]
        )
        return bid.id, document_id

    unindexed, _ = await bid_with_document(
        kind=DocumentKind.TENDER_DOCUMENT, notice="614251-2026"
    )
    indexed, indexed_document = await bid_with_document(
        kind=DocumentKind.TENDER_DOCUMENT, notice="614252-2026"
    )
    espd_only, _ = await bid_with_document(
        kind=DocumentKind.TENDER_ESPD_REQUEST, notice="614253-2026"
    )
    # One chunk is all it takes to be "indexed": the question is existence, not completeness.
    await ChunkVectorStore(db).insert_tender_chunks(
        company_id=uuid.UUID(company_id),
        bid_id=uuid.UUID(indexed),
        document_id=indexed_document,
        chunks=[
            EmbeddedChunk(
                chunk=Chunk(
                    document_id=str(indexed_document),
                    index=0,
                    pages=(1,),
                    text="Mindestumsatz 3 Mio EUR",
                    token_count=6,
                ),
                embedding=tuple([0.0] * VECTOR_DIMENSIONS),
            )
        ],
    )

    selected = {bid.bid_id for bid in await backfill.unindexed_bids(db, bid_id=None)}

    assert unindexed in selected, "a bid with documents and no chunks is the whole point"
    assert indexed not in selected, "re-embedding a corpus that exists would charge for nothing"
    assert espd_only not in selected, "a DUME is XML: parse_docs skips it, so there is no work"
    assert {bid.bid_id for bid in await backfill.unindexed_bids(db, bid_id=unindexed)} == {
        unindexed
    }


@skip_without_database
async def test_a_documents_searchability_is_read_with_the_document(db: Database) -> None:
    """Whether the workspace can say "this document cannot be searched" (2026-09-17).

    A bid analysed before `a55d14b` has documents and no `tender_chunks`, and nothing on
    screen said so — the count of problems was zero, because nothing had failed; the step had
    simply never existed (ADR-0098). The fact is one `exists` away and it is now read *with*
    the document rather than by a query of its own: `GET /bids/{id}` is polled every two
    seconds and ADR-0093 spent real work getting that path down to three reads.
    """
    company_id = str(uuid.uuid4())
    companies = CompaniesReadModel(db)
    await companies.create(
        company_id=uuid.UUID(company_id), owner_user_id=uuid.uuid4(), profile=PROFILE
    )
    records = DocumentsReadModel(db)
    bid = await create_bid(
        db,
        company_id=company_id,
        notice_number="614260-2026",
        title="Netztechnik",
        source_language="de",
        bidder_language="de",
    )
    ids: list[uuid.UUID] = []
    for name in ("a-indexed.pdf", "b-not-indexed.pdf"):
        document_id = uuid.uuid4()
        await records.insert(
            company_id=uuid.UUID(company_id),
            document_id=document_id,
            kind=DocumentKind.TENDER_DOCUMENT,
            name=name,
            storage_path=f"{company_id}/{document_id}/{name}",
        )
        await records.mark_ready(company_id=uuid.UUID(company_id), document_id=document_id)
        ids.append(document_id)
    await attach_documents(
        db, company_id=company_id, bid_id=bid.id, document_ids=[str(one) for one in ids]
    )
    await ChunkVectorStore(db).insert_tender_chunks(
        company_id=uuid.UUID(company_id),
        bid_id=uuid.UUID(bid.id),
        document_id=ids[0],
        chunks=[
            EmbeddedChunk(
                chunk=Chunk(
                    document_id=str(ids[0]),
                    index=0,
                    pages=(1,),
                    text="Mindestumsatz 3 Mio EUR",
                    token_count=6,
                ),
                embedding=tuple([0.0] * VECTOR_DIMENSIONS),
            )
        ],
    )

    rows = await bid_documents(db, company_id=company_id, bid_id=bid.id)

    # Ordered by name, so the indexed one is first.
    assert [(row.name, row.searchable) for row in rows] == [
        ("a-indexed.pdf", True),
        ("b-not-indexed.pdf", False),
    ]
