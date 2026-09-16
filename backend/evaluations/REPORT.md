# Crossbid — evaluation report

Generated 2026-09-16 by `scripts/run_eval.py` from saved measurements. Regenerating is offline and free; the measurements themselves are not — see the script's docstring for the commands that produce them.

Judge: `google/gemini-2.5-flash-lite` — a different vendor from every model under test, which is S7.1's rule.

## Headline

| Tender | Requirement recall | Gate | Citation faithfulness | Translation adequacy |
|---|---|---|---|---|
| DE | 0.831 (147/177) | FAIL | 1.0000 (311/311) | 0.903 (30/311 rows) |
| FR | 0.933 (28/30) | PASS | 1.0000 (114/114) | 0.830 (30/114 rows) |
| EN | 0.950 (38/40) | PASS | 1.0000 (201/201) | 0.967 (30/201 rows) |

Recall gate: **0.90**, from `evaluation.recall_threshold`.

## Retrieval (ragas, agentic RAG path)

| Tender | context recall | context precision | faithfulness | answer relevancy | Questions | Answer key |
|---|---|---|---|---|---|---|
| DE | 0.967 | 0.615 | 0.927 | 0.673 | 30 | verified |
| FR | 0.870 | 0.612 | 0.921 | 0.621 | 23 | verified |

## Reading the two weaker retrieval numbers

**Context precision is depressed by the agent searching more than once, not by bad retrieval.** `context_precision` assumes a single retrieval; a ReAct agent that is unsure searches again, and every passage from every search in the turn is pooled into one list. Each extra search adds five passages of which at most a few can be relevant, so the metric falls as the agent works harder.

| Tender | One search (≤5 passages) | Several (≥15 passages) |
|---|---|---|
| DE | 0.702 (21) | 0.099 (4) |
| FR | 0.690 (19) | 0.072 (3) |

**Answer relevancy penalises the agent for refusing to guess.** Its worst case here scores **0.00** on this answer: *"Die Bindefrist entspricht der Zuschlagsfrist … Die konkrete Dauer bzw. das konkrete Enddatum ist in den abgerufenen Passagen nicht genannt."* The agent declined to state a figure it had not retrieved, which is what `prompts/chat.md` requires of it. Ragas computes the metric by generating questions from the answer and comparing them with the original; an answer that declines to answer generates none, and there is no way for the metric to tell a refusal from an irrelevant reply. Longer answers also score slightly lower.

Neither observation makes the numbers wrong. Both mean the mean is the wrong thing to read alone.

## What the measurements cost

| Tender | Rows | Problems | Model calls priced | Cost | Wall clock | Source |
|---|---|---|---|---|---|---|
| DE | 311 | 0 | openai/gpt-5.6-terra | $1.6780 | 294 s | live_run 2026-09-16 |
| FR | 144 | 0 | openai/gpt-5.6-terra | $0.2962 | 71 s | live_run 2026-09-16 |
| EN | 201 | 1 | openai/gpt-5.6-terra | $1.2954 | 220 s | live_run 2026-09-16 |

Extraction total: **$3.27**.

## What this report does not measure

- retrieval: not measured for en.
