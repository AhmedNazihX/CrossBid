"""S7.1 — the committed graph over a fixture pack, run so its rows can be scored offline.

Extraction costs money, so nothing scores a tender by extracting it again. A run happens
once, its rows are written to `tests/fixtures/extractions/<name>.json`, and every recall,
faithfulness and translation figure afterwards is read from that file for free. This module
is the run half; `crossbid.eval.extraction` is the file it writes.

**Why it exists at all, rather than living in the live test.** `tests/integration/
test_bid_run_live.py` has run the DE pack since S3.1.1 and its figure — $1.74, 243 s — is
the one the report quotes. S7.1 needs the same run over FR and EN, and over a second model,
which is three more callers of machinery that existed once as test-local helpers. Copying it
would have produced two definitions of "a run against a fixture pack", and the number each
produced would have stopped being comparable the first time one of them was edited. So the
machinery moved here and the live test calls it, exactly as `eval/matching.py` imports
`extract_reqs._comparable` rather than restating what a comparable quote is.

**What is real in a pack run and what is not.** Real: the committed graph, the parser, the
extraction node, the model calls, the interrupt, and — since S5.2 — the usage capture that
attributes every call to a node. Not real: Storage, Postgres, and checking. The pack is read
off disk through `parse_docs`'s fetcher seam, `plan_checks` and `check_reqs` are stubbed
because they would read the companies table and open a database the harness deliberately
does not have, and the checkpointer is a `MemorySaver`. That is the same shape the DE figure
was always measured in, which is what keeps a re-record comparable with it.

**Two things a pack run does not pay for, stated because the report quotes its cost.**
`parse_docs` embeds every tender document into `tender_chunks` when it is given a
`TenderIndexer` (ADR-0057); it is given none here, because the writer needs Postgres. On the
DE pack that is roughly 150 000 tokens of `text-embedding-3-small`, about **$0.004** — real,
but four thousandths of a dollar against a $1.74 run. And `check_reqs` is stubbed, so the
figure is the cost of reaching `awaiting_review` with the matrix unchecked, which is what
the 2026-09-11 and 2026-09-13 figures were too.

**The usage sink is the cost, not a callback.** ADR-0056 put cost where it cannot be
forgotten: every model response is captured by `stage`'s `UsageRecorder` and handed to a
`UsageSink`. The live test used to sum a callback's view of `token_usage.cost` instead, and
that callback saw only chat completions. Summing the sink measures what `/dev/costs` shows a
bidder, through the production path, and it is the reason `RecordingUsageSink` below exists
rather than a second cost recorder: **a run whose sink recorded nothing fails rather than
reporting $0.00.**
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import Any, Final

from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from crossbid.agent.graph import (
    AWAIT_REVIEW,
    BidNode,
    ReadModelProjection,
    RunProjection,
    build_graph,
    initial_state,
)
from crossbid.agent.nodes.parse_docs import DocumentParser
from crossbid.agent.nodes.score_verdict import VerdictScorer
from crossbid.agent.state import ExtractionProblem
from crossbid.db import Database
from crossbid.models.company import CompanyProfile
from crossbid.models.matrix import MatrixRow
from crossbid.models.requirement import Requirement
from crossbid.models.tender import BidStatus, DocumentKind
from crossbid.models.verdict import Decision, Verdict
from crossbid.readmodel.bids import BidDocumentRow, BidRow, thread_id_of
from crossbid.readmodel.documents import DocumentStatus
from crossbid.settings import Settings, bid_run_config
from crossbid.usage import UsageEvent

ESPD_FILENAME: Final = "DUME_acheteur.xml"
"""The one file in a pack that is not a PDF and is not read by the PDF parser.

Only the FR fixture has one. It is what makes that pack the only one whose run lights the
cross-border wedge: a published DUME states eCertis criterion ids as canonical UUIDs, so
`check_reqs` can look up national evidence for them without a model inferring anything
(ADR-0007, ADR-0022). A DE run carries zero criterion ids and is correct to.
"""

DOCUMENTS_DIRNAME: Final = "documents"
"""The procurement documents, *not* the notice PDF one level above them. The two globs give
different counts on the same pack — 191 pages against 202 for DE — and CLAUDE.md records the
confusion. The pack directory's own name is never the thing globbed."""


