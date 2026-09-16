"""S7.1 — judge translation adequacy on a sample of each tender's extracted rows.

    uv run python scripts/score_translation.py de fr en --sample 30

Reads the saved extraction results and writes `tests/fixtures/translation/<name>.json`.

Its own directory, not beside the extractions: `tests/fixtures/extractions/*.json` is globbed
by `test_recall_script.py` and every file there has to validate as an `ExtractionResult`. A
score file dropped in among them fails collection for the whole suite, which is how this was
found.
Costs money: one GEval judgement per sampled row, on the `judge` slug. Thirty rows per tender
is a few cents; judging all 311 DE rows would cost more than the extraction that produced
them, which is why `crossbid/eval/translation.py` samples.

**Telemetry is switched off before DeepEval is imported.** DeepEval ships a PostHog client
that reports usage on import, and this repository's rule is that nothing leaves the machine
that was not asked for — the tender text certainly does not, but neither should the fact that
an eval ran. `DEEPEVAL_TELEMETRY_OPT_OUT` has to be set before the import, not after, so it
is set here rather than in a Makefile line somebody can forget.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    # `[tool.uv] package = false`, so `crossbid` is importable only via the project root.
    sys.path.insert(0, str(BACKEND_DIR))

# Before the DeepEval import, deliberately. See the module docstring.
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")

from deepeval.metrics import GEval  # noqa: E402
from deepeval.models import OpenAIModel  # noqa: E402
from deepeval.test_case import LLMTestCase, LLMTestCaseParams  # noqa: E402

from crossbid.eval.extraction import load_extraction  # noqa: E402
from crossbid.eval.translation import (  # noqa: E402
    CRITERIA,
    EVALUATION_STEPS,
    THRESHOLD,
    TranslationCase,
    sample_cases,
    translated_rows,
)
from crossbid.settings import SettingsError, load_settings  # noqa: E402

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
EXTRACTIONS_DIR = BACKEND_DIR / "tests" / "fixtures" / "extractions"
TRANSLATION_DIR = BACKEND_DIR / "tests" / "fixtures" / "translation"
INPUT_ERROR = 2


def _metric(api_key: str, slug: str) -> GEval:
    """GEval with fixed steps, on the judge slug, through OpenRouter."""
    return GEval(
        name="Translation adequacy",
        criteria=CRITERIA,
        evaluation_steps=list(EVALUATION_STEPS),
        evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
        model=OpenAIModel(model=slug, api_key=api_key, base_url=OPENROUTER_BASE_URL),
        threshold=THRESHOLD,
        async_mode=False,
    )


def _judge(metric: GEval, case: TranslationCase) -> tuple[float, str]:
    metric.measure(LLMTestCase(input=case.source_text, actual_output=case.translation))
    return float(metric.score or 0.0), str(metric.reason or "")


def _score(name: str, metric: GEval, slug: str, limit: int) -> Path:
    extraction = load_extraction(EXTRACTIONS_DIR / f"{name}.json")
    population = translated_rows(extraction)
    cases = sample_cases(extraction, limit=limit)

    judged: list[dict[str, object]] = []
    for case in cases:
        score, reason = _judge(metric, case)
        judged.append(
            {
                "requirement_id": case.requirement_id,
                "document_name": case.document_name,
                "page": case.page,
                "source_lang": case.source_lang,
                "source_text": case.source_text,
                "translation": case.translation,
                "score": score,
                "reason": reason,
            }
        )
        flag = "" if score >= THRESHOLD else "   <- below threshold"
        print(f"  {case.document_name} p.{case.page}: {score:.2f}{flag}", flush=True)

    mean = sum(float(e["score"]) for e in judged) / len(judged) if judged else None
    TRANSLATION_DIR.mkdir(parents=True, exist_ok=True)
    path = TRANSLATION_DIR / f"{name}.json"
    path.write_text(
        json.dumps(
            {
                "fixture_dir": extraction.meta.fixture_dir,
                "judge": slug,
                "translated_rows": len(population),
                "sampled": len(judged),
                "threshold": THRESHOLD,
                "mean": mean,
                "cases": judged,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    printable = f"{mean:.3f}" if mean is not None else "n/a"
    below = sum(1 for e in judged if float(e["score"]) < THRESHOLD)
    print(
        f"{name}: translation adequacy {printable} over {len(judged)} of "
        f"{len(population)} translated rows; {below} below {THRESHOLD}"
    )
    return path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Judge translation adequacy. Costs money.")
    parser.add_argument("results", nargs="+", help="extraction result stems, e.g. de.live")
    parser.add_argument("--sample", type=int, default=30)
    args = parser.parse_args(argv)
    try:
        settings = load_settings()
    except SettingsError as exc:
        print(f"settings: {exc}", file=sys.stderr)
        return INPUT_ERROR

    slug = settings.runtime.models.judge
    metric = _metric(settings.env.openrouter_api_key.get_secret_value(), slug)
    print(f"judge: {slug}")
    for name in args.results:
        print(f"scoring {name} …", flush=True)
        _score(name, metric, slug, args.sample)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
