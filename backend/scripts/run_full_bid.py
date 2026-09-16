"""S7.4 — run a whole bid, checking included, and report the verdict the agent reached.

    DATABASE_URL=... uv run python scripts/run_full_bid.py de

Needs `scripts/index_pack.py <pack> --with-evidence` to have run against the same database:
`check_reqs` searches the tender corpus *and* the bidder's own documents, and against an empty
corpus every requirement comes back unsupported for the wrong reason.

**This is the only script here that runs the product end to end.** `extract_pack.py` stops
after extraction, which is what every figure in `REPORT.md` measures and why those figures are
cheap. This one runs the per-requirement ReAct loop as well, so it costs more and takes longer,
and it is the only way to see a verdict the agent actually reached rather than one assembled by
hand.

**What it was written for.** The user guide's third walkthrough is a bid the agent recommends
against, and a screenshot of a `no_go` proves nothing on its own. Seed the small company
(`index_pack.py --profile small`), run this, and the no-go is agent output: a mandatory
requirement whose threshold the company's own figures do not clear, an `unsupported` row, a
blocking gap. Seed `--profile demo` and the same tender on the same evidence comes back
differently. The two runs are the experiment.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    # `[tool.uv] package = false`, so `crossbid` is importable only via the project root.
    sys.path.insert(0, str(BACKEND_DIR))

from crossbid.db import Database  # noqa: E402
from crossbid.eval.packrun import PACKS, run_pack  # noqa: E402
from crossbid.readmodel.companies import CompaniesReadModel  # noqa: E402
from crossbid.settings import SettingsError, load_settings  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from index_pack import ids_for  # noqa: E402

INPUT_ERROR = 2


async def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one bid end to end. Costs money.")
    parser.add_argument("pack", choices=sorted(PACKS))
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="write the verdict and the row counts here; a run costs money and minutes, so "
        "the result should outlive the terminal it was printed in",
    )
    args = parser.parse_args(argv)
    try:
        settings = load_settings()
    except SettingsError as exc:
        print(f"settings: {exc}", file=sys.stderr)
        return INPUT_ERROR
    dsn = settings.env.database_url
    if dsn is None:
        print("DATABASE_URL is not set — point it at the indexed database", file=sys.stderr)
        return INPUT_ERROR

    pack = PACKS[args.pack]
    company_id, bid_id = ids_for(pack)
    database = await Database.connect(dsn.get_secret_value())
    try:
        profile = await CompaniesReadModel(database).get(company_id=company_id)
        if profile is None:
            print(f"no company {company_id} — run index_pack.py first", file=sys.stderr)
            return INPUT_ERROR
        turnover = ", ".join(f"{entry.year}: {entry.amount:,.0f}" for entry in profile.turnover)
        print(f"bidder: {profile.name} — {profile.staff_fte} FTE, turnover {turnover}")
        print(f"running {pack.name} end to end (extraction + checking) …", flush=True)

        run = await run_pack(
            settings,
            pack,
            backend_dir=BACKEND_DIR,
            company_id=str(company_id),
            bid_id=str(bid_id),
            database=database,
        )
    finally:
        await database.close()

    statuses = Counter(row.status.value for row in run.matrix_rows)
    print(
        f"\n{len(run.requirements)} requirements, {len(run.matrix_rows)} matrix rows, "
        f"{run.calls} calls, ${run.cost_usd:.4f}, {run.elapsed_seconds:.0f}s"
    )
    print("  rows: " + (", ".join(f"{k}={v}" for k, v in sorted(statuses.items())) or "none"))
    if not run.verdicts:
        print("  no verdict was scored", file=sys.stderr)
        return 1
    verdict = run.verdicts[-1]
    print(f"\n  VERDICT: {verdict.decision.value.upper()}")
    print(
        f"  {verdict.mandatory_supported} of {verdict.mandatory_total} mandatory supported, "
        f"{len(verdict.gaps)} gap(s)"
    )
    for gap in verdict.gaps[:10]:
        print(f"    [{gap.severity.value}] {gap.summary}")
        if gap.required or gap.actual:
            print(f"       required {gap.required!r} · actual {gap.actual!r}")

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(
                {
                    "pack": pack.name,
                    "company": profile.name,
                    "staff_fte": profile.staff_fte,
                    "staff_fte_relevant": profile.staff_fte_relevant,
                    "turnover": [
                        {"year": e.year, "amount": e.amount} for e in profile.turnover
                    ],
                    "requirements": len(run.requirements),
                    "matrix_rows": len(run.matrix_rows),
                    "row_statuses": dict(sorted(statuses.items())),
                    "calls": run.calls,
                    "cost_usd": run.cost_usd,
                    "elapsed_seconds": run.elapsed_seconds,
                    "decision": verdict.decision.value,
                    "mandatory_supported": verdict.mandatory_supported,
                    "mandatory_total": verdict.mandatory_total,
                    "gaps": [
                        {
                            "severity": gap.severity.value,
                            "summary": gap.summary,
                            "required": gap.required,
                            "actual": gap.actual,
                        }
                        for gap in verdict.gaps
                    ],
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"\n  written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