@dataclass(frozen=True)
class TenderPack:
    """Which fixture pack to run, and the bid facts a run needs to exist.

    `fixture_dir` is repo-relative from `backend/`, the same convention `GoldenMeta` and
    `ExtractionMeta` use, so a run, its answer key and its result file are all named by one
    string and cannot be paired up wrongly.
    """

    fixture_dir: str
    notice_number: str
    title: str
    source_language: str
    bidder_language: str

    @property
    def name(self) -> str:
        """`de`, `fr`, `en` — the last segment, and what the result file is called."""
        return PurePosixPath(self.fixture_dir).name

    def directory(self, backend_dir: Path) -> Path:
        return backend_dir / self.fixture_dir


@dataclass(frozen=True)
class PackRun:
    """What one run produced, and what it cost to produce it."""

    requirements: tuple[Requirement, ...]
    problems: tuple[ExtractionProblem, ...]
    statuses: tuple[BidStatus, ...]
    usage: tuple[UsageEvent, ...]
    elapsed_seconds: float
    parked: bool
    """Whether the graph stopped at `await_review`. False means it never reached the
    interrupt, which makes the rows a partial result rather than a run."""
    matrix_rows: tuple[MatrixRow, ...] = ()
    verdicts: tuple[Verdict, ...] = ()
    """What checking and scoring produced. Both empty on a run with no database: checking is
    stubbed there, and a verdict scored over an empty matrix says nothing about the bidder."""

    @property
    def cost_usd(self) -> float:
        """What the provider reported, summed over every captured call.

        Summed as `Decimal` and converted once at the end: the per-call figures are fractions
        of a cent and float addition over 49 of them drifts in the digit the report prints.
        """
        return float(sum((event.cost_usd or Decimal(0) for event in self.usage), Decimal(0)))

    @property
    def calls(self) -> int:
        return len(self.usage)


# ------------------------------------------------------------- the three absent collaborators


class RecordingProjection:
    """The read model, replaced by a list — and optionally *also* the read model.

    A pack run with no Postgres has nowhere to write, and the rows it is worth paying for are
    the requirements: they reach this object by the same call the real projection would have
    written them with, so a run that extracted nothing produces an empty list rather than
    looking like a success.

    **`delegate` is what makes a paid run visible in the app.** Given one, every write is
    recorded *and* passed on, so the bid a run produced can be opened in the browser instead
    of existing only as a number in a terminal. That is the difference between a screenshot of
    the product and a screenshot of a fixture, and it costs nothing extra: the run has already
    been paid for.
    """

    def __init__(self, delegate: RunProjection | None = None) -> None:
        self._delegate = delegate
        self.statuses: list[BidStatus] = []
        self.problems: list[ExtractionProblem] = []
        self.rows: list[Requirement] = []
        self.verdicts: list[Verdict] = []
        self.matrix_rows: list[MatrixRow] = []

    async def set_status(self, *, company_id: str, bid_id: str, status: BidStatus) -> None:
        self.statuses.append(status)
        if self._delegate is not None:
            await self._delegate.set_status(company_id=company_id, bid_id=bid_id, status=status)

    async def set_problems(
        self, *, company_id: str, bid_id: str, problems: Sequence[ExtractionProblem]
    ) -> None:
        self.problems = list(problems)
        if self._delegate is not None:
            await self._delegate.set_problems(
                company_id=company_id, bid_id=bid_id, problems=problems
            )

    async def write_requirements(self, *, company_id: str, rows: Sequence[Requirement]) -> int:
        self.rows.extend(rows)
        if self._delegate is not None:
            await self._delegate.write_requirements(company_id=company_id, rows=rows)
        return len(rows)

    async def write_matrix_rows(
        self, *, company_id: str, bid_id: str, rows: Sequence[MatrixRow]
    ) -> int:
        self.matrix_rows = list(rows)
        if self._delegate is not None:
            await self._delegate.write_matrix_rows(
                company_id=company_id, bid_id=bid_id, rows=rows
            )
        return len(rows)

    async def set_verdict(self, *, company_id: str, bid_id: str, verdict: Verdict) -> None:
        """The advisory verdict, written by `score_verdict` *before* the interrupt.

        Recorded rather than refused: a pack run does reach this, because scoring is the
        last node before `await_review`. It is the agent's advisory verdict over an empty
        matrix — `check_reqs` is stubbed — so the harness keeps it for completeness and
        nothing scores it.
        """
        self.verdicts.append(verdict)
        if self._delegate is not None:
            await self._delegate.set_verdict(
                company_id=company_id, bid_id=bid_id, verdict=verdict
            )

    # The two writes below belong to review, which a pack run never reaches: the graph stops
    # at `await_review` and nothing resumes it. They are implemented because `RunProjection`
    # is one protocol and a partial implementation is not one -- and implemented as
    # failures, so that a later change quietly running a pack past the interrupt is a named
    # error rather than a silently discarded review.

    async def record_review(
        self,
        *,
        company_id: str,
        bid_id: str,
        decision: Decision,
        agent_verdict: Verdict | None,
        final_verdict: Verdict,
        override_reason: str | None,
    ) -> None:
        raise AssertionError("a pack run stops at the interrupt and is never reviewed")

    async def write_reviewed_rows(
        self, *, company_id: str, bid_id: str, rows: Sequence[MatrixRow]
    ) -> int:
        raise AssertionError("a pack run stops at the interrupt and is never reviewed")


