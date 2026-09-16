"""S7.1 — score the collected retrieval samples with ragas, and print the four numbers.

    uv run python scripts/score_retrieval.py de fr en

Reads `tests/fixtures/retrieval/<pack>.samples.json` (written by `run_retrieval_eval.py`)
and writes `<pack>.scores.json` beside it. No database: the agent was already asked, and
re-asking it to compute a mean would spend money to learn nothing new.

**The judge is a different vendor from every model under test**, which is S7.1's rule.
Extraction and chat run on OpenAI slugs through OpenRouter; the judge is
`google/gemini-2.5-flash-lite`. The plan named `anthropic/claude-haiku-4.5` and that would
also satisfy the rule — flash-lite is ten times cheaper at $0.10/$0.40 against $1/$5, and
the judge is asked ninety times four.

**Two of the four metrics need the answer key and two do not.** If the key is still a draft,
that is printed against every reference-scored figure rather than hidden: `questions.py`
explains why a draft is a different claim, not a smaller one.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    # `[tool.uv] package = false`, so `crossbid` is importable only via the project root.
    sys.path.insert(0, str(BACKEND_DIR))

from openai import AsyncOpenAI  # noqa: E402
from ragas.embeddings.base import embedding_factory  # noqa: E402
from ragas.llms import llm_factory  # noqa: E402
from ragas.metrics.collections import (  # noqa: E402
    AnswerRelevancy,
    ContextPrecisionWithReference,
    ContextRecall,
    Faithfulness,
)

from crossbid.eval.packrun import PACKS, TenderPack  # noqa: E402
from crossbid.eval.questions import load_question_set  # noqa: E402
from crossbid.eval.retrieval import (  # noqa: E402
    ANSWER_RELEVANCY,
    CONTEXT_PRECISION,
    CONTEXT_RECALL,
    FAITHFULNESS,
    METRIC_NAMES,
)
from crossbid.settings import SettingsError, load_settings  # noqa: E402

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
RETRIEVAL_DIR = BACKEND_DIR / "tests" / "fixtures" / "retrieval"
INPUT_ERROR = 2


def _openrouter(api_key: str) -> AsyncOpenAI:
    """One client for both the judge and the embedder. OpenRouter is OpenAI-compatible on
    `/chat/completions` and on `/embeddings`, which is what lets ragas use it unchanged."""
    return AsyncOpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key)


def _judge(client: AsyncOpenAI, slug: str) -> object:
    return llm_factory(slug, provider="openai", client=client)


def _embedder(client: AsyncOpenAI, slug: str) -> object:
    """`AnswerRelevancy` needs embeddings: it re-asks the question from the answer and
    measures the cosine distance. The slug is the app's own `embed` role, so the metric
    embeds with the same model the corpus was indexed with."""
    return embedding_factory(provider="openai", model=slug, client=client)


async def _score_one(
    metrics: Mapping[str, object], sample: Mapping[str, object]
) -> dict[str, float]:
    """One sample's four numbers, skipping any the judge could not return.

    A metric that raises is dropped rather than recorded as zero: `RetrievalScore.mean`
    averages what exists, because a judge that failed and a retriever that missed are
    different findings and must not average into the same figure.
    """
    question = str(sample["question"])
    answer = str(sample["answer"])
    contexts = [str(text) for text in sample["retrieved_contexts"]]  # type: ignore[union-attr]
    reference = str(sample["reference"])
    if not contexts:
        return {}

    scores: dict[str, float] = {}
    referenced = {
        "user_input": question,
        "retrieved_contexts": contexts,
        "reference": reference,
    }
    generated = {
        "user_input": question,
        "response": answer,
        "retrieved_contexts": contexts,
    }
    calls = {
        CONTEXT_RECALL: referenced,
        CONTEXT_PRECISION: referenced,
        FAITHFULNESS: generated,
        # No `retrieved_contexts`: answer relevancy asks whether the answer addresses the
        # question, which is the one metric here that does not look at the corpus at all.
        ANSWER_RELEVANCY: {"user_input": question, "response": answer},
    }
    for name, kwargs in calls.items():
        try:
            result = await metrics[name].ascore(**kwargs)  # type: ignore[attr-defined]
        except Exception as exc:  # one bad sample must not lose the tender
            print(f"    {sample['id']} {name}: {type(exc).__name__}", file=sys.stderr)
            continue
        scores[name] = float(result.value)
    return scores


def _mean(scored: Sequence[Mapping[str, object]], metric: str) -> float | None:
    """The metric's mean over the samples it was computed for, or `None` for none of them.

    `None` rather than 0.0: a judge that never answered and a retriever that missed every
    passage are different findings, and averaging absent scores as zeros would print the
    first as the second.
    """
    values = [
        float(entry["scores"][metric])  # type: ignore[index]
        for entry in scored
        if metric in entry["scores"]  # type: ignore[operator]
    ]
    return sum(values) / len(values) if values else None


CONCURRENCY: Final = 8
"""Samples judged at once.

