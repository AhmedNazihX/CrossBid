# Crossbid

A cross-border EU tender go/no-go qualification agent for small and medium-sized businesses.

A German IT services company wants to bid for a French public contract. The tender is 190
pages of French procurement law, the buyer wants proof of things like *capacité économique et
financière*, and the company has no idea which German document answers which French
requirement. Crossbid reads the tender in its source language, extracts the requirements,
checks each one against the company's own documents, maps required proofs to their German
equivalents through the EU's eCertis database, and produces a compliance matrix with a
go/no-go recommendation — where **every cell carries a citation or is marked partially supported**.

It is **advisory only**. It never submits a bid, and a human reviews and confirms every
verdict before it is final.

## Status

**Increments 0 to 4 are complete: 17 of 17 stories in the last one.** Increment 5, the
submission evidence, is next. Nine migrations, sixty-two architectural decision records, 4 910
backend tests at 100 % line and branch coverage, and a clean `make lint` across both halves.
A further nine run against a real Postgres in CI, which is where the SQL is actually executed
rather than inspected as a string.

A bidder can sign in, describe their company, search TED and start a bid from a notice,
upload a pack that is scanned for planted instructions before anything is embedded, read
every extracted requirement with its citation and its translation, see each one checked
against their own documents, ask the tender questions and get cited answers, then review the
matrix row by row and confirm or override the verdict. An operator can see cost per bid and
per node and switch models, prompts and tools without a redeploy.

**One measured criterion is not met, deliberately in the open.** Requirement recall on the
German golden tender is **0.72** on the committed run and **about 0.74 ± 0.02** across four,
against a threshold of 0.90 set before anything had been measured.
`uv run scripts/recall.py tests/fixtures/extractions/de.live.json` reproduces it and exits
non-zero, and a test pins that red result so it cannot drift green unnoticed. Whether to
amend the threshold or spend more on extraction is an open decision, recorded rather than
hidden.

The **1.00** figure this section used to quote is the Increment 0 feasibility spike measured
against 21 hand-written requirements, not the verified 177-label answer key. See
[`docs/decisions.md`](docs/decisions.md) ADR-0003 for that result and its caveats, and
[`docs/project-plan.md`](docs/project-plan.md) for scope and build order.

## Quick start

Requirements: [Docker](https://docs.docker.com/get-docker/),
[uv](https://docs.astral.sh/uv/getting-started/installation/), Node 20+, and an
[OpenRouter API key](https://openrouter.ai/keys).

```bash
cp infra/.env.example .env      # then set OPENROUTER_API_KEY and APP_ENCRYPTION_KEY
make install                    # uv sync in backend/, npm install in frontend/
make dev                        # db + api + web in Docker
DATABASE_URL=postgresql://crossbid:crossbid@localhost:5432/crossbid make migrate
DATABASE_URL=postgresql://crossbid:crossbid@localhost:5432/crossbid make seed-dev  # prints the NEXT_PUBLIC_DEV_COMPANY_ID line to paste into .env
```

`make migrate` applies the schema in `backend/migrations/` from the host, so it needs the
Compose database's published port; the API creates LangGraph's own tables itself at startup.
To run against the hosted Supabase project instead, set `DATABASE_URL` in `.env` to its direct
connection string and run `make migrate` once with no prefix.

- Web app — http://localhost:3000
- API docs — http://localhost:8000/docs
- Health — http://localhost:8000/health

Generate `APP_ENCRYPTION_KEY` with:

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Tasks

Run `make help` for the full list.

| Command | What it does |
|---|---|
| `make dev` | Start db + api + web in Docker |
| `make dev-api` / `make dev-web` | Run one app on the host with reload |
| `make test` | Tests, excluding those marked `live`. Offline: no socket, no money |
| `make test-db` | Only the tests that need a real Postgres and spend nothing. CI runs these on every push |
| `make test-live` | Only the tests that hit real services or an LLM (costs money) |
| `make lint` | ruff, `ruff format --check`, pyright, eslint, prettier, `tsc --noEmit`, and the dependency-manifest check |
| `make deps` | Regenerate `dependencies.txt` from both lock files |
| `make migrate` | Apply `backend/migrations/*.sql` to `DATABASE_URL`; idempotent, refuses edited applied files |
| `make seed-dev` | Create the one dev `companies` row (idempotent, refused when `ENV=production`) and print the `NEXT_PUBLIC_DEV_COMPANY_ID` line to paste |
| `make eval` | Write `evaluations/REPORT.md` *(lands with S7.1)* |

`make eval` is wired and documented, and reports which story delivers it until it lands.

## Layout

```
backend/     FastAPI · Python 3.12 · uv · LangGraph      — own pyproject, Dockerfile, tests
frontend/    Next.js 15 · TypeScript · Tailwind          — own package.json, Dockerfile
infra/       Docker Compose, .env.example
scripts/     gen_dependencies.py
docs/        project plan, roadmap, ADRs, design canvas, demo runbook
             (architecture.md, the user guide and the critique land with Increment 5)
```

The two apps are separate processes on separate origins and share nothing but the OpenAPI
contract, from which `frontend/lib/api.ts` is generated. FastAPI owns all business logic,
database access, LLM calls, and secrets; the browser never sees an API key, a database
password, or a LangGraph checkpoint.

`dependencies.txt` is a generated manifest of every third-party package in both apps. Never
edit it by hand — run `make deps` after any dependency change. `make lint` fails on drift.

## How it works

The outer graph is a **deterministic workflow** with one human interrupt:

```
parse_docs → extract_reqs → check_reqs → score_verdict → [human review] → apply_review → finalize
```

The **agentic** part is inside `check_reqs`: it fans out one ReAct agent per requirement,
each free to choose among five tools — company document search, tender search, TED lookup,
eCertis evidence lookup, and currency conversion — to gather the evidence for its own row.
The verdict itself is rules-based, not model-generated: an unmet mandatory requirement or a
live exclusion ground yields `no_go` with the gap listed; `conditional` when open items remain, and `insufficient_evidence` when the documents do not settle enough rows to judge.

Data sources are public documented APIs only — TED, eCertis, and ECB rates via Frankfurter.
**Nothing is scraped.** Procurement documents live on national platforms behind portal pages,
so the bidder uploads them.

## Documentation

| File | What it covers |
|---|---|
| [`docs/project-plan.md`](docs/project-plan.md) | Scope, layout, epics → features → stories, build order, risks |
| [`docs/roadmap.md`](docs/roadmap.md) | Diagrams: folder tree, layer rules, sequence, dependencies, Gantt |
| [`docs/decisions.md`](docs/decisions.md) | ADRs — one per architectural decision, with the reasoning |
| [`project.md`](project.md) | Original product specification |
| [`135.md`](135.md) | Course brief this project answers |

## Licence and data

Tender fixtures under `backend/tests/fixtures/tenders/` are real public procurement documents,
committed with their provenance in each directory's `SOURCES.md`. They are published under EU
and national transparency rules; each file records where and when it was retrieved.