class RecordingUsageSink:
    """`usage.UsageSink` over a list, which is what makes the run's cost a measurement.

    Without this the graph builds a `DatabaseUsageSink` over the database below, and the
    first model response to be captured raises inside `stage` and fails the run. That is not
    hypothetical: it is why the DE figure in the repository predates S5.2 — the live test
    passed a database that refuses to connect and nothing had re-run it since cost capture
    landed.
    """

    def __init__(self) -> None:
        self.events: list[UsageEvent] = []

    async def record(self, event: UsageEvent) -> None:
        self.events.append(event)


class NoDatabase:
    """Stands in for `Database`, and refuses rather than pretends.

    Every collaborator that would have used it is passed explicitly, so a call to
    `connection()` means the wiring changed and a pack run has silently started depending on
    Postgres. Raising here turns that into a failed run with a name on it instead of a
    connection attempt from a script that has no DSN.
    """

    checkpointer = MemorySaver()
    store = InMemoryStore()
    """The agent's long-term memory, in process. `build_apply_review` is the one node a pack
    run does not inject — it parks at the interrupt and never reaches it — so this is a store
    that gets *constructed* and never read. It is in memory rather than absent for the same
    reason `checkpointer` is: refusing here would fail a run over a node it never runs."""

    def connection(self) -> Any:
        raise AssertionError(
            "a pack run must not touch Postgres — a collaborator is missing from run_pack"
        )


# ------------------------------------------------------------------------------ the pack


def pack_documents(
    pack_dir: Path, *, bid_id: str, company_id: str
) -> tuple[BidDocumentRow, ...]:
    """The rows `parse_docs` would have loaded, built from what is on disk.

    Three kinds, and the pack's own layout says which is which. A PDF in `documents/` is a
    `TENDER_DOCUMENT`; a `DUME_acheteur.xml` beside them is a `TENDER_ESPD_REQUEST`, the one
    kind `parse_docs` routes to `ingestion/espd.py` instead of the PDF parser; and a PDF at
    the pack root is the `TENDER_NOTICE`.

    **The notice is included, and until S7.1 it was not.** `test_bid_run_live.py` globbed
    `documents/*.pdf` alone, so the DE run read 28 files and 191 pages — while the DE answer
    key labels **six scored requirements on the notice PDF**, which no run could ever reach.
    Those six were permanent recall misses worth 3.4 points of a 177-label denominator, and
    nothing in the output said so. A bidder uploads the notice (it is the first field of the
    start form, and `DocumentKind.TENDER_NOTICE` exists for it), the key labels it, so the
    run reads it. This is why a figure recorded here is not comparable with the 2026-09-13
    one; the report says so rather than printing them side by side.

    Anything else in the directory is ignored on purpose and not reported: the EN pack ships
    `.docx` and `.xlsx` annexes that no parser in this build reads, the golden key says so in
    writing, and a pack run inventing a problem for each of them would put three permanent
    entries in every EN report that no reviewer can act on.
    """
    return tuple(
        BidDocumentRow(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, path.name)),
            name=path.name,
            storage_path=f"{company_id}/{path.stem}/{path.name}",
            kind=_kind_of(path, pack_dir=pack_dir),
            status=DocumentStatus.READY,
            bid_id=bid_id,
            pages=0,
        )
        for path in pack_paths(pack_dir)
    )


