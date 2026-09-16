"""S3.1.1's budget criterion: the DE pack reaches the interrupt in time and on budget.

Marked `live`: it calls OpenRouter on the default models for every section of the 28-file,
191-page pack (ADR-0001), which costs real money and minutes. It is **not** run by
`make test`; `make test-live` runs it, and it skips rather than fails on a machine with no
`OPENROUTER_API_KEY`.

**The run itself moved to `crossbid.eval.packrun` at S7.1 and this module kept the
judgement.** The report needs the same run over FR and EN and over a second model, and four
callers of a test-local helper would have become four slightly different definitions of "a
run against a fixture pack" — after which the numbers they produced would no longer be
comparable, which is the only reason to record them. What is asserted here is what remains
specific to this pack: that DE parks at the interrupt inside `agent.run_budget_seconds` and
`agent.run_budget_usd`. `scripts/extract_pack.py` re-records the other packs and asserts
nothing, because a budget is a property of a pack and its settings, not of running one.

What is real and what is not is documented on `run_pack`. In short: real graph, real parser,
real extraction, real model calls, real interrupt; no Storage, no Postgres, no checking, and
no embedding — the last of which is about $0.004 of the DE run and is named in the report
rather than silently missing from it.

**Two reasons this test could not have passed between S5.2 and S7.1**, both fixed by moving
on to `run_pack` and both pinned offline by `tests/unit/test_packrun.py`:

1. `stage` captures every model response into a `UsageSink` (ADR-0056), and the default sink
   writes to Postgres. The old fake database refused to connect, so the first captured call
   raised and the run failed having already paid for it.
2. `score_verdict` reads the bidder's profile unconditionally, and `_profile` catches only
   `CompanyReadModelError` and `ValueError` — a database that is not there raises straight
   through as `scoring failed`.

That is why the committed DE figure is dated 2026-09-13 and why S7.1 re-records it.

The run also *writes* what it extracted, to `tests/fixtures/extractions/de.live.json`
(S3.2.3). Recall is measured from that file afterwards by `uv run scripts/recall.py`, offline
and for free; without it every recall number would cost another $1.74 and four minutes.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from crossbid.agent.runner import RunBudget
from crossbid.eval.extraction import (
    ExtractionMeta,
    ExtractionResult,
    ExtractionSource,
    dump_extraction,
)
from crossbid.eval.packrun import DE, PackRun, pack_documents, run_pack
from crossbid.models.tender import BidStatus
from crossbid.settings import Settings, SettingsError, load_settings

pytestmark = pytest.mark.live

BACKEND_DIR = Path(__file__).resolve().parents[2]
EXPECTED_DOCUMENT_COUNT = 29
"""The 28 procurement documents **and** the notice PDF one level up.

It was 28 until S7.1. CLAUDE.md records the two counts a glob can give on this pack -- 191
pages for `documents/*.pdf`, 202 with the notice -- and the run took the smaller one while
the answer key labelled six scored requirements on the notice. See `pack_documents`."""

RESULT_PATH = BACKEND_DIR / "tests" / "fixtures" / "extractions" / "de.live.json"
"""Where this run leaves its rows for `scripts/recall.py` (S3.2.3).

Written rather than printed because extraction costs money and minutes: the one artefact
that can be scored offline afterwards is the reason to pay for it once rather than every time
somebody wants a recall number. `de.json` beside it is the synthetic stand-in, and the two
are told apart by `meta.source`, never by the filename.
"""


def resolve_settings() -> Settings | None:
    try:
        return load_settings()
    except SettingsError:
        return None


SETTINGS = resolve_settings()
skip_without_key = pytest.mark.skipif(SETTINGS is None, reason="OPENROUTER_API_KEY is not set")


def write_result(run: PackRun, settings: Settings) -> None:
    """Keep the rows this run paid for, so S3.2.3 can score them without paying again.

    Called before the budget assertions on purpose: a run that overshoots the time or cost
    limit still extracted requirements, and throwing them away would mean paying twice to
    find out what recall the overshooting run had.
    """
    dump_extraction(
        ExtractionResult(
            meta=ExtractionMeta(
                fixture_dir=DE.fixture_dir,
                source=ExtractionSource.LIVE_RUN,
                produced_on=date.today(),
                method=(
                    "The committed graph over the 28-file DE pack on the configured models, "
                    "run by tests/integration/test_bid_run_live.py through "
                    "crossbid.eval.packrun.run_pack. Checking is stubbed and nothing is "
                    "embedded, so the cost is extraction's alone."
                ),
                models=dict(settings.runtime.models.model_dump()),
                cost_usd=run.cost_usd,
                elapsed_seconds=run.elapsed_seconds,
            ),
            requirements=run.requirements,
            problems=run.problems,
        ),
        RESULT_PATH,
    )


@skip_without_key
@pytest.mark.anyio
async def test_the_de_pack_reaches_awaiting_review_within_the_time_and_cost_budget() -> None:
    assert SETTINGS is not None
    documents = pack_documents(DE.directory(BACKEND_DIR), bid_id="b", company_id="c")
    assert len(documents) == EXPECTED_DOCUMENT_COUNT, "the DE fixture changed shape"
    budget = RunBudget.from_settings(SETTINGS)

    # Act
    run = await run_pack(SETTINGS, DE, backend_dir=BACKEND_DIR)
    write_result(run, SETTINGS)

    # Assert -- parked for a human, with rows, inside both limits
    assert run.parked, "the run did not stop at await_review"
    assert run.statuses[:2] == (BidStatus.PARSING, BidStatus.EXTRACTING)
    assert run.statuses[-1] is BidStatus.AWAITING_REVIEW
    assert set(run.statuses[2:-1]) == {BidStatus.CHECKING}
    assert run.requirements, "extraction wrote no requirements"
    assert run.calls > 0, "no model call was captured; the usage sink is not wired"
    assert run.cost_usd > 0, "OpenRouter reported no cost: check USAGE_ACCOUNTING_EXTRA_BODY"
    assert run.elapsed_seconds < budget.seconds, (
        f"{run.elapsed_seconds:.0f}s to awaiting_review, budget {budget.seconds}s"
    )
    assert run.cost_usd < budget.usd, f"${run.cost_usd:.2f} spent, budget ${budget.usd}"
