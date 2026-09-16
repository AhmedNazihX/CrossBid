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
import re
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
from crossbid.llm import chat_model, resilient  # noqa: E402
from crossbid.models.golden import GoldenRequirement, load_golden  # noqa: E402
from crossbid.settings import ModelRole, Settings, SettingsError, load_settings  # noqa: E402

RETRIEVAL_DIR = BACKEND_DIR / "tests" / "fixtures" / "retrieval"
LANGUAGE_NAMES = {"de": "German", "fr": "French", "en": "English"}
"""BCP-47 code to the name a model can act on.

Passing the code straight into a prompt is what "should be in de" looks like from the other
side, and a judge reading that concluded the requested language was English and rejected every
German question in the pack. A code is an identifier; a prompt needs a word.
"""


def language_name(code: str) -> str:
    return LANGUAGE_NAMES.get(code.lower(), code)


FUNCTION_WORDS = {
    "de": frozenset(
        [
            "der",
            "die",
            "das",
            "den",
            "dem",
            "und",
            "ist",
            "muss",
            "müssen",
            "welche",
            "welchen",
            "welcher",
            "wie",
        ]
    ),
    "fr": frozenset(
        [
            "le",
            "la",
            "les",
            "des",
            "est",
            "doit",
            "doivent",
            "quel",
            "quelle",
            "quels",
            "comment",
            "dans",
            "pour",
        ]
    ),
    "en": frozenset(
        [
            "the",
            "and",
            "what",
            "which",
            "how",
            "must",
            "is",
            "are",
            "for",
            "with",
            "does",
            "do",
            "of",
        ]
    ),
}
"""High-frequency function words, for telling the three languages apart.

**This is a rule and not a judge, deliberately.** Asked whether a German question was written
in German, `gemini-2.5-flash-lite` answered "no, the expected language is English" for every
question in the pack — it anchored on the word *English* in the surrounding prompt and could
not be talked out of it. Which language a sentence is in is decidable from its function words;
a model is the wrong instrument for it, exactly as it is the wrong instrument for whether a
quote appears on a page (ADR-0068). The judge keeps the semantic questions, which it is good
at.
"""


def looks_like(text: str, code: str) -> bool:
    """Whether `text` reads as the language `code` names, by function-word count."""
    words = set(re.findall(r"[a-zä-üß']+", text.casefold()))
    scores = {lang: len(words & vocabulary) for lang, vocabulary in FUNCTION_WORDS.items()}
    best = max(scores.values())
    return best > 0 and scores.get(code.lower(), 0) == best


OVERDRAW = 3
"""Labels sampled per question wanted. Headroom for the ones a check rejects."""

SAMPLE_SEED = 20260916
"""Fixed, so re-running this script proposes the same questions and a reviewer's work on a
previous draft is not thrown away by a reshuffle."""

INPUT_ERROR = 2

PROMPT = """You write the question a bidder would have asked.

You are given one requirement from a public tender: **what it demands**, in one line of
English, and the clause it was read from. Write the single question a bidder would type to find
that requirement.

**The English line is the answer your question must have.** Somebody holding only that line,
and not the clause, has to be able to answer your question completely. This is the rule that
matters: the question is graded against that line, so a question asking for anything the line
does not state — a number it does not give, a scope it does not name, who it applies to when it
does not say — is wrong, even when the clause happens to contain it.

The clause is there for one reason only: so you use the tender's own terminology. Do not ask
about anything in it that the English line leaves out.

Rules:
- Write the question in {language}, the bidder's language.
- Ask it the way a person reading the tender would ask it, not the way the document addresses
  them. "Welche Variante möchten Sie wählen?" is a field on a form; nobody types that.
- Do not restate the answer. A question containing its own answer measures nothing.
- One thing, phrased for a search box. Not a legal sub-clause.
- **Specific enough to pick out this requirement and no other.** "Welches Dokument ist
  erforderlich?" is answerable from the line above and useless: a tender demands dozens of
  documents and that question finds all of them. Name the subject — the insurance, the
  turnover, the deadline — even when the English line is short.
- No document names, page numbers, article numbers, or the word "tender".
- Return the question only: no preamble, no quotation marks.

What it demands (English — your question's answer):
{summary}

The clause it came from, for terminology only ({source_language}):
{quote}
"""