def pack_paths(pack_dir: Path) -> tuple[Path, ...]:
    """Every file of the pack a run reads, notice first, in a fixed order.

    One list, because `pack_documents` names the rows and `_fixture_parser` has to hand back
    the bytes for those same names. Two globs would be two answers to "what is in this pack",
    and the one that went stale would fail as a `FileNotFoundError` inside `parse_docs` —
    which is what adding the notice did on its first run, before this existed.
    """
    documents_dir = pack_dir / DOCUMENTS_DIRNAME
    paths = [*sorted(pack_dir.glob("*.pdf")), *sorted(documents_dir.glob("*.pdf"))]
    espd = documents_dir / ESPD_FILENAME
    if espd.exists():
        paths.append(espd)
    return tuple(paths)


def _kind_of(path: Path, *, pack_dir: Path) -> DocumentKind:
    """Which of the three tender kinds a file in a pack is.

    `parse_docs` routes only `TENDER_ESPD_REQUEST` away from the PDF parser, so the notice
    is parsed exactly like a procurement document and the kind is a label rather than a
    behaviour here. It is still set correctly, because it is what a bidder chose in the
    upload form and the report describes a run a bidder could have made.
    """
    if path.name == ESPD_FILENAME:
        return DocumentKind.TENDER_ESPD_REQUEST
    at_root = path.parent == pack_dir
    return DocumentKind.TENDER_NOTICE if at_root else DocumentKind.TENDER_DOCUMENT


def _fixture_parser(pack_dir: Path, rows: Sequence[BidDocumentRow]) -> DocumentParser:
    """`parse_docs` with its two seams pointed at the fixture directory.

    No `index` is passed, so nothing is embedded — see the module docstring on what that
    leaves out of the cost.
    """
    by_name = {path.name: path for path in pack_paths(pack_dir)}

    async def load(company_id: str, bid_id: str) -> Sequence[BidDocumentRow]:
        return rows

    async def fetch(company_id: str, document: BidDocumentRow) -> bytes:
        return by_name[document.name].read_bytes()

    return DocumentParser(load_documents=load, fetch=fetch)


class NoCompanyProfile:
    """`score_verdict`'s company lookup, answering what a bid with no seeded profile gets.

    The scorer is *not* stubbed — the real rules run over the real matrix — because a run
    that skipped scoring would not reach `await_review`, and reaching the interrupt is the
    thing `parked` reports. Only the profile read is replaced, and it is replaced with the
    same answer `VerdictScorer._profile` produces for a company that has none: `None`, which
    the verdict renders as "no recorded figures".

    It is replaced rather than left alone because `CompaniesReadModel.get` goes to Postgres
    unconditionally, and `_profile` catches only `CompanyReadModelError` and `ValueError` —
    a database that is not there raises straight through `stage` as `scoring failed`. That
    is the second reason `test_bid_run_live.py` can no longer complete a run, alongside the
    usage sink above.
    """

    async def get(self, *, company_id: uuid.UUID) -> CompanyProfile | None:
        return None


async def _skip_planning(state: Any, config: Any = None) -> Any:
    """Stands in for `plan_checks`, which would read the companies table."""
    return {"bidder_country": "de"}


async def _skip_checking(state: Any, config: Any = None) -> Any:
    """Stands in for `check_reqs`. With requirements present the fan-out really does send to
    it, so this is a stub that is reached and not a decoration."""
    return {"matrix_rows": []}


