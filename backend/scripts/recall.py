"""S3.2.3 — score extraction against the golden answer keys, and carry S6.4's verification.

    uv run scripts/recall.py                       # every result in tests/fixtures/extractions
    uv run scripts/recall.py path/to/result.json   # one or more named results

Prints recall on the mandatory requirements of each tender and exits non-zero when any of
them is below `evaluation.recall_threshold` in `settings.default.yaml`. Everything it reads
is a file: no network, no database, no model call, and no application secret — the runtime
YAML is loaded on its own so the script runs in a checkout with no `.env`.

**It does not run extraction.** One DE-pack run is 49 model calls, five minutes and $1.38
(ADR-0012), so the rows come from a saved `ExtractionResult`. To produce a real one, run
`make test-live` — `tests/integration/test_bid_run_live.py` writes the run it measures to
`tests/fixtures/extractions/` — and score the file it leaves behind. The results committed
today are `source: synthetic`: built from the golden labels to exercise this script, and
marked on every report so their number is never mistaken for a measurement.

**How a reviewer closes S6.4** — done for all three tenders on 2026-09-13, and kept here
because the procedure is the deliverable. The report lists, per tender, the golden labels
nothing found, the extracted rows no label explains (the one failure a verbatim check is
blind to), the stage-filter leaks and the field disagreements. Adjudicate those lists,
correct `tests/fixtures/tenders/<fixture>/golden.yaml`, and then set that file's
`meta.labelled_by` to `llm_assisted_human_verified` with `verified_by` naming you and
`verified_on` dated. Nothing in this script can do it for you.

**That flip closed S6.4 and did *not* close S3.2.1.** It was expected to — the plan's
Increment 1 row says so — and the expectation was wrong in an instructive way: verifying the
key made the number *trustworthy*, not *higher*. Measured against the verified key, recall is
0.72 on the committed live run and ~0.74 +/- 0.02 across four. S3.2.1's criterion is "at
least 0.9", so the story now fails on a measurement rather than waiting on a task.

Exit codes: 0 every tender clears the threshold, 1 one did not (or nothing was read), 2 the
inputs could not be read at all.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    # `[tool.uv] package = false`, so `crossbid` is importable only via the project root.
    sys.path.insert(0, str(BACKEND_DIR))

from pydantic import ValidationError  # noqa: E402  (after the sys.path fix)

from crossbid.eval.recall import exit_code_for, score_paths  # noqa: E402
from crossbid.eval.report import render  # noqa: E402
from crossbid.settings import SettingsError, load_runtime_settings  # noqa: E402

DEFAULT_EXTRACTIONS_DIR = BACKEND_DIR / "tests" / "fixtures" / "extractions"
DEFAULT_HINT = str(DEFAULT_EXTRACTIONS_DIR.relative_to(BACKEND_DIR))
INPUT_ERROR = 2


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "extractions",
        nargs="*",
        type=Path,
        help=(
            "Saved extraction results (JSON). Each names its own tender, so the golden "
            f"file is resolved from it. Default: every *.json in {DEFAULT_HINT}"
        ),
    )
    return parser.parse_args(argv)


def _paths(args: argparse.Namespace) -> list[Path]:
    if args.extractions:
        return list(args.extractions)
    return sorted(DEFAULT_EXTRACTIONS_DIR.glob("*.json"))


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    paths = _paths(args)
    try:
        threshold = load_runtime_settings().evaluation.recall_threshold
        scores = score_paths(paths, backend_dir=BACKEND_DIR, threshold=threshold)
    except (OSError, ValidationError, SettingsError, ValueError) as err:
        print(f"recall: cannot score these inputs: {err}", file=sys.stderr)
        return INPUT_ERROR

    print(render(scores))
    return exit_code_for(scores)


if __name__ == "__main__":
    sys.exit(main())