Four metrics over ninety questions, and each metric decomposes into several judge calls --
`Faithfulness` splits the answer into statements and verifies each, `AnswerRelevancy`
generates questions back from the answer. Run one sample at a time that is hours of wall
clock for a number nobody is waiting on interactively. Eight at a time is minutes, and is
well inside what OpenRouter serves without rate-limiting this account; the bound exists
because unbounded `gather` over ninety samples opens a few hundred concurrent requests and
gets throttled, which is slower than doing it properly.
"""


async def _score_pack(pack: TenderPack, metrics: Mapping[str, object]) -> Path:
    samples_path = RETRIEVAL_DIR / f"{pack.name}.samples.json"
    document = json.loads(samples_path.read_text(encoding="utf-8"))
    question_set = load_question_set(RETRIEVAL_DIR / f"{pack.name}.questions.yaml")

    limit = asyncio.Semaphore(CONCURRENCY)

    async def judge(sample: Mapping[str, object]) -> dict[str, object]:
        async with limit:
            scores = await _score_one(metrics, sample)
        line = ", ".join(f"{k}={v:.2f}" for k, v in scores.items()) or "nothing retrieved"
        print(f"  {sample['id']}: {line}", flush=True)
        return {"id": sample["id"], "scores": scores}

    scored = list(await asyncio.gather(*(judge(s) for s in document["samples"])))

    means = {name: _mean(scored, name) for name in METRIC_NAMES}
    path = RETRIEVAL_DIR / f"{pack.name}.scores.json"
    path.write_text(
        json.dumps(
            {
                "fixture_dir": pack.fixture_dir,
                "key_state": question_set.meta.state.value,
                "key_verified": question_set.meta.verified,
                "questions": len(scored),
                "means": means,
                "per_question": scored,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    printable = ", ".join(
        f"{name}={value:.3f}" if value is not None else f"{name}=n/a"
        for name, value in means.items()
    )
    flag = "" if question_set.meta.verified else "   [KEY IS A DRAFT]"
    print(f"{pack.name}: {printable}{flag}")
    return path


async def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score retrieval samples with ragas.")
    parser.add_argument("packs", nargs="+", choices=sorted(PACKS))
    args = parser.parse_args(argv)
    try:
        settings = load_settings()
    except SettingsError as exc:
        print(f"settings: {exc}", file=sys.stderr)
        return INPUT_ERROR

    slug = settings.runtime.models.judge
    client = _openrouter(settings.env.openrouter_api_key.get_secret_value())
    judge = _judge(client, slug)
    embedder = _embedder(client, settings.runtime.models.embed)
    print(f"judge: {slug}   embeddings: {settings.runtime.models.embed}")
    metrics = {
        CONTEXT_RECALL: ContextRecall(llm=judge),
        CONTEXT_PRECISION: ContextPrecisionWithReference(llm=judge),
        FAITHFULNESS: Faithfulness(llm=judge),
        ANSWER_RELEVANCY: AnswerRelevancy(llm=judge, embeddings=embedder),
    }
    for name in args.packs:
        print(f"scoring {name} …", flush=True)
        await _score_pack(PACKS[name], metrics)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
