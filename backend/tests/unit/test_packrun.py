"""S7.1 — the pack-run harness: what it reads, what it records, and what it refuses.

Nothing here spends money. `run_pack` is the call that does, and every test below drives it
over its `extract_reqs` seam so that the wiring it owns — the pack read off disk, the usage
sink, the stubs, the interrupt — is proven for free. What the seam hides is one node, and
that node has its own suite.

The last test is the reason this module exists at all. `run_pack` passes its own
`RecordingUsageSink`, and it would be easy to read that as tidiness. It is not: the default
is `DatabaseUsageSink` over the database the harness deliberately does not have, and the
first model response to be captured raises inside `stage` and fails the whole run. That is
what has been true of `test_bid_run_live.py` since S5.2 landed, and it is why the DE cost in
the repository is dated 2026-09-13.
"""

from __future__ import annotations

import shutil
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from crossbid.agent.state import BidState
from crossbid.eval.packrun import (
    ESPD_FILENAME,
    NoDatabase,
    PackRun,
    RecordingProjection,
    RecordingUsageSink,
    TenderPack,
    pack_documents,
    run_pack,
)
from crossbid.models.tender import BidStatus, DocumentKind
from crossbid.models.verdict import Decision
from crossbid.readmodel.documents import DocumentStatus
from crossbid.readmodel.usage import DatabaseUsageSink
from crossbid.settings import Settings
from crossbid.usage import Provider, UsageEvent, UsageNode
from tests.conftest import requirement, verdict

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
DE_DOCUMENTS = FIXTURES / "tenders" / "de" / "documents"
FR_DOCUMENTS = FIXTURES / "tenders" / "fr" / "documents"

PACK = TenderPack(
    fixture_dir="packs/demo",
    notice_number="614251-2026",
    title="a pack under test",
    source_language="de",
    bidder_language="de",
)


def usage_event(cost: str | None) -> UsageEvent:
    return UsageEvent(
        company_id="c",
        bid_id="b",
        node=UsageNode.EXTRACT_REQS,
        provider=Provider.OPENROUTER,
        model="openai/gpt-5.6-terra",
        input_tokens=10,
        output_tokens=2,
        cost_usd=None if cost is None else Decimal(cost),
    )


def build_pack(
    root: Path,
    *,
    pdfs: int = 1,
    espd: bool = False,
    annexes: bool = False,
    notice: bool = False,
) -> Path:
    """A pack directory on disk, built from real fixture files."""
    documents = root / PACK.fixture_dir / "documents"
    documents.mkdir(parents=True)
    if notice:
        shutil.copy(
            sorted(DE_DOCUMENTS.glob("*.pdf"))[-1],
            documents.parent / "614251-2026.notice.de.pdf",
        )
    for index, source in enumerate(sorted(DE_DOCUMENTS.glob("*.pdf"))[:pdfs]):
        shutil.copy(source, documents / f"{index:02d}_{source.name}")
    if espd:
        shutil.copy(FR_DOCUMENTS / ESPD_FILENAME, documents / ESPD_FILENAME)
    if annexes:
        (documents / "Annex_2.docx").write_bytes(b"not a pdf")
        (documents / "Annex_6.xlsx").write_bytes(b"not a pdf either")
    return root


# ------------------------------------------------------------------ what the pack is read as


def test_a_pdf_in_the_documents_folder_becomes_a_tender_document(tmp_path: Path) -> None:
    root = build_pack(tmp_path, pdfs=2)

    rows = pack_documents(root / PACK.fixture_dir, bid_id="b", company_id="c")

    assert [row.kind for row in rows] == [DocumentKind.TENDER_DOCUMENT] * 2
    assert all(row.status is DocumentStatus.READY for row in rows)


def test_a_published_dume_is_the_one_row_the_pdf_parser_never_sees(tmp_path: Path) -> None:
    """The FR pack's wedge. A DUME read as a tender document would reach the PDF parser,
    fail to open, and be reported as unparseable — losing the only criterion ids in the
    whole fixture set (ADR-0022)."""
    root = build_pack(tmp_path, pdfs=1, espd=True)

    rows = pack_documents(root / PACK.fixture_dir, bid_id="b", company_id="c")

    kinds = {row.name: row.kind for row in rows}
    assert kinds[ESPD_FILENAME] is DocumentKind.TENDER_ESPD_REQUEST
    assert set(kinds.values()) == {
        DocumentKind.TENDER_DOCUMENT,
        DocumentKind.TENDER_ESPD_REQUEST,
    }


def test_an_annex_no_parser_reads_is_ignored_rather_than_reported(tmp_path: Path) -> None:
    """The EN pack ships three. Turning each into a problem would put three permanent
    entries in every EN report that no reviewer can act on."""
    root = build_pack(tmp_path, pdfs=1, annexes=True)

    rows = pack_documents(root / PACK.fixture_dir, bid_id="b", company_id="c")

    assert [row.name.endswith(".pdf") for row in rows] == [True]


# -------------------------------------------------------------------------- what a run costs


def test_cost_is_summed_over_the_captured_calls_not_computed() -> None:
    run = PackRun(
        requirements=(),
        problems=(),
        statuses=(),
        usage=(usage_event("0.01"), usage_event("0.005")),
        elapsed_seconds=1.0,
        parked=True,
    )

    assert run.cost_usd == pytest.approx(0.015)
    assert run.calls == 2


