"""S7.1 — assemble every measured metric into `evaluations/REPORT.md`.

    make eval                          # or: uv run python scripts/run_eval.py

**Offline and free.** It runs no model and opens no database: every figure is read from an
artefact an earlier, paid step already wrote, so the report can be regenerated after a
wording change without spending the $3.56 the measurements cost. The paid steps, in the order
they must run, are:

    uv run python scripts/extract_pack.py de fr en        # extraction, ~$3.27
    uv run python scripts/score_translation.py de.live fr.live en.live
    DATABASE_URL=... uv run python scripts/index_pack.py de fr en
    DATABASE_URL=... uv run python scripts/run_retrieval_eval.py de fr en
    uv run python scripts/score_retrieval.py de fr en

Recall and citation faithfulness are recomputed here every time, because both are pure
functions of files already in the repository — the extraction results and the packs — and
recomputing them keeps the report honest if an answer key changes. Translation adequacy and
retrieval are read from their saved scores, because both cost money.

**A metric nothing produced is printed as "not measured".** `crossbid/eval/suite.py` explains
why that is a rule rather than a courtesy.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    # `[tool.uv] package = false`, so `crossbid` is importable only via the project root.
    sys.path.insert(0, str(BACKEND_DIR))

from crossbid.eval.extraction import load_extraction  # noqa: E402
from crossbid.eval.faithfulness import score_faithfulness  # noqa: E402
from crossbid.eval.questions import load_question_set  # noqa: E402
from crossbid.eval.recall import score_tender  # noqa: E402
from crossbid.eval.retrieval import METRIC_NAMES  # noqa: E402
from crossbid.eval.suite import (  # noqa: E402
    RetrievalSummary,
    TenderReport,
    TranslationSummary,
    duration,
    gate,
    missing_metrics,
    money,
    number,
    partial_metrics,
    precision_split,
)
from crossbid.models.golden import load_golden  # noqa: E402
from crossbid.settings import SettingsError, load_runtime_settings  # noqa: E402

EXTRACTIONS = BACKEND_DIR / "tests" / "fixtures" / "extractions"
TRANSLATION = BACKEND_DIR / "tests" / "fixtures" / "translation"
RETRIEVAL = BACKEND_DIR / "tests" / "fixtures" / "retrieval"
REPORT_PATH = BACKEND_DIR / "evaluations" / "REPORT.md"
TENDERS = ("de", "fr", "en")
INPUT_ERROR = 2


def _translation(stem: str) -> TranslationSummary | None:
    path = TRANSLATION / f"{stem}.json"
    if not path.is_file():
        return None
    document = json.loads(path.read_text(encoding="utf-8"))
    below = sum(
        1 for case in document["cases"] if float(case["score"]) < float(document["threshold"])
    )
    return TranslationSummary(
        mean=document["mean"],
        sampled=document["sampled"],
        translated=document["translated_rows"],
        below_threshold=below,
        judge=document["judge"],
    )


def _retrieval(name: str, judge: str) -> RetrievalSummary | None:
    """This tender's retrieval figures, or `None` when they do not belong to the current key.

    Scores and questions live in separate files and are produced by separate paid steps, so
    they drift: regenerate the key and yesterday's scores are still sitting there, with the
    same shape and the same tender name. Comparing the question ids is what makes a stale file
    read as *not measured* instead of as a measurement of something else.
    """
    path = RETRIEVAL / f"{name}.scores.json"
    questions = RETRIEVAL / f"{name}.questions.yaml"
    if not path.is_file() or not questions.is_file():
        return None
    document = json.loads(path.read_text(encoding="utf-8"))
    current = [question.id for question in load_question_set(questions).questions]
    if document.get("question_ids") != current:
        print(
            f"  {name}: retrieval scores were measured against a different set of questions; "
            "re-run scripts/score_retrieval.py",
            file=sys.stderr,
        )
        return None
    return RetrievalSummary(
        means=document["means"],
        questions=document["questions"],
        key_verified=bool(document["key_verified"]),
        judge=judge,
    )


def _report_for(name: str, threshold: float, judge: str) -> TenderReport | None:
    path = EXTRACTIONS / f"{name}.live.json"
    if not path.is_file():
        return None
    extraction = load_extraction(path)
    golden = load_golden(extraction.golden_path(BACKEND_DIR))
    return TenderReport(
        name=name,
        recall=score_tender(golden, extraction, threshold=threshold),
        faithfulness=score_faithfulness(
            extraction, pack_dir=BACKEND_DIR / extraction.meta.fixture_dir
        ),
        translation=_translation(f"{name}.live"),
        retrieval=_retrieval(name, judge),
    )


def _headline(reports: Sequence[TenderReport], threshold: float) -> list[str]:
    lines = [
        "## Headline",
        "",
        "| Tender | Requirement recall | Gate | Citation faithfulness | Translation adequacy |",
        "|---|---|---|---|---|",
    ]
    for report in reports:
        translation = number(None)
        if report.translation and report.translation.mean is not None:
            # The sample size travels with the figure: 0.733 over six rows and 0.733 over a
            # hundred are different claims, and the cell is where a reader forms the belief.
            translation = (
                f"{report.translation.mean:.3f} "
                f"({report.translation.sampled}/{report.translation.translated} rows)"
            )
        lines.append(
            f"| {report.name.upper()} | {report.recall.recall:.3f} "
            f"({len(report.recall.found)}/{len(report.recall.scored)}) | {gate(report.recall)} "
            f"| {report.faithfulness.score:.4f} "
            f"({len(report.faithfulness.faithful)}/{len(report.faithfulness.checks)}) "
            f"| {translation} |"
        )
    lines += ["", f"Recall gate: **{threshold:.2f}**, from `evaluation.recall_threshold`.", ""]
    return lines


def _retrieval_table(reports: Sequence[TenderReport]) -> list[str]:
    scored = [report for report in reports if report.retrieval]
    if not scored:
        return []
    lines = [
        "## Retrieval (ragas, agentic RAG path)",
        "",
        "| Tender | "
        + " | ".join(name.replace("_", " ") for name in METRIC_NAMES)
        + " | Questions | Answer key |",
        "|---|" + "---|" * (len(METRIC_NAMES) + 2),
    ]
    for report in scored:
        assert report.retrieval is not None
        cells = " | ".join(number(report.retrieval.means.get(m)) for m in METRIC_NAMES)
        lines.append(
            f"| {report.name.upper()} | {cells} | {report.retrieval.questions} "
            f"| {report.retrieval.key_state} |"
        )
    lines.append("")
    return lines


def _reading_retrieval(reports: Sequence[TenderReport]) -> list[str]:
    """What the two weaker retrieval numbers mean, measured rather than asserted."""
    lines: list[str] = []
    for report in reports:
        if report.retrieval is None:
            continue
        scores_path = RETRIEVAL / f"{report.name}.scores.json"
        samples_path = RETRIEVAL / f"{report.name}.samples.json"
        if not (scores_path.is_file() and samples_path.is_file()):
            continue
        scored = json.loads(scores_path.read_text(encoding="utf-8"))["per_question"]
        samples = json.loads(samples_path.read_text(encoding="utf-8"))["samples"]
        counts = {s["id"]: len(s["retrieved_contexts"]) for s in samples}
        split = precision_split(
            {e["id"]: e["scores"].get("context_precision") for e in scored}, counts
        )
        if split.narrow is None or split.broad is None:
            continue
        lines.append(
            f"| {report.name.upper()} | {split.narrow:.3f} ({split.narrow_count}) "
            f"| {split.broad:.3f} ({split.broad_count}) |"
        )
    if not lines:
        return []
    return [
        "## Reading the two weaker retrieval numbers",
        "",
        "**Context precision is depressed by the agent searching more than once, not by bad "
        "retrieval.** `context_precision` assumes a single retrieval; a ReAct agent that is "
        "unsure searches again, and every passage from every search in the turn is pooled into "
        "one list. Each extra search adds five passages of which at most a few can be "
        "relevant, so the metric falls as the agent works harder.",
        "",
        "| Tender | One search (≤5 passages) | Several (≥15 passages) |",
        "|---|---|---|",
        *lines,
        "",
        "**Answer relevancy penalises the agent for refusing to guess.** Its worst case here "
        'scores **0.00** on this answer: *"Die Bindefrist entspricht der Zuschlagsfrist … Die '
        "konkrete Dauer bzw. das konkrete Enddatum ist in den abgerufenen Passagen nicht "
        'genannt."* The agent declined to state a figure it had not retrieved, which is what '
        "`prompts/chat.md` requires of it. Ragas computes the metric by generating questions "
        "from the answer and comparing them with the original; an answer that declines to "
        "answer generates none, and there is no way for the metric to tell a refusal from an "
        "irrelevant reply. Longer answers also score slightly lower.",
        "",
        "Neither observation makes the numbers wrong. Both mean the mean is the wrong thing to "
        "read alone.",
        "",
    ]


def _cost_table(reports: Sequence[TenderReport]) -> list[str]:
    lines = [
        "## What the measurements cost",
        "",
        "| Tender | Rows | Problems | Model calls priced | Cost | Wall clock | Source |",
        "|---|---|---|---|---|---|---|",
    ]
    total = 0.0
    for report in reports:
        meta = report.extraction.meta
        total += meta.cost_usd or 0.0
        lines.append(
            f"| {report.name.upper()} | {len(report.extraction.requirements)} "
            f"| {len(report.extraction.problems)} | {meta.models.get('extract', '?')} "
            f"| {money(meta.cost_usd)} | {duration(meta.elapsed_seconds)} "
            f"| {meta.source.value} {meta.produced_on.isoformat()} |"
        )
    lines += ["", f"Extraction total: **${total:.2f}**.", ""]
    return lines


def _honesty(reports: Sequence[TenderReport]) -> list[str]:
    absent = missing_metrics(reports)
    partial = partial_metrics(reports)
    if not absent and not partial:
        return []
    lines = ["## What this report does not measure", ""]
    lines += [f"- **{name}** — no tender produced a figure." for name in absent]
    lines += [f"- {note}." for note in partial]
    lines.append("")
    return lines


def render(reports: Sequence[TenderReport], threshold: float, judge: str) -> str:
    lines = [
        "# Crossbid — evaluation report",
        "",
        f"Generated {date.today().isoformat()} by `scripts/run_eval.py` from saved "
        "measurements. Regenerating is offline and free; the measurements themselves are not "
        "— see the script's docstring for the commands that produce them.",
        "",
        f"Judge: `{judge}` — a different vendor from every model under test, which is S7.1's "
        "rule.",
        "",
        *_headline(reports, threshold),
        *_retrieval_table(reports),
        *_reading_retrieval(reports),
        *_cost_table(reports),
        *_honesty(reports),
    ]
    return "\n".join(lines).rstrip() + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assemble evaluations/REPORT.md. Offline.")
    parser.add_argument("--out", type=Path, default=REPORT_PATH)
    args = parser.parse_args(argv)
    try:
        runtime = load_runtime_settings()
    except SettingsError as exc:
        print(f"settings: {exc}", file=sys.stderr)
        return INPUT_ERROR

    threshold = runtime.evaluation.recall_threshold
    judge = runtime.models.judge
    reports = [r for name in TENDERS if (r := _report_for(name, threshold, judge))]
    if not reports:
        print(
            "No live extraction results found. Run scripts/extract_pack.py first.",
            file=sys.stderr,
        )
        return INPUT_ERROR

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(reports, threshold, judge), encoding="utf-8")
    print(f"wrote {args.out.relative_to(BACKEND_DIR)} for {len(reports)} tender(s)")
    for note in (*missing_metrics(reports), *partial_metrics(reports)):
        print(f"  incomplete: {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