async def run_pack(
    settings: Settings,
    pack: TenderPack,
    *,
    backend_dir: Path,
    company_id: str | None = None,
    bid_id: str | None = None,
    extract_reqs: BidNode | None = None,
    database: Database | None = None,
) -> PackRun:
    """Run the committed graph over one fixture pack and return everything it produced.

    Spends real money: this is the call `make test-live` and `scripts/extract_pack.py` pay
    for. It never asserts a budget — `test_bid_run_live.py` owns that judgement for the DE
    pack, because a budget is a property of the pack and the settings rather than of running
    one at all, and a script re-recording FR should not fail for a reason the report would
    rather state.

    `extract_reqs` is the one seam this function keeps, for the same reason `build_graph`
    keeps nine: the suite has to prove the wiring — that the pack is read off disk, that the
    usage sink is the one passed, that the run parks at the interrupt — and it cannot spend
    $1.74 to do it. Every caller that is paying for a run passes nothing and gets the
    committed extraction node.
    """
    company_id = company_id or str(uuid.uuid4())
    bid_id = bid_id or str(uuid.uuid4())
    pack_dir = pack.directory(backend_dir)
    rows = pack_documents(pack_dir, bid_id=bid_id, company_id=company_id)
    if not rows:
        raise ValueError(
            f"{pack.fixture_dir}: no documents to run — is the fixture checked out?"
        )

    projection = RecordingProjection(
        delegate=ReadModelProjection(database) if database is not None else None
    )
    sink = RecordingUsageSink()
    # With a database the run is the whole product: `plan_checks` reads the bidder's country,
    # `check_reqs` runs its per-requirement ReAct loop against the indexed corpora, and
    # `score_verdict` scores the real matrix against the real profile. Without one the run is
    # extraction alone -- which is what every figure in `REPORT.md` measures, and is why the
    # two are not comparable on cost or on duration.
    full = database is not None
    graph = build_graph(
        settings,
        database if database is not None else NoDatabase(),  # type: ignore[arg-type]
        parse_docs=_fixture_parser(pack_dir, rows),
        extract_reqs=extract_reqs,
        plan_checks=None if full else _skip_planning,
        check_reqs=None if full else _skip_checking,
        score_verdict=None if full else VerdictScorer(NoCompanyProfile()),
        projection=projection,
        usage=sink,
        checkpointer=MemorySaver(),
    )
    bid = BidRow(
        id=bid_id,
        company_id=company_id,
        thread_id=thread_id_of(bid_id),
        notice_number=pack.notice_number,
        title=pack.title,
        source_language=pack.source_language,
        bidder_language=pack.bidder_language,
        status=BidStatus.QUEUED,
    )
    config = bid_run_config(bid_id, thread_id=bid.thread_id, run_name=f"pack_run_{pack.name}")

    started = time.monotonic()
    await graph.ainvoke(initial_state(bid), config)
    elapsed = time.monotonic() - started
    snapshot = await graph.aget_state(config)

    return PackRun(
        requirements=tuple(projection.rows),
        problems=tuple(projection.problems),
        statuses=tuple(projection.statuses),
        usage=tuple(sink.events),
        matrix_rows=tuple(projection.matrix_rows),
        verdicts=tuple(projection.verdicts),
        elapsed_seconds=elapsed,
        parked=snapshot.next == (AWAIT_REVIEW,),
    )


# ---------------------------------------------------------------------- the three packs

DE = TenderPack(
    fixture_dir="tests/fixtures/tenders/de",
    notice_number="614251-2026",
    title="IPv6-Experten Los 2 — Netzwerk- und Informationstechnik (BMI)",
    source_language="de",
    bidder_language="de",
)
FR = TenderPack(
    fixture_dir="tests/fixtures/tenders/fr",
    notice_number="618320-2026",
    title="Conseil en architecture d'entreprise (Ministère de l'éducation nationale)",
    source_language="fr",
    bidder_language="de",
)
EN = TenderPack(
    fixture_dir="tests/fixtures/tenders/en",
    notice_number="606362-2026",
    title="Digital Communications Services (EASA)",
    source_language="en",
    bidder_language="de",
)

PACKS: Final[Mapping[str, TenderPack]] = {pack.name: pack for pack in (DE, FR, EN)}
"""The three golden tenders, keyed by the name their answer key and result file use.

**Every pack is bid in German**, including the two that are not written in it. That is the
product's wedge rather than a convenience: the bidder is the fictional German GmbH, and a
`bidder_language` equal to the source language would leave `Requirement.translation` a copy
of the quote and give S7.1's translation metric nothing to score on two tenders out of three.
It is also the only configuration under which the FR pack demonstrates what the project is
for — a German company reading a French tender.
"""
