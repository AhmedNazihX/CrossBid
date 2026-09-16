"""S7.1 — ask the judge which drafted questions a reviewer should not have to find by hand.

    uv run python scripts/review_questions.py de fr en

Writes `tests/fixtures/retrieval/<pack>.review.json`. Costs about a cent for all ninety: one
cheap judge call per question.

**Why a model and not a rule.** `crossbid/eval/questions.py` catches the two things a machine
can see — a question written in the form's own voice, and one that reuses the clause's wording.
The two defects that matter are semantic *and* cross-lingual: the question is in the bidder's
language and `reference` is one line of English, so no lexical measure can compare them. An
earlier attempt did exactly that and flagged 86 of 90 questions, which is the same as flagging
none.

The two it asks about, both found by a human reviewer on 2026-09-16 in questions the lexical
pass had not flagged:

- **`answerable`** — can the question be answered from the reference *alone*? The sharp case
  was a question asking whether **each member of a consortium** must sign, whose passage says
  so and whose reference does not. `context_recall` scores retrieved contexts against the
  reference, so a retriever that finds exactly the right passage is marked down. The reference
  is human-verified and is not the thing to change; the question is.
- **`restates`** — does the question already contain its own answer? Then retrieval against it
  measures nothing.

**This does not verify the key.** It narrows what a person reads from ninety to a handful.
`meta.state` is still set by a human, and `questions.py` still refuses to call a file verified
without a name and a date.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    # `[tool.uv] package = false`, so `crossbid` is importable only via the project root.
    sys.path.insert(0, str(BACKEND_DIR))

from pydantic import BaseModel, Field  # noqa: E402

from crossbid.eval.packrun import PACKS  # noqa: E402
from crossbid.eval.questions import (  # noqa: E402
    RetrievalQuestion,
    load_question_set,
    review_flags,
)
from crossbid.llm import chat_model  # noqa: E402
from crossbid.settings import ModelRole, Settings, SettingsError, load_settings  # noqa: E402

RETRIEVAL_DIR = BACKEND_DIR / "tests" / "fixtures" / "retrieval"
CONCURRENCY = 8
INPUT_ERROR = 2

PROMPT = """You are checking one entry of a retrieval answer key before a person signs it.

An entry is a question a bidder might ask about a public tender, a reference answer, and the
passage the answer came from. The question is in the bidder's language; the reference answer is
in English. That is expected and is not a defect.

Judge two things, and nothing else.

1. `answerable`: could somebody holding ONLY the reference answer answer this question? If the
   question asks for a detail the reference does not state — a number, a scope, who it applies
   to — the answer is false, EVEN IF the passage contains that detail. The reference is what
   the metric scores against.
2. `restates`: does the question already give away its own answer, so that anyone reading the
   question knows the answer without retrieving anything?

Be strict on 1 and lenient on 2: a question naturally shares vocabulary with its subject.

Question ({language}): {question}
Reference answer (English): {reference}
Passage ({source_language}): {passage}
"""


class Judgement(BaseModel):
    answerable: bool = Field(
        description="Can the question be answered from the reference alone?"
    )
    restates: bool = Field(description="Does the question give away its own answer?")
    reason: str = Field(description="One sentence, naming what is missing or restated")


async def _judge_one(
    model: object, meta: object, question: RetrievalQuestion, limit: asyncio.Semaphore
) -> dict[str, object]:
    """One question's verdict, under the concurrency bound."""
    async with limit:
        result = await model.ainvoke(  # type: ignore[attr-defined]
            [
                (
                    "human",
                    PROMPT.format(
                        language=meta.bidder_language,  # type: ignore[attr-defined]
                        source_language=meta.source_language,  # type: ignore[attr-defined]
                        question=question.question,
                        reference=question.reference,
                        passage=question.reference_contexts[0],
                    ),
                )
            ]
        )
    assert isinstance(result, Judgement)
    return {
        "id": question.id,
        "answerable": result.answerable,
        "restates": result.restates,
        "reason": result.reason,
        "mechanical": [flag.value for flag in review_flags(question)],
    }


async def _review_pack(model: object, name: str) -> int:
    question_set = load_question_set(RETRIEVAL_DIR / f"{name}.questions.yaml")
    limit = asyncio.Semaphore(CONCURRENCY)
    rows = list(
        await asyncio.gather(
            *(_judge_one(model, question_set.meta, q, limit) for q in question_set.questions)
        )
    )
    bad = [row for row in rows if not row["answerable"] or row["restates"]]
    path = RETRIEVAL_DIR / f"{name}.review.json"
    path.write_text(
        json.dumps({"reviewed": len(rows), "needs_a_look": bad}, indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    print(f"\n{name}: {len(bad)} of {len(rows)} need a look -> {path.name}")
    for row in bad:
        why = "not answerable from the reference" if not row["answerable"] else "restates"
        print(f"  {row['id']}: {why} — {str(row['reason'])[:120]}")
    return len(bad)


async def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Narrow a draft key to what needs a human.")
    parser.add_argument("packs", nargs="+", choices=sorted(PACKS))
    args = parser.parse_args(argv)
    try:
        settings: Settings = load_settings()
    except SettingsError as exc:
        print(f"settings: {exc}", file=sys.stderr)
        return INPUT_ERROR

    data = settings.model_dump()
    data["runtime"]["models"]["extract"] = settings.runtime.models.judge
    judge = chat_model(ModelRole.EXTRACT, Settings.model_validate(data))
    model = judge.with_structured_output(Judgement)
    print(f"reviewer: {settings.runtime.models.judge}")

    for name in args.packs:
        await _review_pack(model, name)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
