"""S7.1 — retrieval quality: did the agent find the passage that answers the question?

The extraction metrics (`recall.py`, `faithfulness.py`) score what the graph read out of a
pack. They say nothing about the half of the product a bidder actually drives: "ask the
tender", where a question goes to a ReAct agent that searches `tender_chunks` and answers
from what it finds. That path is the course brief's *agentic RAG* item, and until S7.1
nothing measured it — which is how `tender_chunks` went three increments with no writer at
all, answering "nothing found" to every question, well-formed and useless (ADR-0057).

**Four numbers, and they answer different questions.** Two need the answer key and two do
not, and the report keeps them apart because a suite of only the reference-free pair would
let a system that retrieves the wrong passage and answers it faithfully score perfectly:

- `context_recall` — of what the verified answer says, how much is supported by what was
  retrieved. The one metric that can say "retrieval missed it".
- `context_precision` — were the retrieved passages the relevant ones, ranked first.
- `faithfulness` — is the answer supported by what was retrieved, rather than by the model's
  own knowledge of German procurement law.
- `answer_relevancy` — does the answer address the question that was asked.

**The corpus is a throwaway Postgres, not Frankfurt** (`scripts/index_pack.py` says why), and
the answer key is derived from the human-verified golden labels (`questions.py` says why).

**Ragas was on the cut list and is back by an explicit decision** (roadmap.md; ADR to
follow). The judge is `google/gemini-2.5-flash-lite` through OpenRouter — a different vendor
from the models under test, which is S7.1's rule, and a tenth the price of the
`claude-haiku-4.5` the plan named.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from crossbid.eval.questions import QuestionSet, RetrievalQuestion
from crossbid.models.review import Citation

CONTEXT_RECALL: Final = "context_recall"
CONTEXT_PRECISION: Final = "context_precision"
FAITHFULNESS: Final = "faithfulness"
ANSWER_RELEVANCY: Final = "answer_relevancy"

METRIC_NAMES: Final = (CONTEXT_RECALL, CONTEXT_PRECISION, FAITHFULNESS, ANSWER_RELEVANCY)
"""Report order: what was retrieved, then what was done with it."""

REFERENCE_FREE: Final = frozenset({FAITHFULNESS, ANSWER_RELEVANCY})
"""The two that need no answer key, named so the report can say which half it is quoting
when a question set is still a draft."""


@dataclass(frozen=True)
class RetrievalSample:
    """One question put to the real chat agent, and everything it came back with."""

    question: RetrievalQuestion
    answer: str
    retrieved_contexts: tuple[str, ...]
    """Every passage the agent retrieved this turn, from the ledger — **not** only the ones
    it chose to cite. Precision and recall are about what retrieval returned; scoring only
    the cited subset would measure the model's citing discipline instead and would flatter
    a search that returned ten passages and used one."""
    citations: tuple[Citation, ...]

    @property
    def retrieved_nothing(self) -> bool:
        return not self.retrieved_contexts


@dataclass(frozen=True)
class QuestionScore:
    """One question's four numbers, or the subset that could be computed."""

    sample: RetrievalSample
    scores: Mapping[str, float]


@dataclass(frozen=True)
class RetrievalScore:
    """One tender's retrieval quality, and whether its answer key was checked by a person."""

    fixture_name: str
    question_set: QuestionSet
    scored: tuple[QuestionScore, ...]

    @property
    def verified(self) -> bool:
        """Whether a human signed off the questions. Printed beside every figure."""
        return self.question_set.meta.verified

    @property
    def answered(self) -> int:
        return sum(1 for score in self.scored if not score.sample.retrieved_nothing)

    def mean(self, metric: str) -> float | None:
        """The metric's mean over the questions it could be computed for.

        `None` rather than 0.0 when nothing could be computed: a metric the judge never
        returned and a metric that scored zero are different findings, and averaging the
        absent ones as zeros would quietly turn a broken judge into a bad retriever.
        """
        values = [score.scores[metric] for score in self.scored if metric in score.scores]
        return sum(values) / len(values) if values else None

    @property
    def means(self) -> dict[str, float | None]:
        return {metric: self.mean(metric) for metric in METRIC_NAMES}

    def worst(self, metric: str, limit: int = 5) -> tuple[QuestionScore, ...]:
        """The questions this metric scored lowest — the reviewer's list, as recall.py does."""
        scored = [score for score in self.scored if metric in score.scores]
        scored.sort(key=lambda score: score.scores[metric])
        return tuple(scored[:limit])


def contexts_of(samples: Sequence[RetrievalSample]) -> int:
    """Total passages retrieved across a tender — context for a precision figure."""
    return sum(len(sample.retrieved_contexts) for sample in samples)
