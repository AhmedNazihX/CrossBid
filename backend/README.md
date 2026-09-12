# Crossbid backend

FastAPI + LangGraph. Python 3.12, managed with [uv](https://docs.astral.sh/uv/).
Self-contained: nothing here needs the frontend's toolchain.

## Quick start

```bash
uv sync --extra dev          # create .venv and install
uv run uvicorn crossbid.main:app --reload
curl localhost:8000/health   # {"status":"ok","service":"crossbid-api"}
```

OpenAPI docs at http://localhost:8000/docs.

## Tasks

| Command | What it does |
|---|---|
| `uv sync --extra dev` | Install runtime + dev dependencies |
| `uv run ruff check . && uv run ruff format --check .` | Lint and format check |
| `uv run pyright` | Type check `crossbid/` |
| `uv run pytest` | Tests, excluding those marked `live` |
| `uv run pytest -m live` | Tests that hit real services or an LLM |

From the repository root, `make lint`, `make test`, `make dev` and `make deps` cover both apps.

## Configuration

`settings.default.yaml` holds model slugs, chunking and agent defaults. It is the only place a
model slug is written down. Secrets come from the environment — copy `infra/.env.example` to
`.env` at the repository root. `backend/.env` is read by the spike script and is gitignored.

Required once the corresponding stories land: `OPENROUTER_API_KEY`, `APP_ENCRYPTION_KEY`,
`DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`.

> **Connection pooling.** Use Supabase's *direct connection* locally and the *session pooler*
> in deployment. The transaction pooler does not support prepared statements and breaks the
> LangGraph checkpointer.

## Layout

Dependencies point one way, and nothing below imports from above:

```
routers / eval -> agent / ingestion / readmodel -> tools / reference / memory / guards -> models / db / settings
```

`eval/` sits on the top row beside `routers/` because it imports the agent, but nothing in a
request path imports it: it is the offline scoring half of S3.2.3, reached only from
`scripts/recall.py`, the `live` bid-run test and the S7.1 suite.

Folders appear as the stories that need them land (see `docs/project-plan.md`); today the
package holds only the app factory. `models/` never imports from elsewhere in `crossbid` — it
is the contract shared by routers, graph nodes, structured outputs, and the generated
TypeScript types.

## Evaluation

```bash
uv run scripts/recall.py                        # every result in tests/fixtures/extractions
uv run scripts/recall.py path/to/result.json    # one named result
```

Scores a saved extraction result against the golden answer key the result names, prints recall
on each tender's mandatory requirements and exits non-zero below
`evaluation.recall_threshold` in `settings.default.yaml` (S3.2.3). It runs no extraction —
`make test-live` does that and writes what it extracted to `tests/fixtures/extractions/`. The
results committed today are `source: synthetic`, built from the golden labels so the script
can be run offline, and every report says so.

The same run carries S6.4's human verification: per tender it lists the golden labels nothing
found, the extracted rows no label explains, the stage-filter leaks and the field
disagreements, which is what a reviewer adjudicates instead of re-reading 257 labels.

## Spike

`scripts/spike_extract.py` is the disposable SP.1 feasibility spike, with its results in
`scripts/spike_reports/`. It is excluded from linting, typing and coverage, and is deleted when
S3.2.1 lands. See ADR-0003.
