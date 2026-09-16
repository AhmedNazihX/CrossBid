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
| DE | 0.929 | 0.592 | 0.849 | 0.649 | 30 | draft key |
| FR | 0.800 | 0.546 | 0.930 | 0.583 | 30 | draft key |
| EN | 0.893 | 0.558 | 0.900 | 0.598 | 30 | draft key |

## What the measurements cost

| Tender | Rows | Problems | Model calls priced | Cost | Wall clock | Source |
|---|---|---|---|---|---|---|
| DE | 311 | 0 | openai/gpt-5.6-terra | $1.6780 | 294 s | live_run 2026-09-16 |
| FR | 144 | 0 | openai/gpt-5.6-terra | $0.2962 | 71 s | live_run 2026-09-16 |
| EN | 201 | 1 | openai/gpt-5.6-terra | $1.2954 | 220 s | live_run 2026-09-16 |

Extraction total: **$3.27**.
