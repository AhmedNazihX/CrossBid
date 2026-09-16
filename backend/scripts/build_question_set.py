"""S7.1 — draft a retrieval answer key from the verified golden labels.

    uv run python scripts/build_question_set.py de fr en --per-tender 30

Writes `tests/fixtures/retrieval/<pack>.questions.yaml`. **The draft is not the key.** Every
file it writes is `state: draft`, and `crossbid/eval/questions.py` refuses to call a draft
verified; a human reads the questions, fixes the ones that give the answer away or ask
something the passage does not answer, and sets `state`, `verified_by` and `verified_on`.
`REPORT.md` prints which state it scored against, for the same reason the extraction report
prints `labelled_by`.

**Only the wording is generated.** The answer (`reference`) is the label's human-verified
`summary` and the passage (`reference_contexts`) is its verbatim `quote`, both carried across
untouched. So the model is never asked what is true about the tender — only to phrase the
question a bidder would have asked to get that answer, which is a much smaller thing to get
wrong and a much faster thing to check.

**Labels are sampled across documents, not taken in file order.** Retrieval scored on thirty
questions that all point at one PDF would measure whether that PDF embeds well, and the DE
pack has 29 documents. The sampler walks the documents round-robin so the questions spread,
and it is seeded so two runs of this script produce the same key.

Cost: one cheap-model call per question, a fraction of a cent for all three tenders.
"""

from __future__ import annotations

import argparse
import asyncio
import itertools
import random
import sys
from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    # `[tool.uv] package = false`, so `crossbid` is importable only via the project root.
    sys.path.insert(0, str(BACKEND_DIR))

from pydantic import BaseModel, Field  # noqa: E402

from crossbid.eval.packrun import PACKS, TenderPack  # noqa: E402
from crossbid.eval.questions import (  # noqa: E402
    QuestionSet,
    QuestionSetMeta,
    RetrievalQuestion,
    VerificationState,
    dump_question_set,
)
from crossbid.eval.recall import scored_labels  # noqa: E402
from crossbid.llm import chat_model  # noqa: E402
from crossbid.models.golden import GoldenRequirement, load_golden  # noqa: E402
from crossbid.settings import ModelRole, Settings, SettingsError, load_settings  # noqa: E402

RETRIEVAL_DIR = BACKEND_DIR / "tests" / "fixtures" / "retrieval"
SAMPLE_SEED = 20260916
"""Fixed, so re-running this script proposes the same questions and a reviewer's work on a
previous draft is not thrown away by a reshuffle."""

INPUT_ERROR = 2

PROMPT = """You write the question a bidder would have asked.

You are given one requirement from a public tender: the verbatim clause, and a one-line
English summary of what it demands. Write the single question a bidder reading this tender
would type to find that clause.

Rules:
- Write the question in {language}, the bidder's language.
- Ask about the substance. Never quote the clause and never restate the summary as a
  statement with a question mark on the end — a question that contains its own answer
  measures nothing.
- Ask about one thing, the way a person types into a search box, not a legal sub-clause.
- Do not mention document names, page numbers, article numbers, or the word "tender".
- Return the question only, with no preamble and no quotation marks.

Clause (verbatim, {source_language}):
{quote}

What it demands (English):
{summary}
"""


class DraftedQuestion(BaseModel):
    """The one field the model is allowed to produce."""

    question: str = Field(min_length=1, description="The bidder's question, in their language")


def _sample(labels: Sequence[GoldenRequirement], limit: int) -> list[GoldenRequirement]:
    """`limit` labels spread across the pack's documents, deterministically."""
    by_document: defaultdict[str, list[GoldenRequirement]] = defaultdict(list)
    for label in labels:
        by_document[label.doc].append(label)

    # S311: this shuffle picks which questions to draft, not a key or a token.
    rng = random.Random(SAMPLE_SEED)  # noqa: S311
    for entries in by_document.values():
        rng.shuffle(entries)

    rounds = itertools.zip_longest(*(by_document[doc] for doc in sorted(by_document)))
    spread = [label for group in rounds for label in group if label is not None]
    return spread[:limit]


async def _draft(settings: Settings, pack: TenderPack, label: GoldenRequirement) -> str:
    model = chat_model(ModelRole.CHEAP, settings).with_structured_output(DraftedQuestion)
    prompt = PROMPT.format(
        language=pack.bidder_language,
        source_language=pack.source_language,
        quote=label.quote,
        summary=label.summary,
    )
    drafted = await model.ainvoke([("human", prompt)])
    assert isinstance(drafted, DraftedQuestion)
    return drafted.question.strip()


async def _build(settings: Settings, pack: TenderPack, limit: int) -> Path:
    golden = load_golden(pack.directory(BACKEND_DIR) / "golden.yaml")
    labels = _sample(scored_labels(golden), limit)
    prefix = pack.name.upper()

    questions: list[RetrievalQuestion] = []
    for index, label in enumerate(labels, start=1):
        questions.append(
            RetrievalQuestion(
                id=f"{prefix}-Q-{index:03d}",
                label_id=label.id,
                question=await _draft(settings, pack, label),
                reference=label.summary,
                reference_contexts=(label.quote,),
                doc=label.doc,
                page=label.page,
            )
        )

    question_set = QuestionSet(
        meta=QuestionSetMeta(
            fixture_dir=pack.fixture_dir,
            source_language=pack.source_language,
            bidder_language=pack.bidder_language,
            derived_from="golden.yaml",
            generated_by=settings.runtime.models.cheap,
            generated_on=date.today(),
            state=VerificationState.DRAFT,
            method=(
                "Question wording drafted by the cheap model from each label's verbatim "
                "quote and its human-verified summary; the answer and the reference passage "
                "are the label's own fields, carried across untouched. Labels sampled "
                f"round-robin across the pack's documents with seed {SAMPLE_SEED}. "
                "A reviewer reads the `question` field only."
            ),
        ),
        questions=tuple(questions),
    )
    path = RETRIEVAL_DIR / f"{pack.name}.questions.yaml"
    dump_question_set(question_set, path)
    print(f"{pack.name}: {len(questions)} questions -> {path.relative_to(BACKEND_DIR)}")
    return path


async def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Draft a retrieval answer key. Costs cents.")
    parser.add_argument("packs", nargs="+", choices=sorted(PACKS))
    parser.add_argument("--per-tender", type=int, default=30)
    args = parser.parse_args(argv)
    try:
        settings = load_settings()
    except SettingsError as exc:
        print(f"settings: {exc}", file=sys.stderr)
        return INPUT_ERROR
    for name in args.packs:
        await _build(settings, PACKS[name], args.per_tender)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