REDRAFT = """Your question was rejected. {reason}

Write a different question, in {language}, that somebody holding ONLY this English line could
answer completely, and which does not restate it:

{summary}
"""

CHECK = """Judge one entry of a retrieval answer key.

`answerable`: could somebody holding ONLY the English answer below answer the question
completely? If the question asks for a detail the answer does not state — a number, a scope,
who it applies to — say false.
`restates`: does the question already give away its own answer?
`specific`: does the question pick out THIS requirement, or would it equally find any
requirement of its kind? "Which document is required?" is not specific — a tender demands
dozens. Say false for a question that names no subject.
Be strict on the first and the third, lenient on the second: a question naturally shares
vocabulary with its subject.

Question (should be in {language}): {question}
The answer it is graded against (always English, by design): {summary}
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


ATTEMPTS = 4
RETRY_PAUSE_SECONDS = 3.0


async def _ask[T: BaseModel](model: object, prompt: str, expected: type[T]) -> T | None:
    """One structured call, retried past a provider that answers with no choices at all.

    `llm.resilient` handles a model that times out or refuses; it does not handle OpenRouter
    returning an error payload, because the OpenAI SDK's structured-output parser walks
    `choices` before anyone can inspect the body and raises `TypeError: 'NoneType' object is
    not iterable`. That is what a rate limit looks like from here, and on a ninety-question run
    it is common enough to lose the run. Retried with a pause; `None` when it never answers.
    """
    for attempt in range(ATTEMPTS):
        try:
            answer = await model.ainvoke([("human", prompt)])  # type: ignore[attr-defined]
        except (TypeError, ValueError) as exc:
            if attempt == ATTEMPTS - 1:
                print(f"    provider gave up: {type(exc).__name__}", flush=True)
                return None
            await asyncio.sleep(RETRY_PAUSE_SECONDS * (attempt + 1))
            continue
        assert isinstance(answer, expected)
        return answer
    return None


class Verdict(BaseModel):
    """The generator checking its own work before a person ever sees it."""

    answerable: bool = Field(description="Answerable from the English line alone?")
    restates: bool = Field(description="Does the question give away its own answer?")
    specific: bool = Field(
        description="Does it pick out this requirement rather than any of its type?"
    )
    reason: str = Field(description="One sentence")


async def _draft(settings: Settings, pack: TenderPack, label: GoldenRequirement) -> str | None:
    """One question, checked against its own answer — or `None` when the label cannot carry one.

    **Returning `None` is the point of the third axis.** Some verified labels summarise to a
    phrase so terse that no specific question can be answered from it alone: "A valid insurance
    certificate." admits nothing better than "Which document is required?", which would
    retrieve every document requirement in the pack. Shipping that weakens the metric silently.
    The label is skipped, the sampler draws another, and the skip is printed.


    **The check is the point, not the prompt.** The first version of this generator drafted
    from the clause and asked the model to behave; a human reviewer then found questions
    demanding specifics the reference never carried — the defect the metric is least able to
    survive, because `context_recall` scores retrieved passages against that reference. An
    instruction that is not verified is a hope. This verifies, with the judge, for a fraction
    of a cent per question.

    **Three axes, because closing the first one opened a third.** Constraining a question to be
    answerable from a terse summary pushes it towards vacuity: "A valid insurance certificate."
    admits no question more specific than "Which document is required?", which would retrieve
    every document requirement in the pack and discriminate nothing. So a draft must be
    answerable *and* specific *and* not a restatement, and a question that is merely answerable
    is rejected like any other.
    """
    # Wrapped like every other model call in this project (S3.4.4): a provider that rate-limits
    # or times out mid-way through ninety questions should cost a retry, not the run.
    writer = resilient(
        chat_model(ModelRole.CHEAP, settings).with_structured_output(DraftedQuestion),
        chat_model(ModelRole.FALLBACK, settings).with_structured_output(DraftedQuestion),
    )
    checker = resilient(
        chat_model(ModelRole.JUDGE, settings).with_structured_output(Verdict),
        chat_model(ModelRole.CHEAP, settings).with_structured_output(Verdict),
    )

    prompt = PROMPT.format(
        language=language_name(pack.bidder_language),
        source_language=language_name(pack.source_language),
        quote=label.quote,
        summary=label.summary,
    )
    question = ""
    verdict = None
    for attempt in range(2):
        drafted = await _ask(writer, prompt, DraftedQuestion)
        if drafted is None:
            continue
        question = drafted.question.strip()

        verdict = await _ask(
            checker,
            CHECK.format(
                question=question,
                summary=label.summary,
                language=language_name(pack.bidder_language),
            ),
            Verdict,
        )
        if verdict is None:
            continue
        if not looks_like(question, pack.bidder_language):
            if attempt == 0:
                prompt = REDRAFT.format(
                    reason=f"It was not written in {language_name(pack.bidder_language)}.",
                    language=language_name(pack.bidder_language),
                    summary=label.summary,
                )
                continue
            print(f"    skipped {label.id}: not in the bidder's language", flush=True)
            return None
        if verdict.answerable and verdict.specific and not verdict.restates:
            return question
        if attempt == 0:
            prompt = REDRAFT.format(
                reason=verdict.reason,
                language=language_name(pack.bidder_language),
                summary=label.summary,
            )
    why = verdict.reason if verdict is not None else "the provider never answered"
    print(f"    skipped {label.id}: {why}", flush=True)
    return None


async def _build(settings: Settings, pack: TenderPack, limit: int) -> Path:
    """`limit` questions that all passed the check, drawn from a wider sample.

    Over-drawn deliberately: a label that cannot carry a specific question is skipped rather
    than written down weakly, so the sample has to be bigger than the key. `OVERDRAW` is the
    headroom; if it runs out the file is short and says so on the way past.
    """
    golden = load_golden(pack.directory(BACKEND_DIR) / "golden.yaml")
    labels = _sample(scored_labels(golden), limit * OVERDRAW)
    prefix = pack.name.upper()

    questions: list[RetrievalQuestion] = []
    skipped = 0
    for label in labels:
        if len(questions) == limit:
            break
        drafted = await _draft(settings, pack, label)
        if drafted is None:
            skipped += 1
            continue
        questions.append(
            RetrievalQuestion(
                id=f"{prefix}-Q-{len(questions) + 1:03d}",
                label_id=label.id,
                question=drafted,
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
                "Each question is drafted from the label's human-verified English summary — "
                "the field the metric scores against — with the verbatim quote supplied for "
                "terminology only. The draft is then checked by "
                f"{settings.runtime.models.judge} on four axes: answerable from the summary "
                "alone, specific enough to pick out this requirement, not a restatement of "
                "its own answer, and in the bidder's language. A draft that fails is re-asked "
                "once and then the label is skipped. Labels sampled round-robin across the "
                f"pack's documents with seed {SAMPLE_SEED}. A reviewer reads the `question` "
                "field only."
            ),
        ),
        questions=tuple(questions),
    )
    path = RETRIEVAL_DIR / f"{pack.name}.questions.yaml"
    dump_question_set(question_set, path)
    short = "" if len(questions) == limit else f"  (wanted {limit}; the sample ran out)"
    print(
        f"{pack.name}: {len(questions)} questions, {skipped} label(s) skipped -> "
        f"{path.relative_to(BACKEND_DIR)}{short}"
    )
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
