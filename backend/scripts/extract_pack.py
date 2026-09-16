"""S7.1 — run extraction on one golden tender and keep the rows, so the report can score them.

    uv run scripts/extract_pack.py fr                          # one pack, configured models
    uv run scripts/extract_pack.py de --model openai/gpt-5.6-luna --suffix luna
    uv run scripts/extract_pack.py de fr en                    # all three, in order

**This spends real money.** Every invocation calls OpenRouter once per section of the pack,
and the cost scales with pages: the DE pack is 191 of them and cost $1.74 on 2026-09-13, the
EN pack is 133, the FR pack is 20. Nothing here is run by `make test` or by CI, and nothing
here retries a pack: a failed run has already paid for the calls it made, so the failure is
printed with what it managed to extract rather than swallowed into a second attempt.

**Why this exists beside `make test-live`.** `tests/integration/test_bid_run_live.py` runs the
DE pack and asserts S3.1.1's budget on it; that is a judgement about one pack, and turning it
into a loop over three would have made a failing FR run look like a broken German budget. The
run itself is `crossbid.eval.packrun.run_pack`, which both callers share, so the figures stay
comparable — that was the whole reason to extract it.

**`--model` overrides the `extract` role only**, and the override is re-validated rather than
patched in: `Settings` refuses a chat slug that is not in `available_models`, which is the
verified set and not OpenRouter's catalogue (ADR-0005). A slug nobody probed is rejected here
rather than discovered halfway through a paid run.

The result lands at `tests/fixtures/extractions/<pack>.live[.<suffix>].json` and is read
afterwards, offline and for free, by `scripts/recall.py` and `scripts/run_eval.py`.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    # `[tool.uv] package = false`, so `crossbid` is importable only via the project root.
    sys.path.insert(0, str(BACKEND_DIR))

from pydantic import ValidationError  # noqa: E402  (after the sys.path fix)

from crossbid.eval.extraction import (  # noqa: E402
    ExtractionMeta,
    ExtractionResult,
    ExtractionSource,
    dump_extraction,
)
from crossbid.eval.packrun import PACKS, PackRun, TenderPack, run_pack  # noqa: E402
from crossbid.settings import Settings, SettingsError, load_settings  # noqa: E402

EXTRACTIONS_DIR = BACKEND_DIR / "tests" / "fixtures" / "extractions"
INPUT_ERROR = 2
RUN_FAILED = 1


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run extraction on one or more golden tenders. Costs money.",
    )
    parser.add_argument(
        "packs",
        nargs="+",
        choices=sorted(PACKS),
        help="which golden tender to extract",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="override the `extract` role's slug; must be one of available_models",
    )
    parser.add_argument(
        "--suffix",
        default=None,
        help="tag the result file, e.g. --suffix luna -> de.live.luna.json",
    )
    return parser.parse_args(argv)


def _with_extract_model(settings: Settings, slug: str) -> Settings:
    """`settings` with the `extract` role repointed, re-validated on the way through.

    `model_copy` would be shorter and would skip every validator, including the one that
    refuses a slug nobody has probed. Dumping and re-validating costs nothing here and keeps
    the override under the same rule as the file.
    """
    data = settings.model_dump()
    data["runtime"]["models"]["extract"] = slug
    return Settings.model_validate(data)


def _result_path(pack: TenderPack, suffix: str | None) -> Path:
    tag = f".{suffix}" if suffix else ""
    return EXTRACTIONS_DIR / f"{pack.name}.live{tag}.json"


def _method(pack: TenderPack, settings: Settings) -> str:
    """How these rows were produced, in the words a reader of the report needs.

    Names what is stubbed, because a cost quoted without that is a cost for a different run.
    """
    return (
        f"The committed graph over the {pack.name.upper()} pack "
        f"({pack.notice_number}), bid in {pack.bidder_language}, run by "
        f"scripts/extract_pack.py through crossbid.eval.packrun.run_pack on "
        f"extract={settings.runtime.models.extract}. Checking is stubbed and nothing is "
        f"embedded, so the cost and duration are extraction's alone."
    )


def _report(pack: TenderPack, run: PackRun, path: Path) -> str:
    parked = "parked at awaiting_review" if run.parked else "DID NOT PARK"
    return (
        f"{pack.name}: {len(run.requirements)} requirements, {len(run.problems)} problems, "
        f"{run.calls} calls, ${run.cost_usd:.4f}, {run.elapsed_seconds:.0f}s — {parked}\n"
        f"  written to {path.relative_to(BACKEND_DIR)}"
    )


async def _extract(settings: Settings, pack: TenderPack, suffix: str | None) -> bool:
    run = await run_pack(settings, pack, backend_dir=BACKEND_DIR)
    path = _result_path(pack, suffix)
    dump_extraction(
        ExtractionResult(
            meta=ExtractionMeta(
                fixture_dir=pack.fixture_dir,
                source=ExtractionSource.LIVE_RUN,
                produced_on=date.today(),
                method=_method(pack, settings),
                models=dict(settings.runtime.models.model_dump()),
                cost_usd=run.cost_usd,
                elapsed_seconds=run.elapsed_seconds,
            ),
            requirements=run.requirements,
            problems=run.problems,
        ),
        path,
    )
    print(_report(pack, run, path))
    return run.parked and bool(run.requirements)


async def _main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        settings = load_settings()
    except SettingsError as exc:
        print(f"settings: {exc}", file=sys.stderr)
        return INPUT_ERROR
    if args.model:
        try:
            settings = _with_extract_model(settings, args.model)
        except (SettingsError, ValidationError) as exc:
            print(f"--model {args.model}: {exc}", file=sys.stderr)
            return INPUT_ERROR

    ok = True
    for name in args.packs:
        pack = PACKS[name]
        print(f"running {name} on extract={settings.runtime.models.extract} …", flush=True)
        ok = await _extract(settings, pack, args.suffix) and ok
    return 0 if ok else RUN_FAILED


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