def test_a_call_the_provider_priced_at_nothing_counts_as_a_call_and_not_as_cost() -> None:
    run = PackRun(
        requirements=(),
        problems=(),
        statuses=(),
        usage=(usage_event(None),),
        elapsed_seconds=1.0,
        parked=True,
    )

    assert run.cost_usd == 0.0
    assert run.calls == 1


# ------------------------------------------------------------------------ what a run records


async def extraction_of(*rows: Any) -> Any:
    """An `extract_reqs` stand-in returning a fixed set of rows."""

    async def node(state: BidState, config: Any = None) -> Any:
        return {"requirements": list(rows), "extraction_problems": []}

    return node


@pytest.mark.anyio
async def test_a_run_reads_the_pack_off_disk_and_parks_at_the_interrupt(
    tmp_path: Path, offline_settings: Settings
) -> None:
    root = build_pack(tmp_path, pdfs=1)
    row = requirement()

    run = await run_pack(
        offline_settings,
        PACK,
        backend_dir=root,
        extract_reqs=await extraction_of(row),
    )

    assert run.parked, "the graph did not stop at await_review"
    assert run.requirements == (row,)
    assert run.statuses[:2] == (BidStatus.PARSING, BidStatus.EXTRACTING)
    assert run.statuses[-1] is BidStatus.AWAITING_REVIEW
    assert run.elapsed_seconds > 0


@pytest.mark.anyio
async def test_a_pack_with_no_documents_is_refused_before_a_model_is_called(
    tmp_path: Path, offline_settings: Settings
) -> None:
    """A run that cost money and extracted nothing is the failure worth spending a
    conditional on: the message names the fixture, because the cause is almost always a
    pack that was never checked out."""
    (tmp_path / PACK.fixture_dir / "documents").mkdir(parents=True)

    with pytest.raises(ValueError, match="no documents to run"):
        await run_pack(offline_settings, PACK, backend_dir=tmp_path)


# --------------------------------------------------- why the harness brings its own sink


@pytest.mark.anyio
async def test_the_default_usage_sink_cannot_survive_a_run_without_postgres() -> None:
    """The defect this harness exists around, pinned so it cannot be quietly reintroduced.

    `build_graph` defaults `usage` to `DatabaseUsageSink(db)`. Give it a database that
    refuses to connect — which is the only honest kind for a run with no Postgres — and the
    first captured model response raises. `stage` catches it and re-raises as `StageError`,
    so the symptom is a failed *stage*, never a message about cost.

    Revert `run_pack`'s `usage=sink` argument and the live runs fail on their first model
    call, having paid for it.
    """
    sink = DatabaseUsageSink(NoDatabase())  # type: ignore[arg-type]

    with pytest.raises(AssertionError, match="must not touch Postgres"):
        await sink.record(usage_event("0.01"))


@pytest.mark.anyio
async def test_the_recording_sink_keeps_every_event_in_order() -> None:
    sink = RecordingUsageSink()

    await sink.record(usage_event("0.01"))
    await sink.record(usage_event("0.02"))

    assert [event.cost_usd for event in sink.events] == [Decimal("0.01"), Decimal("0.02")]


# ------------------------------------------------------------ what the projection will not do


@pytest.mark.anyio
async def test_matrix_rows_are_counted_and_discarded() -> None:
    """`check_reqs` is stubbed, so the matrix is always empty — but the write still happens
    and still has to answer with a count, because `stage` projects whatever a node returns."""
    projection = RecordingProjection()

    assert await projection.write_matrix_rows(company_id="c", bid_id="b", rows=[]) == 0


@pytest.mark.anyio
async def test_a_review_write_is_refused_because_a_pack_run_never_gets_one() -> None:
    """Reaching either of these means something resumed the graph past the interrupt. The
    rows would be a review nobody submitted, so it fails loudly instead of recording one."""
    projection = RecordingProjection()

    with pytest.raises(AssertionError, match="never reviewed"):
        await projection.record_review(
            company_id="c",
            bid_id="b",
            decision=Decision.GO,
            agent_verdict=None,
            final_verdict=verdict(),
            override_reason=None,
        )
    with pytest.raises(AssertionError, match="never reviewed"):
        await projection.write_reviewed_rows(company_id="c", bid_id="b", rows=[])


@pytest.mark.anyio
async def test_the_notice_pdf_at_the_pack_root_is_part_of_the_run(tmp_path: Path) -> None:
    """Six of the DE key's 177 scored labels cite the notice PDF. Globbing `documents/`
    alone made all six permanent recall misses — 3.4 points of the denominator — and
    nothing in the recall report said the pages had never been read."""
    root = build_pack(tmp_path, pdfs=1, notice=True)

    rows = pack_documents(root / PACK.fixture_dir, bid_id="b", company_id="c")

    kinds = {row.name: row.kind for row in rows}
    assert kinds["614251-2026.notice.de.pdf"] is DocumentKind.TENDER_NOTICE
    assert sum(kind is DocumentKind.TENDER_DOCUMENT for kind in kinds.values()) == 1
