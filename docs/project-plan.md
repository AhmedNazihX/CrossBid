# Crossbid — project plan (Epics → Features → Stories)

> Status: **approved 2026-09-10, re-sequenced after PM review the same day, implementation not started**. Source of truth for scope, layout, and build order. Scope is unchanged from the approval; the PM review changed only ordering, acceptance criteria, and added the Spike, CI, recall-script stories, the Risks table, and the graded-coverage table. Supersedes `project.md` §8; `project.md` §2–§5 will be trimmed to match at the start of E0. **Amended 2026-09-10 after Increment 0** — R2 and R3 in the Risks table and the embeddings bullet above were corrected against what the fixture download and the live endpoint probes actually showed (ADR-0001, ADR-0004). Scope is still unchanged. Decisions come from the 41-question grill session of 2026-09-10.

## Context

Sprint capstone (brief in `135.md`): build a useful AI agent with LangGraph, OpenAI, and Next.js. The project is **Crossbid**, a cross-border EU tender go/no-go agent for SMEs (spec in `project.md`). A grill session on 2026-09-10 settled 41 scope and design questions and verified the external dependencies live. This plan replaces the delivery plan in `project.md` §8 and narrows §2–§4 to the agreed vertical slice. Time is not a hard constraint (user's Q1), so the extra time goes into quality of the slice, not breadth.

**Vertical slice:** a fictional German IT GmbH uploads its document pack, picks a TED notice (DE or FR), uploads the tender documents, and gets a bilingual compliance matrix and a rules-based go/no-go verdict that a human reviews and confirms in a Next.js workspace. Plus "ask the tender" chat.

## Settled decisions (from the grill; do not reopen)

**Cut from course build:** response drafting, second interrupt, DOCX export, OCR, `next-intl`, PDF quote highlighting (jump-to-page only), APScheduler, `deadline_calculator`, `web_search_buyer`, Ragas, RLS-as-isolation claim, feedback few-shot injection, Polish/Dutch tenders, LLM profile extraction, numeric verdict score.

**Kept / decided:**
- Intake = TED notice via API (structured fields, no LLM) + manual upload of procurement documents. TED `document-url-lot` links land on national platforms; never fetch them (no scraping).
- eCertis is criterion-centric: tool is `ecertis_evidence_lookup(criterion_id, bidder_country)`. EU criteria list and DE/FR evidences cached as JSON in repo.
- Five tools: `company_rag_search`, `tender_rag_search`, `search_ted`, `ecertis_evidence_lookup`, `currency_convert` (Frankfurter). Tool registry with manifests + enable/disable toggles.
- LLM access: **OpenRouter is the single provider** (the only key the user holds). Default slugs `openai/gpt-5.6-terra` for extraction/translation and `openai/gpt-5.6-luna` for classification, chat, and the injection guard. Verified 2026-09-10: both expose `structured_outputs`, `response_format`, `tools` through OpenRouter at the same prices as OpenAI direct ($2/$12 and $0.20/$1.20 per 1M). Multi-model has two layers: (1) switching vendor slugs inside OpenRouter from the dev panel — the three vendors usable on this account are `openai/gpt-5.6-*`, `anthropic/claude-haiku-4.5` and `google/gemini-2.5-flash`(`-lite`); `claude-sonnet-5` is 404 here, see ADR-0005; (2) **bring your own key**: a user can store their own OpenAI and/or Anthropic key (or their own OpenRouter key) in Settings and pick which provider their company's bids run through. Keys are encrypted at rest (Fernet, `APP_ENCRYPTION_KEY`), scoped by `company_id`, verified with a one-token test call on save, never returned to the client (last-4 hint only), never logged. Embeddings always run through the app's OpenRouter route so a company's corpus stays in one vector space. Slugs and per-provider role defaults live in one settings file.
- Extraction: map over page-tagged sections (5–8 pages) with structured output, dedupe pass. Extractor assigns nullable `ecertis_criterion_id` from the ~56 EU criteria enum.
- `check_reqs`: LangGraph `Send` fan-out per requirement, concurrency ~5, max 4 tool calls each, returns `MatrixRow`. This is the agentic (ReAct) part; outer graph is a deterministic workflow with one interrupt.
- Verdict: rules only. Unmet mandatory or exclusion ground ⇒ `no_go` with gap list; else `conditional` or `go`. **Extended 2026-09-10 (ADR-0006):** the FR fixture scores selection on a 10-point scale with numeric bands and eliminates below 5/10, so the scorer must also handle a weighted threshold, not only pass/fail minima. This is a rules change, not a return to the numeric verdict score that was cut — the weights are the buyer's, published in the tender. *(vocabulary amended 2026-09-11, ADR-0013)*
- Interrupt/resume: `interrupt()` with matrix+verdict; `Command(resume={row_edits, decision})` → apply edits → re-run scorer → record override if reviewer disagrees → END.
- Persistence: `PostgresSaver` + `PostgresStore` (pgvector) on Supabase EU; **direct connection locally, session pooler in deployment, never transaction pooler**. App read-model tables written after `score_verdict` and after resume.
- Storage: Supabase Storage bucket, prefix per company, signed URLs. Chunks 800 tokens/100 overlap, embeddings via OpenRouter's `/embeddings` endpoint. **Default `openai/text-embedding-3-small` (1536 dims, ~$0.027/1M)**, changed from 3-large on 2026-09-10 while nothing was yet embedded (ADR-0004): 1536 dims sits under pgvector's 2000-dim index cap, so HNSW/IVFFlat are available. `openai/text-embedding-3-large` (3072 dims, $0.13/1M) stays as the quality switch and `qwen/qwen3-embedding-8b` (4096 dims, ~$0.057/1M) as the non-OpenAI multilingual option; `baai/bge-m3` is dropped — HTTP 404 on this account's data policy. Changing the slug means re-embedding and a column dimension change, so S7.1 measures the choice rather than reopening it. Vector-only retrieval.
- Parsing: `pymupdf4llm` default; Docling (`do_ocr=False`) behind the same `Parser` interface, switchable. Pages with no text flagged "not read".
- Guards: regex/heuristic scan on every chunk → flagged chunks to luna yes/no → excluded and listed to reviewer; document text wrapped in delimited data blocks; `slowapi` rate limit on bid creation; schema validation on tool outputs; scorer refuses `go` without evidence on mandatory rows.
- Auth: Supabase Auth magic link, JWT verified in FastAPI, single company per user. Developer role = env-var email list. `/dev` route gated on both sides.
- Frontend calls FastAPI directly with bearer token; CORS locked; TS types via `openapi-typescript`; poll `/bids/{id}` every 2 s.
- "Ask the tender": separate thread `bid:{id}:chat`, ReAct agent with `tender_rag_search`, `company_rag_search`, `get_matrix`.
- Tenant isolation: application-level `company_id` on every query and Store namespace.
- Observability: LangSmith for traces. Cost figures come from OpenRouter's per-generation usage accounting (`usage: {include: true}` returns cost in the response), not from LangSmith price tables, so any vendor slug is priced correctly. Eval: DeepEval only (GEval faithfulness + translation adequacy, custom recall metric) with the judge wired to OpenRouter through DeepEval's OpenAI-compatible custom model. **Judge is `anthropic/claude-haiku-4.5`** (ADR-0005), not `claude-sonnet-5`, which 404s on this account; it still satisfies S7.1's rule that the judge come from a different vendor than the models under test. Golden set: 3 tenders (DE, FR, EN), LLM-assisted labels hand-verified.
- Per-user `language` (default `de` for demo) and `tone` settings applied to explanations and chat. UI chrome English.
- Fixtures: real DE and FR tender packs committed under `backend/tests/fixtures/tenders/{de,fr}/` with `SOURCES.md`; <15 MB each.
- Deployment: Docker Compose first; Vercel + Railway/Fly EU + Supabase EU only at the end.

---

## Repository layout

Two top-level folders, `backend/` and `frontend/`, each a self-contained project with its own dependency file, Dockerfile, tests, and deploy target. No shared package, no monorepo tooling. The Pydantic models in the backend are the single schema source; the frontend consumes them as generated TypeScript types. Inside the API, folders are layered so that dependencies point one way: `routers/eval → agent/ingestion/readmodel → tools/reference/memory/guards → models/db/settings`. Nothing below imports from above. `eval/` (S3.2.3) sits beside `routers/` rather than under it: it imports the agent — reusing `extract_reqs`' own quote matcher and stage filter so a score cannot drift from the extractor — and nothing in a request path imports it.

```
/
├── backend/                          FastAPI · Python 3.12 · uv        — its own pyproject, venv, Dockerfile, tests
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── settings.default.yaml         OpenRouter slugs per role (extract, cheap, embed), temperature, max tokens, enabled tools, system prompt
│   ├── crossbid/                     the Python package
│   │   ├── main.py                   app factory: CORS, slowapi, routers, startup (.setup() for checkpointer/store)
│   │   ├── llm.py                    chat-model factory: resolve(company, role) → company's active provider (own OpenAI / Anthropic / OpenRouter key) or app OpenRouter default
│   │   ├── settings.py               pydantic-settings (env) + yaml defaults + app_settings row → one Settings object
│   │   ├── auth.py                   Supabase JWT verification; deps current_user, current_company, is_developer
│   │   ├── crypto.py                 Fernet encrypt/decrypt for stored provider keys (APP_ENCRYPTION_KEY)
│   │   ├── db.py                     psycopg pool (autocommit, dict_row); PostgresSaver / PostgresStore factories
│   │   ├── models/                   Pydantic v2 schemas and enums — shared by routers, graph nodes, structured outputs
│   │   │   ├── requirement.py        Requirement, RequirementCategory, RequirementKind
│   │   │   ├── matrix.py             MatrixRow, RowStatus, Evidence, EcertisEvidence
│   │   │   ├── verdict.py            Verdict, Decision
│   │   │   ├── company.py            CompanyProfile, CertificateHeld
│   │   │   ├── tender.py             TedNotice, BidSummary
│   │   │   ├── review.py             ReviewSubmission, RowEdit, ChatTurn
│   │   │   └── provider.py           Provider enum, ProviderKeyStatus (provider, hint, verified_at), ProviderSelection
│   │   ├── agent/                    everything LangGraph
│   │   │   ├── state.py              BidState (TypedDict) and CheckState (per-requirement Send payload)
│   │   │   ├── graph.py              build_graph(): parse_docs → extract_reqs → check_reqs → score_verdict → interrupt → apply_review → finalize
│   │   │   ├── chat_graph.py         ask-the-tender ReAct agent (separate thread bid:{id}:chat)
│   │   │   ├── nodes/                one module per node; pure functions of (state, config) → partial state
│   │   │   ├── tools/                registry.py + one module per tool; each exports `tool` and `MANIFEST`
│   │   │   └── prompts/              versioned .md prompts: extract, check, explain, chat, guard
│   │   ├── ingestion/                documents in → chunks + embeddings out
│   │   │   ├── parser.py             Parser protocol, ParsedDocument(pages, unread_pages)
│   │   │   ├── pymupdf_parser.py     default
│   │   │   ├── docling_parser.py     switchable, do_ocr=False
│   │   │   ├── chunker.py            800/100 page-tagged chunks
│   │   │   ├── embeddings.py         OpenRouter embeddings client (text-embedding-3-small default, ADR-0004) + pgvector insert/search scoped by company/bid
│   │   │   ├── storage.py            Supabase Storage upload + signed URLs
│   │   │   └── ted_client.py         TED v3 expert-query builder, search, notice PDF download
│   │   ├── reference/                read-only external reference data
│   │   │   ├── ecertis_client.py     REST client (build time) + cache loader (run time)
│   │   │   ├── frankfurter.py        ECB rates
│   │   │   └── data/ecertis/         criteria.json, evidence_de.json, evidence_fr.json (generated, committed)
│   │   ├── memory/                   LangGraph Store namespaces: profile/{company_id}, corrections/{company_id}
│   │   ├── guards/                   injection.py (heuristics + luna), wrap.py (data-block delimiting)
│   │   ├── readmodel/                SQL + writers for bids, requirements, matrix_rows, reviews (dashboard reads these, never checkpoints)
│   │   └── routers/                  thin HTTP layer: companies, documents, tenders, bids, review, chat, provider_keys, dev_settings, feedback
│   ├── migrations/                   plain SQL, numbered; applied by `uv run scripts/migrate.py`
│   ├── scripts/                      migrate.py, build_ecertis_cache.py, seed_demo_company.py, run_eval.py
│   ├── evaluations/                  golden/{de,fr,en}.yaml, deepeval suite, REPORT.md
│   └── tests/
│       ├── unit/                     fakes for LLM (GenericFakeChatModel), TED, eCertis, Frankfurter
│       ├── integration/              marked `live`; full graph on the DE fixture up to the interrupt
│       └── fixtures/
│           ├── tenders/{de,fr,en}/   real TED packs + SOURCES.md
│           ├── company/              demo GmbH document pack + profile.yaml
│           └── adversarial/          injection PDFs
├── frontend/                         Next.js 15 App Router · TypeScript · Tailwind · the CrossBid design system (ADR-0014; Radix for behaviour) — its own package.json, Dockerfile
│   ├── package.json
│   ├── Dockerfile
│   ├── app/
│   │   ├── (auth)/login/             magic link
│   │   ├── (app)/                    authenticated shell
│   │   │   ├── dashboard/
│   │   │   ├── company/              profile form, document upload
│   │   │   ├── settings/             AI provider: active provider radio, add/replace/remove OpenAI · Anthropic · OpenRouter key, test button, language, tone
│   │   │   ├── bids/new/             TED search → pick notice → upload → start
│   │   │   └── bids/[id]/            workspace (pdf left, matrix right), chat/
│   │   └── dev/                      settings, tool toggles, costs — gated by is_developer
│   ├── components/                   matrix/, pdf/, verdict/, landing/, ui/ (design-system primitives; shadcn removed 2026-09-11)
│   └── lib/                          api.ts (generated by openapi-typescript), supabase.ts, polling hook
├── infra/
│   ├── docker-compose.yml            postgres+pgvector, api, web
│   └── .env.example
├── scripts/
│   └── gen_dependencies.py           reads backend/uv.lock + frontend/package-lock.json → dependencies.txt
├── Makefile                          dev · test · lint (runs deps-check) · deps · migrate · eval
├── dependencies.txt                  generated manifest of every third-party package, both apps; never hand-edited
├── docs/
│   ├── project-plan.md               this file
│   ├── architecture.md               graph diagram, agent-vs-workflow explanation
│   ├── decisions.md                  ADRs, one per settled decision
│   ├── user-guide.md                 three worked examples
│   └── critique.md                   LLM critique and fixes (Easy 1)
├── 135.md                            course brief
├── project.md                        product spec (trimmed to match this plan after approval)
├── CLAUDE.md
└── README.md                         quick start
```

**How a bid flows through the folders.** `routers/bids.py` receives the notice number and document ids, starts `agent/graph.py` in a background task with `thread_id = bid:{id}`. `nodes/parse_docs.py` calls `ingestion/` to load chunks. `nodes/extract_reqs.py` uses `prompts/extract.md`, `guards/wrap.py`, and the criterion enum from `reference/data/ecertis`. `nodes/check_reqs.py` fans out with `Send`, each sub-run binding the tools that `tools/registry.py` says are enabled. `nodes/score_verdict.py` is pure rules plus one explanation call, then `readmodel/` writes the snapshot and the graph hits `interrupt()`. `routers/review.py` resumes with `Command`, `nodes/apply_review.py` re-scores, `readmodel/` writes the final state. The web app never sees a checkpoint; it reads `readmodel` tables through the routers and polls `GET /bids/{id}`.

**Rules that keep it clean.**
- `models/` has no imports from anywhere else in `crossbid`. It is the contract for routers, nodes, structured outputs, and the generated TS types.
- Nodes never open HTTP connections or run SQL directly; they call `ingestion/`, `reference/`, `memory/`, `readmodel/`.
- Tools are the only place the LLM touches the outside world. Every tool validates its output against a Pydantic schema before returning.
- `reference/data/` is generated by a script and committed, so tests and the demo never hit eCertis live.
- `readmodel/` is a projection. If it and the checkpoint disagree, the checkpoint is right and the writer has a bug.
- `frontend/lib/api.ts` is generated, never edited by hand. Run the generator whenever a Pydantic model changes.

## Frontend ↔ backend boundary, and Supabase's role

**Segregation.** Two processes on two origins. The Next.js app renders UI and holds the user's session token. FastAPI owns all business logic, database access, LLM calls, and secrets. The browser never sees the OpenRouter key, a database password, or a checkpoint. The only thing the two share is the OpenAPI contract, which generates `frontend/lib/api.ts`.

**Interaction.**
1. Login: the browser talks to Supabase Auth (magic link) and receives a JWT. No password code in our repo.
2. Every API call carries `Authorization: Bearer <jwt>`. FastAPI verifies the signature against Supabase's public keys (JWKS), reads the user id, loads the user's company. CORS allows only the web origin.
3. Long runs: `POST /bids` returns 202 with the bid id and starts the graph in a background task. The browser polls `GET /bids/{id}` every 2 s. When status is `awaiting_review` it renders the matrix. `POST /bids/{id}/review` resumes the graph.
4. Files: the browser uploads PDFs to FastAPI (multipart). FastAPI parses, chunks, embeds, and stores the original in Supabase Storage. The viewer asks the API for a short-lived signed URL and loads the PDF straight from Storage.
5. Chat: `POST /bids/{id}/chat` returns the answer with citations; no streaming in v1.

**What Supabase is.** Hosted Postgres plus three services we use: **Auth** (users, magic-link email, JWT issuing), **Storage** (S3-style object store with signed URLs), and the **pgvector** extension. It has an EU region, a free tier, connection poolers, and a dashboard. Open source; nothing in our code is Supabase-specific except the JWKS URL and the Storage client.

**Its role here.**
- **The one database**: app read-model tables, `company_chunks` / `tender_chunks` embeddings, LangGraph checkpoints, and the LangGraph Store all live in the same Postgres. One DSN, one backup, one region.
- **Auth**: issues the JWT the frontend sends and the backend verifies.
- **Storage**: holds every uploaded PDF under a `company_id` prefix.

**What we deliberately do not use.** No `supabase-js` data access from the browser (all data goes through FastAPI), no RLS as the isolation mechanism (application-level `company_id` filtering instead), no Edge Functions, no Realtime. Keeping Supabase to "Postgres + Auth + Storage" means the backend could move to any Postgres later by swapping the auth verifier and the storage client.

**Environments.** Dev and demo point at one hosted Supabase EU project (direct connection locally). The Docker Compose Postgres with pgvector is for tests and offline work; Auth and Storage are not mocked locally, tests use fakes.

## Data model and API surface

**Read-model tables (Postgres, written by the API; LangGraph tables are created separately by `.setup()`).**
- `companies(id, owner_user_id, name, country, legal_form, language, tone, active_provider enum default 'openrouter_app', profile jsonb)`
- `provider_keys(company_id, provider enum(openai, anthropic, openrouter), encrypted_key bytea, key_hint text, verified_at, created_at, PK(company_id, provider))`
- `documents(id, company_id, bid_id nullable, kind enum, storage_path, pages, unread_pages int[], flagged_chunks int[], expiry date nullable)`
- `company_chunks` / `tender_chunks(id, document_id, company_id, bid_id, page, text, embedding vector(1536))` — 1536 for `text-embedding-3-small` (ADR-0004); an HNSW index is possible because this is under pgvector's 2000-dim cap
- `bids(id, company_id, ted_publication_number, title, buyer, source_language, deadline, thread_id, status enum, verdict jsonb, provider_used text)`
- `requirements(id, bid_id, category, kind, source_text, source_lang, page, translation, ecertis_criterion_id, deadline)`
- `matrix_rows(id, requirement_id, status, evidence jsonb, ecertis_evidence jsonb, agent_rationale, reviewer_status, override_reason, attached_doc_ids, reviewed_at)`
- `reviews(id, bid_id, decision, agent_verdict, final_verdict, override_reason, reviewer_id, created_at)`
- `feedback(id, matrix_row_id nullable, bid_id, rating, comment)`
- `llm_usage(id, bid_id, node, provider, model, input_tokens, output_tokens, cost_usd, created_at)`
- `app_settings(id=1, models jsonb, temperature, max_tokens, system_prompt, enabled_tools text[])`

**Endpoints (all under the Supabase JWT; `/dev/*` additionally requires `is_developer`).**
- Companies: `POST /companies`, `GET /companies/me`, `PUT /companies/me` (language, tone)
- Provider keys (BYOK): `GET /settings/providers` (configured providers with last-4 hint and verified_at, active provider), `PUT /settings/providers/{provider}` (stores the key only after a one-token verification call), `DELETE /settings/providers/{provider}`, `PUT /settings/providers/active`
- Documents: `POST /documents` (multipart → storage → parse → chunk → guard → embed, background), `GET /documents/{id}`, `GET /documents/{id}/url` (signed)
- Tenders: `GET /tenders/search` (TED proxy)
- Bids: `POST /bids` (202, starts graph), `GET /bids`, `GET /bids/{id}` (status, requirements, matrix, verdict, unread pages, flagged chunks, provider_used), `POST /bids/{id}/review` (row edits + decision → resume), `POST /bids/{id}/chat`
- Feedback: `POST /feedback`
- Developer: `GET/PUT /dev/settings`, `GET /dev/costs`

---

## Project plan: Epics → Features → Stories

**Conventions.** An *epic* states an outcome, why it matters, and an observable "done when". A *feature* is a capability plus the benefit it delivers. A *story* is written from the person who benefits (*As a …, I want …, so that …*), followed by acceptance criteria in Given / When / Then form, a size, and hard prerequisites (`needs`). Implementation pointers sit in *Notes* so the story itself stays about behaviour. Sizes: **S** about 1 h, **M** 1–3 h, **L** 3–6 h (the roadmap uses the same scale). Priority is **Must** unless a story is tagged **Could**; Could stories sit in Increment 6 of the Delivery order and are never scheduled ahead of grader evidence.

**Personas.**
- **Bidder** — Sabine, owner and sales lead of a 25-person German IT services GmbH. Bids domestically, wants to bid in France. Not a procurement professional; reads German and some English, no French.
- **Reviewer** — the person who confirms or overrides the agent's verdict. In v1 this is Sabine or a colleague; the role is kept separate because the review step is the product's safety boundary.
- **Operator** — whoever runs the deployment and tunes models, tools, and prompts in the developer panel.
- **Maintainer** — the team building Crossbid. Used only for enabler stories that have no end-user surface of their own.

---

### SP · Spike: extraction feasibility — Increment 0, before E0

**Goal.** Know whether the core bet holds before building infrastructure around it.
**Why.** The product rests on one assumption: an LLM can extract the requirements of a real 100-page DE or FR tender with recall ≥ 0.9, and cross-lingual retrieval finds the German evidence. Every later epic assumes this, and nothing else in the plan tests it before Milestone 3.
**Done when.** A disposable script has run extraction and one round of checking on the DE fixture, a rough recall figure is recorded in `docs/decisions.md`, and a go or pivot decision is written next to it.

- **SP.1** (M) *As a maintainer, I want a script that runs extraction and checking on the DE fixture without database, auth, or UI, so that the recall target is tested before any infrastructure exists.* `needs S6.1 (DE pack only)`
  - Given the DE fixture and 20 hand-picked mandatory requirements, when the script runs with PyMuPDF, 5–8 page sections, structured output, and in-memory embeddings, then it prints found / missed per requirement and a recall figure.
  - Given recall ≥ 0.7 after at most two prompt iterations, then Increment 1 starts as planned and the figure is recorded in an ADR.
  - Given recall < 0.7 after two iterations, then section size, chunking, and model slug are revisited and an ADR records the change before Increment 1 starts.
  - Given the script, then it lives in `backend/scripts/spike_extract.py`, is excluded from coverage, and is deleted when S3.2.1 lands.
  - Notes: no tests, no checkpointer, no Storage. Deliberately disposable; its only output is the number and the decision.

---

### E0 · Foundations — lane tag A · gate for Increment 1

**Goal.** A running skeleton in which a signed-in user reaches an authenticated API backed by Postgres with LangGraph persistence.
**Why.** Everything builds on it, and the API contract (F0.4) lets frontend stories be coded against typed stubs before the backend logic exists.
**Done when.** `docker compose up` starts API, web, and database; a magic-link login yields a token accepted by `GET /companies/me`; an empty graph run leaves a checkpoint that survives a restart; `frontend/lib/api.ts` is generated from the live OpenAPI schema.
**Order.** F0.1, F0.2, S0.3.2, S0.3.3, and F0.4 are Increment 1. S0.3.1 (magic-link auth) is Increment 4; until it lands the API runs in dev auth mode (see S0.3.1 Notes), so the gate is thinner than the epic.

**F0.1 Repository and tooling** — each app starts and tests with one command, independently of the other.

- **S0.1.1** (S) *As a maintainer, I want `backend/` and `frontend/` scaffolded as independent projects, so that either can be developed, tested, and deployed on its own.*
  - Given a fresh clone, when I run `uv sync` in `backend/` and `npm install` in `frontend/`, then each succeeds without the other's toolchain installed.
  - Given either folder opened alone, then it contains its own dependency file, Dockerfile, and README section.
  - Notes: `uv init` with Python 3.12; `create-next-app` with TypeScript, Tailwind, App Router; shadcn/ui init.
- **S0.1.2** (M) *As a maintainer, I want one command to start Postgres with pgvector, the API, and the web app, so that local development mirrors the deployed topology.* `needs S0.1.1`
  - Given `.env` copied from `infra/.env.example`, when I run `docker compose up`, then the API answers on :8000, the web app on :3000, and Postgres has the `vector` extension.
  - Given the README, then `dev`, `test`, `migrate`, and `eval` tasks are documented and work.
- **S0.1.3** (M) *As a maintainer, I want linting, type checks, test runners, and a dependency manifest guard configured, so that quality checks run identically on every machine and no dependency change goes unrecorded.* `needs S0.1.1`
  - Given the empty skeleton, when I run `make lint`, then ruff, pyright, `npm run lint`, and `make deps-check` all pass.
  - Given a dependency added to `backend/pyproject.toml` or `frontend/package.json`, when I run `make deps`, then `scripts/gen_dependencies.py` rewrites `dependencies.txt` at the repo root from `backend/uv.lock` and `frontend/package-lock.json` with name, version, and owning app; running `make lint` without `make deps` fails on drift.
  - Given a commit, then a pre-commit hook runs ruff, prettier, and `make deps-check`.
  - Notes: `dependencies.txt` is generated, never edited by hand (rule in CLAUDE.md).
- **S0.1.4** (M) *As a maintainer, I want continuous integration that runs lint, type checks, tests with coverage, and the generated-file checks on every push, so that a broken main branch is caught before anyone reviews it.* `needs S0.1.3`
  - Given a push or pull request, when the workflow runs, then ruff, pyright, `npm run lint`, `tsc --noEmit`, pytest with coverage, and `make deps-check` run, and the job fails on any error.
  - Given backend line coverage below 80% on `crossbid/`, then the job fails and lists the uncovered files.
  - Given a stale `frontend/lib/api.ts`, then the job fails (this is the check S0.4.2 refers to).
  - Notes: GitHub Actions, one job per app; a Postgres + pgvector service container for integration tests that are not marked `live`. Coverage needs `pytest-cov` as a dev dependency, which is not in the pre-approved list and must be approved before this story is implemented.

**F0.2 Database and persistence** — one EU Postgres holds app data, vectors, checkpoints, and the long-term store.

- **S0.2.1** (M) *As a maintainer, I want a Supabase EU project with a private Storage bucket and a migration runner, so that schema changes are versioned and data stays in the EU.*
  - Given `migrations/0001_init.sql`, when I run the migrate script twice, then it applies once and records the version.
  - Given the project, then bucket `company-docs` exists and is private.
- **S0.2.2** (M) *As a bidder, I want a bid that was paused for days to resume exactly where it stopped, so that a review I could not finish today is not lost.* `needs S0.2.1`
  - Given a graph invoked with a thread id, when the API restarts, then `get_state` returns the saved state.
  - Given a transaction-pooler DSN, when the API starts, then it refuses with a message naming the session pooler.
  - Notes: psycopg pool with `autocommit=True`, `row_factory=dict_row`; `PostgresSaver.setup()` and `PostgresStore.setup()` at startup.
- **S0.2.3** (M) *As a maintainer, I want read-model tables for bids, requirements, matrix rows, reviews, usage, and settings, so that the dashboard reads plain rows instead of checkpoints.* `needs S0.2.1`
  - Given the migration, then every table in the Data model section exists with foreign keys and a `company_id` index.
  - Given a re-run, then the migration is idempotent.

**F0.3 Authentication and settings** — users sign in without passwords; operators change behaviour without redeploying.

- **S0.3.1** (M) *As a bidder, I want to sign in with a link sent to my email, so that I never manage a password.* `needs S0.2.1`
  - Given a valid Supabase token, when I call any `/companies` endpoint, then my user and company are resolved.
  - Given an expired or forged token, then the API answers 401.
  - Given my email in `DEVELOPER_EMAILS`, when I call `/dev/*`, then 200; otherwise 403.
  - Given `AUTH_MODE=dev` and a non-production environment, when a request carries `X-Dev-Company`, then that company is used without a token; given `AUTH_MODE=supabase`, then the header is ignored.
  - Notes: dev auth mode is the bridge that lets Increments 1–3 run before this story; it is refused at startup when `ENV=production`.
- **S0.3.2** (S) *As an operator, I want model slugs, temperature, max tokens, enabled tools, and the system prompt in one settings file with database overrides, so that tuning needs no code change.*
  - Given `settings.default.yaml`, when the API starts, then values load and the `app_settings` row overrides them.
  - Given a missing `OPENROUTER_API_KEY` or `APP_ENCRYPTION_KEY`, when the API starts, then it fails fast with a message naming the variable.
  - Notes: `llm.py` builds `ChatOpenAI` against `https://openrouter.ai/api/v1` with `extra_body={"usage": {"include": true}}`.
- **S0.3.3** (S) *As an operator, I want every graph run traced, so that I can inspect prompts, tool calls, and latency per node.*
  - Given `LANGSMITH_API_KEY`, when a bid runs, then a trace appears with `bid_id` metadata.
  - Given no key, then the application runs without error and without tracing.

**F0.4 Contracts** — one typed definition of every domain object, shared by API, graph, and frontend.

- **S0.4.1** (M) *As a maintainer, I want Pydantic models for every domain object, so that routers, graph nodes, structured outputs, and the frontend share one definition.*
  - Given the models in the layout, then each exports a JSON schema without error and every enum is closed.
  - Given `Requirement.ecertis_criterion_id`, then it is typed against the criterion list (placeholder until S1.1.3).
- **S0.4.2** (S) *As a maintainer, I want TypeScript types generated from the OpenAPI schema, so that the web app compiles against the real contract before backend logic exists.* `needs S0.4.1`
  - Given router stubs returning typed empty responses, when I run `npm run gen:api`, then `frontend/lib/api.ts` is written.
  - Given a stale generated file, then CI fails.

---

### E1 · Reference data and external clients — lane tag A

**Goal.** The agent consults the outside world through typed tools, none of which scrape.
**Why.** Certificate equivalence, tender search, and currency conversion are the facts the matrix depends on.
**Done when.** Five tools are registered with manifests and pass unit tests against recorded responses; the eCertis cache is committed.

**F1.1 eCertis evidence** — for any EU criterion, show which document a bidder from a given country submits as proof.

- **S1.1.1** (M) *As a maintainer, I want the EU criteria and the German and French evidence lists cached as JSON in the repository, so that tests and demos never depend on eCertis being up.* `needs S0.1`
  - Given the build script, when it runs, then `criteria.json`, `evidence_de.json`, and `evidence_fr.json` are written with a source date, and a second run changes nothing.
- **S1.1.2** (M) *As a bidder, I want to see which German document proves a criterion that a French tender invokes, so that I attach the right paper instead of guessing.* `needs S1.1.1`
  - Given criterion "payment of taxes" and bidder country DE, when the tool runs, then it returns the evidence name, issuer, and description in German and English.
  - Given a criterion with no German entry, then the tool returns status `not_found`, never an exception.
- **S1.1.3** (S) *As a maintainer, I want the criterion enum generated from the cache, so that the extractor can only choose criteria that exist.* `needs S1.1.1`
  - Given the generator, then the `Literal` type matches the cache and the extraction schema rejects unknown ids.

**F1.2 TED search** — find and read published notices without leaving Crossbid.

- **S1.2.1** (M) *As a bidder, I want to search TED by CPV code, country, and keyword, so that I find tenders in my field without learning the TED portal.*
  - Given CPV 72000000 and country FR, when I search, then results show title, buyer, deadline, languages, publication number, and the documents link.
  - Given any filter combination, then the query never places `OR` inside `IN (...)`.
  - Given a network failure, then the client retries once and returns a typed error.
- **S1.2.2** (S) *As a bidder, I want to open the notice as published, so that I read the buyer's own words before uploading documents.* `needs S1.2.1`
  - Given a result, when I open it, then the notice PDF downloads in its source language.
  - Given the tool registry, then `search_ted` is registered with a manifest.

**F1.3 Currency conversion** — thresholds and bonds in the bidder's currency.

- **S1.3.1** (S) *As a bidder, I want turnover thresholds and bid bonds converted to euros at the ECB rate, so that I can tell whether my company qualifies.*
  - Given 2,000,000 PLN, when converted, then the tool returns the EUR value and the rate date.
  - Given the rate service is down, then the last cached rate is returned with a staleness flag.
  - Notes: kept as the fifth registered tool (brief Medium 6). Both fixture tenders are in EUR, so the demo never converts; the tool is exercised by unit tests only. Scheduled in Increment 4, after the four tools the matrix needs.

**F1.4 Tool registry** — operators decide which tools the agent may call.

- **S1.4.1** (M) *As an operator, I want to enable or disable tools without redeploying, so that I can constrain what the agent may reach.* `needs S1.1.2, S2.4.2; S1.2.2 and S1.3.1 register themselves when they land in Increment 4`
  - Given `enabled_tools` in settings, when the graph builds, then only those tools are bound.
  - Given a tool module, then it exports `MANIFEST` with name, description, `external`, and `default_enabled`, and `GET /dev/settings` lists all manifests.

---

### E2 · Ingestion and company memory — lane tag B

**Goal.** Every PDF a bidder uploads becomes page-cited, guarded, searchable text, and the company's facts are remembered.
**Why.** The matrix is only as trustworthy as the evidence it can find and cite.
**Done when.** The demo GmbH pack is seeded; a French query for information-security certification returns the German ISO 27001 page; the adversarial fixture is flagged.

**F2.1 Parsing and chunking** — page-faithful text from PDFs.

- **S2.1.1** (M) *As a bidder, I want my PDFs read page by page, so that every finding can point to a page I can open.* `needs S0.1`
  - Given a text PDF, when parsed, then the result has one entry per page.
  - Given a page without extractable text, then its number appears in `unread_pages` and parsing continues.
- **S2.1.2** (M, **Could**) *As a maintainer, I want Docling available behind the same parser interface, so that table-heavy tenders can be re-parsed by changing a setting.* `needs S2.1.1`
  - Given `parser: docling`, when the DE fixture is parsed with OCR off, then the page count and shape match the default parser.
- **S2.1.3** (S) *As a maintainer, I want chunks of about 800 tokens with 100 overlap that carry their page, so that every retrieval hit has a citation.* `needs S2.1.1`
  - Given a chunk that crosses a page boundary, then both pages are recorded.
  - Given the fixture, then chunk sizes are within 10% of the target.

**F2.2 Embeddings and storage** — private files, multilingual search.

- **S2.2.1** (M) *As a bidder, I want my documents searchable by meaning across languages, so that a French requirement finds evidence in my German files.* `needs S0.2.2`
  - Given the demo pack, when I query in French for information-security certification, then the German ISO 27001 chunk ranks first.
  - Given any search, then it is scoped by `company_id` and, for tenders, `bid_id`.
  - Notes: OpenRouter `/embeddings` with the slug from settings.
- **S2.2.2** (M) *As a bidder, I want my files stored privately and viewable only by me, so that company documents never leak.* `needs S0.2.1`
  - Given an upload, then it is stored under my company prefix and the signed URL expires within 10 minutes.
  - Given another company's document id, when I request its URL, then 404.
- **S2.2.3** (M) *As a bidder, I want to upload a document and see it become ready, so that I know when the agent can use it.* `needs S2.2.1, S2.2.2`
  - Given an upload, then the API answers 202 with an id and status moves `uploaded → parsed → embedded → ready`, or `failed` with a reason.
  - Given unread pages, then their count is shown on the document.

**F2.3 Guards** — untrusted documents cannot steer the agent or run up the bill.

- **S2.3.1** (M) *As a reviewer, I want text that tries to instruct the AI to be flagged and kept out of the analysis, so that a malicious tender cannot steer the verdict.* `needs S6.5`
  - Given the adversarial fixtures, when ingested, then each planted instruction chunk is flagged and listed on the document.
  - Given the clean fixtures, then zero chunks are flagged.
  - Given a flagged chunk, then it never enters a prompt.
- **S2.3.2** (S) *As a maintainer, I want all document text wrapped as data in every prompt, so that it is never read as instructions.*
  - Given any prompt template, then the wrapper is applied and a unit test asserts the delimiters.
- **S2.3.3** (S) *As an operator, I want per-user limits on uploads and bid creation, so that one account cannot exhaust the LLM budget.*
  - Given the configured limit, when it is exceeded, then the API answers 429 with a retry-after header.

**F2.4 Company profile and memory** — facts the bidder controls, remembered across bids.

- **S2.4.1** (M) *As a bidder, I want to record my company's country, legal form, turnover, and certificates with expiry dates, so that requirements are checked against facts I control.* `needs S0.2.3 (runs under dev auth mode until S0.3.1)`
  - Given the form, when I save, then `GET /companies/me` returns the profile and the Store namespace `profile/{company_id}` is written.
  - Given a certificate whose expiry has passed, then it is flagged on the profile.
- **S2.4.2** (M) *As a maintainer, I want retrieval tools over company and tender chunks, so that the agent gathers evidence itself.* `needs S2.2.1`
  - Given a query, then each tool returns document id, page, quote, and score for the top results, scoped by company and bid.
- **S2.4.3** (M) *As a maintainer, I want a one-command seed of the demo GmbH, so that any environment can run the walkthrough.* `needs S6.3`
  - Given an empty database, when the seed runs, then the company, profile, and all documents exist and are `ready`; a second run changes nothing.

---

### E3 · Agent graph — lane tag B

**Goal.** A bidder receives a page-cited bilingual requirement matrix and a rules-based go/no-go that pauses for human review and continues with the reviewer's decisions.
**Why.** This is the product: judgement work before a bid is written, with a human holding the final word.
**Done when.** The DE fixture run stops at the interrupt with at least 90% of golden mandatory requirements found (S3.2.3 against S6.4); a review resumes to a final state; every listed failure mode is handled.

**F3.1 Run lifecycle** — start a bid and follow it.

- **S3.1.1** (M) *As a bidder, I want to start a bid and follow its progress, so that I know the agent is working and when it needs me.* `needs S0.2.2`
  - Given a notice number and ready documents, when I post a bid, then 202 with an id and the graph runs in the background.
  - Given polling, then status is one of `queued, parsing, extracting, checking, scoring, awaiting_review, finalizing, done, failed`.
  - Given an API restart mid-run, then the run resumes from its last checkpoint.
  - Given the DE fixture pack on the default models, when a bid runs, then it reaches `awaiting_review` within 10 minutes and the OpenRouter-reported cost is under $2.50; both limits live in settings and are asserted by the `live` integration test.

**F3.2 Requirement extraction** — everything the tender asks, typed, cited, and explained.

- **S3.2.1** (L) *As a bidder, I want every requirement listed with its type, category, page, and quote, and explained in German, so that I understand a French tender without reading 100 pages of French.* `needs S1.1.3, S2.3.2; recall criterion verified by S3.2.3 once S6.4 lands`
  - Given a parsed tender, when extraction runs, then each requirement has kind, category, page, source quote, translation, and a nullable criterion id.
  - Given the DE golden tender, then recall on mandatory requirements is at least 0.9, measured by S3.2.3. Until S6.4 exists the SP.1 figure stands in and the story is not closed.
  - Given an extracted row without a quote, then it is rejected and re-asked once.
  - Notes: sections of 5–8 pages, structured output per section, dedupe by quote similarity and page proximity.
- **S3.2.2** (S) *As a bidder, I want the buyer's structured notice data used directly, so that the deadline, languages, and stated criteria are never mis-read.* `needs S1.2.1`
  - Given a TED notice, then its criteria descriptions, submission language, and deadline become requirements tagged `source: notice` before LLM extraction, and the deadline is stored on the bid.
- **S3.2.3** (S→M) *As a maintainer, I want a recall script that scores extraction against the golden labels, so that E3's done-when is checked while the graph is built, not weeks later in S7.1.* `needs S3.2.1, S6.4`
  - Given a golden YAML and an extraction result, when the script runs, then it prints recall on mandatory requirements per tender and exits non-zero below the threshold in settings.
  - Given S7.1, then the DeepEval suite reuses this matcher instead of reimplementing it.
  - **Given S6.4's labels are LLM drafts, then this script also carries their human verification** *(user decision, 2026-09-12: "fold it")*. `test_golden_labels.py` already proves every label's quote is verbatim on its cited page, so the machine-checkable half is done; what a person must still judge is whether a row is really a requirement, whether its `kind`/`stage` are right, and **what is missing** — the one failure a verbatim check cannot see. The script therefore reports, per tender: extracted rows with no golden match (candidate missing labels), golden rows the extractor never found (the recall misses), and disagreements on `kind`/`stage`/`criterion`. The reviewer adjudicates that list rather than reading 257 labels, and flipping a file's header to `labelled_by: llm_assisted_human_verified` with a `verified_by`/`verified_on` is what closes S6.4 — and with it S3.2.1 and Milestone 1.
  - Notes: this is why S3.2.3 must filter the DE file on `stage: bid_eligibility` before scoring (13 of 143 scored rows are `contract_performance` on purpose, ADR-0015).

**F3.3 Per-requirement checking** — the agentic core.

- **S3.3.1** (L) *As a bidder, I want each requirement checked against my documents and, where relevant, against the German equivalent evidence, so that I see exactly what I can prove and what I cannot.* `needs S1.4.1, S2.4.2`
  - Given the requirement list, when checking runs, then each requirement yields a matrix row with status in `supported, supported_via_equivalent, unsupported, partially_supported, needs_document`, evidence quotes with pages, eCertis evidence when a criterion id is set, and a rationale. *(vocabulary amended 2026-09-11, ADR-0013)*
  - Given any row with status `met`, then it has at least one evidence quote.
  - Given the run, then no requirement uses more than 4 tool calls and no more than 5 run concurrently.
  - Notes: LangGraph `Send` fan-out; a small ReAct loop per requirement.
- **S3.3.2** (M) *As a maintainer, I want deterministic tests for every status branch, so that a prompt change cannot silently break the matrix.* `needs S3.3.1`
  - Given a fake model scripted for each of the five statuses, then the row shape and tool-call limits are asserted.

**F3.4 Verdict, interrupt, review** — the human decides.

- **S3.4.1** (M) *As a bidder, I want a clear go or no-go with the exact gaps in my language, so that I can decide in minutes.* `needs S3.3.1`
  - Given any mandatory row `unsupported` or any exclusion ground unmet, then the verdict is `no_go` with the gap list. *(vocabulary amended 2026-09-11, ADR-0013)*
  - Given mandatory rows `partially_supported`, then the verdict is `conditional` naming them. *(vocabulary amended 2026-09-11, ADR-0013)*
  - Given a mandatory row without evidence, then the verdict is never `go`.
  - Given the user's language and tone settings, then the explanation follows them.
- **S3.4.2** (M) *As a reviewer, I want the run to pause for my confirmation and continue with my edits, so that no verdict leaves the system unchecked.* `needs S3.4.1`
  - Given scoring has finished, then the graph interrupts and the bid shows `awaiting_review`.
  - Given row edits and a decision, when I submit the review, then the scorer re-runs on my statuses and the bid ends `done`.
  - Given my decision differs from the recomputed verdict, then an override with my reason is recorded.
  - Given a second submission, then 409.
- **S3.4.3** (M) *As a bidder, I want the dashboard to reflect my bids instantly, so that I never wait on the agent's internal state.* `needs S3.4.2`
  - Given scoring and given review, then the read-model tables are written at each point and `GET /bids` reads only from them.
  - Given a consistency test, then read-model rows match the checkpoint.
- **S3.4.4** (M) *As a bidder, I want the run to survive bad inputs and flaky services, so that one unreadable page or timeout does not lose my bid.* `needs S3.4.2`
  - Given unread pages, then they are listed on the bid.
  - Given an LLM timeout, then one retry, then the smaller model.
  - Given a schema violation, then one re-ask, then the row is `partially_supported`. *(vocabulary amended 2026-09-11, ADR-0013)*
  - Given no eCertis entry, then the row is flagged for the reviewer.
  - Given an expired certificate used as evidence, then a warning with the date.

**F3.5 Ask the tender** — questions with citations.

- **S3.5.1** (M) *As a bidder, I want to ask questions about the tender and my matrix and get cited answers in German, so that I can clarify a point without re-reading.* `needs S2.4.2, S3.4.3`
  - Given a question, then the answer cites document and page.
  - Given nothing relevant in the documents, then the answer says so instead of guessing.
  - Notes: separate thread `bid:{id}:chat` with `tender_rag_search`, `company_rag_search`, `get_matrix`.

---

### E4 · Web app — lane tag C

**Goal.** A non-procurement user completes onboarding, starts a bid, reviews the matrix beside the source document, and confirms a verdict without training.
**Why.** The review step is the product's safety boundary; it has to be fast and legible for someone who is not a lawyer.
**Done when.** The Playwright smoke test passes and a first-time user completes the DE walkthrough from the user guide unaided.

**F4.0 Design before code** — the screens are agreed with the user before any product component is coded.

- **S4.0.1** (M) *As a bidder, I want the screens designed and agreed before they are coded, so that the review workspace is legible to a non-lawyer on the first build.* `needs S0.4.1; blocks S4.4.1, S4.5.1, S4.5.2, S4.5.3`
  - Given the domain contracts, when the design canvas is produced with the `/design` skill, then it holds artboards for the dashboard, the new-bid flow, the bid workspace at desktop and phone width, and the confirm/override state of the verdict panel.
  - Given the canvas, then the user reviews it in the published artifact and either confirms it or requests changes; no component under `components/matrix`, `components/pdf`, or `components/verdict` is coded before that confirmation.
  - Given confirmation, then the artifact URL and every accepted change are recorded in an ADR, and later UI stories cite the artboard they implement.
  - Notes: the shell, login, and upload screens (S4.1.2, S4.2.2) are stock shadcn/ui and are exempt. The confirmation is a hard gate; the roadmap shows it as a milestone inside Increment 1.

**F4.1 Shell and sign-in** — a place to work, in plain English.

- **S4.1.1** (M) *As a bidder, I want to sign in by clicking a link in my email and land on my dashboard, so that I start working within a minute.* `needs S0.4.2`
  - Given the login page, when I enter my email, then a link arrives and following it opens the dashboard with a persisted session.
  - Given a protected route without a session, then I am redirected to login.
- **S4.1.2** (S) *As a bidder, I want a consistent layout with clear navigation, so that I always know where bids, company, and settings are.* `needs S0.4.2 (hand-written types for the first two endpoints are acceptable until it lands); login link appears with S4.1.1`
  - Given any page, then navigation shows Dashboard, Company, Settings, and New bid; empty states explain the next step.

**F4.2 Onboarding** — tell Crossbid about the company.

- **S4.2.1** (M) *As a bidder, I want to fill in my company's country, legal form, turnover, and certificates, so that checks run against my facts.* `needs S4.1.1`
  - Given the form, when I save, then values persist and validation errors name the field.
  - Given the same form, then explanation language (default German) and tone are set here, so brief Easy 2 does not depend on the Could-priority provider page.
- **S4.2.2** (M) *As a bidder, I want to upload company documents by type and watch them become ready, so that I know the agent can use them.* `needs S4.1.2, S2.2.3`
  - Given a file, when I upload it with a type, then a row shows status until `ready` or `failed` with a reason and unread-page count.

**F4.3 New bid** — from tender search to a running check.

- **S4.3.1** (M) *As a bidder, I want to search TED, pick a notice, upload its documents, and start the check in one flow, so that I never leave the app to begin.* `needs S4.1.1`
  - Given search filters, then results show buyer, deadline, and languages, and a link to the platform hosting the documents.
  - Given a picked notice, then Start is disabled until at least one tender document is `ready`.

**F4.4 Dashboard** — the state of every bid at a glance.

- **S4.4.1** (M) *As a bidder, I want to see each bid's status, verdict, days to deadline, and open items, so that I know what needs me today.* `needs S4.1.1, S4.0.1`
  - Given bids, then each row shows a verdict badge, a deadline countdown in the buyer's time zone, and the count of open items.

**F4.5 Bid workspace** — verify every claim in one click.

- **S4.5.1** (L) *As a reviewer, I want the source PDF beside the matrix with jump-to-page from every citation, so that I can verify a claim without searching.* `needs S3.1.1, S4.0.1`
  - Given a citation, when I click it, then the viewer opens that page.
  - Given a running bid, then the page polls and shows the current stage, and lists extracted requirements as soon as they exist.
  - Given matrix rows, then they render read-only with status, evidence quotes, and the eCertis card; editing is S4.5.2. This criterion is completed in Increment 2, the rest in Increment 1.
- **S4.5.2** (L) *As a reviewer, I want to change a row's status, give a reason, attach a document, and switch each row between French and German, so that my judgement is recorded next to the agent's.* `needs S3.4.3, S4.0.1`
  - Given a row, when I edit status or attach a document, then the change is held locally until I confirm and the agent's original stays visible.
  - Given a row with eCertis evidence, then a card names the German document and issuer.
  - Given flagged chunks or unread pages, then a notice lists them.
- **S4.5.3** (M) *As a reviewer, I want to confirm the verdict or override it with a reason, so that nothing proceeds without my decision.* `needs S3.4.2, S4.0.1`
  - Given my edits, when I confirm or override, then the review is submitted once and the final state is shown.

**F4.6 Chat, developer panel, settings** — the supporting surfaces.

- **S4.6.1** (M) *As a bidder, I want to ask questions about the tender and see cited answers, so that I clarify without re-reading.* `needs S3.5.1`
  - Given a question, then the answer shows citations that jump to the page.
- **S4.6.2** (M) *As an operator, I want a developer panel to pick models per role, tune temperature and max tokens, edit the system prompt, toggle tools, and see cost per bid and node, so that I tune the agent without touching code.* `needs S5.2`
  - Given a non-developer account, then the route is not reachable.
  - Given a change, when saved, then the next bid uses it.
- **S4.6.3** (S) *As a bidder, I want to rate a matrix row or chat answer and add a comment, so that my corrections are kept for later improvement.*
  - Given a thumbs rating, then it is stored with the row or answer id.
- **S4.6.4** (M, **Could**) *As a bidder, I want to add my own OpenAI, Anthropic, or OpenRouter key and choose which one my bids use, so that I control the provider and the bill.* `needs S5.4`
  - Given a key, when I press Test and save, then it is verified and only the last four characters are shown afterwards.
  - Given an invalid key, then nothing is saved and the error names the provider.
  - Given the page, then it states that embeddings always use the app's route.

---

### E5 · Multi-model, bring your own key, observability, cost — lane tag A

**Goal.** Operators choose models, users may bring their own keys, and every run's cost is visible and attributed.
**Why.** Model choice and cost transparency are graded, and a bidder paying their own provider is a real deployment path.
**Done when.** A bid runs on a user's OpenAI key with the correct provider in the cost view, and falls back with a warning when the key is removed.
**Priority.** S5.1, S5.2, S5.3 are Must (they cover brief Easy 3, Medium 1, Medium 7, Medium 8) and belong to Increment 4. S5.4, S5.5, S5.6 and S4.6.4 (bring your own key) are **Could**: no brief item asks for them, so they are Increment 6, after grader evidence.

- **S5.1** (M) *As an operator, I want to switch the model for each role among OpenAI, Anthropic, and Google slugs on OpenRouter, so that I can compare quality and cost.* `needs S1.4.1`
  - Given a slug change, then the next bid uses it and structured output still validates.
- **S5.2** (M) *As an operator, I want tokens and cost per bid and per node, so that I can see where the money goes.* `needs S0.3.2 (OpenRouter usage accounting); S5.6 later adds direct-provider rows`
  - Given a finished bid, then `GET /dev/costs` shows tokens and cost per node with the provider used.
- **S5.3** (S) *As a reviewer, I want flagged chunks confirmed by a cheap model, so that false positives from heuristics do not hide legitimate text.* `needs S2.3.1`
  - Given a heuristically flagged chunk, then the classifier's yes/no is stored with it.
- **S5.4** (M, **Could**) *As a bidder, I want my provider key stored securely and verified when I save it, so that I can trust it is never exposed.* `needs S0.2.3, S0.3.1`
  - Given a key, when saved, then a one-token call verifies it first, it is encrypted at rest, and only a last-four hint is ever returned.
  - Given logs and traces, then the key never appears.
  - Given repeated attempts, then the endpoint is rate-limited.
- **S5.5** (M, **Could**) *As a bidder, I want my bids to run on the provider I selected, and to fall back safely if my key stops working, so that a broken key never blocks a deadline.* `needs S5.4`
  - Given an active own key, then the model factory uses it for that company.
  - Given a missing or invalid key, then the bid runs on the app route and shows a warning.
- **S5.6** (S, **Could**) *As an operator, I want costs for direct providers computed from tokens and a price table, so that every provider is accounted for.* `needs S5.5`
  - Given a direct-provider run, then `llm_usage` rows carry tokens and computed cost; OpenRouter runs carry the reported cost.

---

### E6 · Content: fixtures, demo company, golden set — lane tag D

**Goal.** Real, verifiable material to build and judge against.
**Why.** Without real tenders and labelled requirements, no quality claim can be made.
**Done when.** Two real tender packs and one EN notice are committed with sources, the demo GmbH pack exists, and the golden set is labelled and verified.

- **S6.1** (M) *As a maintainer, I want one German and one French CPV 72 tender pack downloaded from platforms that allow anonymous access and committed with their sources, so that every test and demo uses real documents.*
  - Given `tests/fixtures/tenders/{de,fr}/`, then each holds the pack under 15 MB and `SOURCES.md` lists the TED number and platform URL.
- **S6.2** (M) *As a maintainer, I want one English TED notice for the golden set, so that recall is measured on a language every grader can read.*
  - Given `tests/fixtures/tenders/en/`, then it holds the notice PDF in English under 15 MB and `SOURCES.md` lists the TED publication number.
  - ~~Given the notice, then it states at least 15 selection or exclusion criteria~~ — **amended 2026-09-10 (ADR-0006): met by the committed pack, not the notice PDF.** The EASA fixture's pack states 20 criteria (14 exclusion + 6 selection); the notice itself states none. Across 600 English CPV-72 notices the maximum carried *in a notice* was 13, and 496 carried none, so the original wording would have forced either an EEA fixture or a weaker one.
- **S6.3** (L) *As a bidder, I want a believable document pack for the demo GmbH, so that the walkthrough shows real evidence rather than placeholders.*
  - Given the pack, then it contains a register extract, tax certificate, ISO 27001 certificate, liability insurance, three past-bid summaries, two reference letters, and `profile.yaml`, all in German.
- **S6.4** (L) *As an evaluator, I want each golden tender's requirements labelled with category, kind, page, quote, and criterion, so that extraction can be scored.* `needs S6.1, S6.2` — **DONE 2026-09-13.**
  - Given the YAML, then labels were produced with LLM assistance and each was verified by a human, and the method is stated in the file header. ✔ All three keys read `labelled_by: llm_assisted_human_verified`, `verified_by: Ahmed Nazih Ali`, `verified_on: 2026-09-13`; each header states what a person adjudicated and each carries a `VERIFICATION.md` worksheet beside it. DE was verified against the live extraction scored by S3.2.3; FR and EN by reading, the live test being DE-only.
- **S6.5** (S) *As a maintainer, I want PDFs with planted instructions, so that the injection guard has something to catch.*
  - Given `tests/fixtures/adversarial/`, then it holds at least three PDFs, each planting one instruction in a different form (plain paragraph, white-on-white text, inside a table), with a manifest of page and planted text.
  - Given each PDF, then the surrounding content is a plausible tender excerpt, so the guard is tested against realistic noise.

---

### E7 · Evaluation and documentation — lane tag E

**Goal.** Evidence of quality, and documentation a reviewer can follow without the author present.
**Why.** The course grades understanding and reflection as much as the build.
**Done when.** `evaluations/REPORT.md` reports the metrics on three tenders, every decision has an ADR, and the user guide walks through three bids.

- **S7.1** (M) *As an evaluator, I want requirement recall, citation faithfulness, and translation adequacy measured on the golden set, so that quality is a number, not a claim.* `needs E3, S6.4`
  - Given the eval script, then `REPORT.md` shows the three metrics per tender, and the judge model is from a different vendor than the model under test.
- **S7.2** (S each, continuous) *As a maintainer, I want an ADR for every settled decision, written when the decision lands, so that the reasoning survives the session that made it.*
  - Given a settled decision implemented by a story, when that story is committed, then `docs/decisions.md` has a dated entry with context, options considered, choice, and consequences.
  - Given the settled-decision list at the top of this plan, then every bullet maps to at least one ADR by the end of Increment 3.
- **S7.3** (M) *As a reviewer of the project, I want an architecture document with the graph and a plain statement of what is a workflow and what is an agent, so that I can judge the design.* `needs F3.4`
  - Given `docs/architecture.md`, then it contains the outer graph diagram, the `check_reqs` fan-out, and one paragraph naming which parts are a deterministic workflow and which are agentic.
  - Given a reader who knows LangGraph but not this repository, then they can name every node with its inputs and outputs from the document alone.
- **S7.4** (M) *As a bidder, I want a user guide with three worked examples, so that I can run my first bid without help.* `needs E4 Must stories (S4.6.4 excluded)`
  - Given the guide, then it covers a German domestic bid, a French cross-border bid, and a no-go case, each with screenshots.
- **S7.5** (S) *As a maintainer, I want an LLM critique of usability, security, and prompt engineering with the fixes applied, so that obvious gaps are closed before review.*
  - Given the running app and its prompts, when the critique is requested from a model other than the extraction model, then `docs/critique.md` lists each finding with severity and either the fixing commit or the reason it was declined.
- **S7.6** (S) *As a maintainer, I want the README quick start and `project.md` trimmed to what was built, so that the repository tells one story.*
  - Given a fresh clone, when a reader follows the README quick start, then the app runs locally without consulting any other file.
  - Given `project.md`, then it describes only what was built and links to this plan for everything else.
  - Given `CLAUDE.md`, then its build, lint, and test commands match the Makefile.
- **S7.7** (M) *As a maintainer, I want a browser smoke test of login, bid, and confirm, so that the critical flow is guarded against regressions.* `needs E4 Must stories (S4.6.4 excluded)`
  - Given the seeded demo company, when the Playwright test runs against the local stack, then it signs in, starts a bid on the DE fixture, waits for `awaiting_review`, confirms, and asserts the final verdict on the dashboard.
  - Given a failure, then a screenshot and trace are saved as artifacts.
  - Notes: sign-in uses a pre-issued session or Supabase's test OTP, never a real inbox.

---

### E8 · Deployment — optional, last

**Goal.** A live EU-hosted instance for the portfolio.
**Done when.** The web app on Vercel reaches the API on Railway or Fly in an EU region through the session pooler, and the smoke test passes against it.

- **S8.1** (M, **Optional**) *As a bidder, I want to use Crossbid from a public URL, so that I can try it without installing anything.* `needs all`
  - Given the public URL, when the S7.7 smoke test runs against it, then it passes.
  - Given the API, then its DSN uses the session pooler and every service runs in an EU region.
  - Given the deployment, then no secret is in the repository; all are set in the host's environment.
- **S8.2** (S, **Optional**) *As a visitor to the public site, I want an imprint, a privacy notice, and a way to ask for a demo, so that the site is lawful to publish and I can reach the team.* `needs S8.1` *(added 2026-09-11: the landing page was built from the design system's website kit, ADR-0014, and its footer would otherwise link to pages that do not exist)*
  - Given a public deployment from Germany, then `/imprint` states the operator per §5 DDG and `/privacy` states the processing per GDPR Art. 13, both linked from the landing footer.
  - Given "Book a demo" or "Talk to the team", then it reaches a real address (a `mailto:` is enough), not an in-page anchor.
  - Given the site is not deployed, then none of this is built: the landing footer lists only sections that exist.

---

## Delivery Milestones

<!-- Business outcomes, not engineering tasks. Status: pending | in-progress | complete. `/plan` updates Status and Plan. One milestone = one increment in the Delivery order below. -->

| # | Milestone | Outcome | Status | Plan |
|---|---|---|---|---|
| 0 | Core bet tested | SP.1 spike on the DE fixture prints a recall figure; go or pivot recorded in an ADR | **complete** | Recall 1.00 automated / 0.95 audited vs a 0.70 gate → **GO** (ADR-0003). Precision, not recall, is the risk: `stage` filter cut 579→238 rows; extraction must fan out (S3.2.1) as 47 sequential calls blow S3.1.1's 10-min budget. |
| 1 | Requirement list in the browser | `docker compose up` starts API, web, and Postgres; a tender pack uploaded in the bare shell yields a page-cited, translated requirement list; a checkpoint survives a restart; the screen designs are confirmed by the user before workspace code starts (E0 minus auth, F2.1, F2.2, S2.3.2, S3.1.1, S3.2.1, S4.0.1, S4.5.1) | **in-progress** | Done: S0.1.1-S0.1.4, S0.4.1, S0.3.2/S0.3.3, S2.1.1/S2.1.3, S1.1.1/S1.1.3, S6.1 FR, S6.2 EN, S0.2.1/S0.2.3, S2.3.2, S0.4.2, S0.2.2 (ADR-0010), S2.2.1/S2.2.2/S3.2.1/S4.1.2 (ADR-0011), **S2.2.3** (upload → parsed → embedded → ready; tender kinds stop at ready — vectors are the graph's job), **S3.1.1** (`POST/GET /bids`, `parse_docs → extract_reqs → await_review` interrupt, runner resumes unfinished bids at startup, budgets in settings; live DE-pack test run once: 290 s, $1.38, 258 requirements — within the 600 s / $2.50 budget), **S0.3.1 dev bridge** (`X-Dev-Company`), **S4.2.2** (upload table + reusable polling hook; found and fixed the missing CORS middleware), **S4.0.1 draft published** — ADR-0012. Migrations 0002/0003 applied to Frankfurt. **960 tests, 100% coverage, all offline.** **S4.0.1 confirmed** by the user on version 6 of the canvas, built on their design system (ADR-0013 vocabulary, ADR-0014 record); `make seed-dev` created the demo tenant. **S4.5.1 (Increment-1 criteria)** done: the design system ported into the web app (tokens, 260 px sidebar shell, primitives citing their artboards), `/bids/{id}` polls every 2 s and lists requirements as they appear, citations jump the browser-native PDF viewer to the page via a signed URL (`GET /documents/{id}/url`), start step on `/bids/new`, `/bids` list; verified in a production build at 1440 and 390 px. **988 tests, 100% coverage.** Landing page implemented from its artboard; shadcn tooling removed. **Two things hold it open, and the second changed character on 2026-09-14.** (1) The cadence requires a recorded end-to-end demo against Frankfurt; not yet recorded. The round trip *has* now been walked in a browser end to end (ADR-0029) — a walkthrough is not a recording, but nothing in the flow is unproven. (2) **S3.2.1 fails its recall criterion.** S3.2.3 now exists and S6.4's keys are human-verified, so the number is measured against a verified key at last — and it is **0.72 on the committed live run, ~0.74 ± 0.02 across four**, against a gate of 0.9. Verifying the key made the figure *trustworthy*, not *higher*, which is the opposite of what this row previously assumed. The story therefore fails on a measurement rather than waiting on a task, and what to do about a threshold set before anything had been measured is an open decision, not an outstanding piece of work. Everything else in the milestone is built and verified. Matrix-row evidence states, buyer/deadline tags and the verdict panel were always Increment 2/3. |
| 2 | Matrix in the browser | Demo GmbH pack seeded; a French query for information-security certification returns the German ISO 27001 page; every requirement has a matrix row with status, evidence, and eCertis card where a criterion is set (F1.1, F1.4, F2.4, F3.3, S4.5.1) | **complete** | Done 2026-09-11 (ADR-0015, commit `79ab06d`): **S1.1.2** (eCertis bidder-language overlay `l10n_de.json`, UUID-keyed; `?lang=de` returns byte-identical ids), **S2.4.2** (`company_rag_search` / `tender_rag_search`, joining `documents` for the filename a citation needs), **S2.4.1** (`GET`/`PUT /companies/me`, no migration; a failed Store write answers 200 with a `warning`), plus wait-fillers **S6.3** (10 generated German demo PDFs, byte-identical on rebuild) and **S6.4** (DE/FR/EN golden keys — **LLM drafts, `verified_by: pending`**, so the story is NOT closed). 2318 tests, 100% coverage. Remaining, in order: **S1.4.1** (tool registry — the three `MANIFEST`s now exist), **S3.3.1** (`check_reqs`, the agentic core), **S3.3.2**, **S4.5.1**'s matrix-row criterion, then **S3.2.3** — all now landed (2026-09-12). **Every story of Increment 2 is built**, and **the milestone is closed (2026-09-14)**. S6.4 closed on 2026-09-13 — all three `golden.yaml` files carry `labelled_by: llm_assisted_human_verified` with a name and a date, and a `VERIFICATION.md` beside each recording what a person actually adjudicated (ADR-0020). Every done-when criterion is verified against Frankfurt rather than asserted: the demo GmbH pack is seeded with ten evidence documents; **a French query for information-security certification returns `Zertifikat_ISO_IEC_27001_2022.pdf` as its top hit** (cosine distance 0.603, checked 2026-09-14 — and a French query for professional indemnity insurance returns the German `Betriebshaftpflichtversicherung_Bestaetigung.pdf`), so the cross-language retrieval the wedge depends on works on the real pack; and a real FR run produced **144 requirements, 144 matrix rows, 30 carrying an eCertis card of which 29 resolved** (ADR-0029). The one thing this milestone does *not* close is S3.2.1's recall number, which belongs to Increment 1 and is dealt with there. |
| 3 | Review round-trip | Bid stops at `awaiting_review`; the reviewer edits rows and confirms or overrides in the workspace; dashboard shows the final verdict from the read model (F3.4, S2.4.3, S4.5.2, S4.5.3, **S4.4.1**) | **complete** | **The backend of F3.4 is done** (2026-09-14): **S3.4.1** the rules-only scorer with a templated explanation in de/en/fr × plain/formal/brief (ADR-0024); **S3.4.2** the review round-trip — the interrupt resumes with a typed `ReviewSubmission`, the same scorer re-runs on the reviewer's statuses, the bid ends `complete`, and a second submission is a 409 claimed by a conditional `UPDATE` (ADR-0025); **S3.4.3** the read-model consistency test, which found that S3.4.2's reviewer columns never reached the database and added the statement that writes them (ADR-0026); **S3.4.4** resilience — one retry then a different-vendor fallback for route failures, one re-ask then `partially_supported` for schema failures, and reviewer notices for an eCertis criterion with no national entry and for evidence from a lapsed certificate (ADR-0027). Migration **0006** applied to Frankfurt (`bids.decision`; `reviews.reviewer_id` nullable, because under `AUTH_MODE=dev` there is no verified identity to record). **S2.4.3** was pulled forward into Increment 2. **S4.5.2** and **S4.5.3** landed on 2026-09-14, built in parallel against the artboards; wiring them together produced the one defect neither side's tests could see (ADR-0029).

**Closed 2026-09-14, and the third criterion is why S4.4.1 moved here.** "Dashboard shows the final verdict from the read model" named a surface whose story sat in Increment 4, which would have made the two increments circular. The user's call was to pull **S4.4.1** into Increment 3 and build it rather than reword the criterion. That exposed a real gap: nothing had ever written `bids.deadline` or `bids.buyer` — extraction sets no deadline and TED search is S1.2.1 — so the countdown column had no data source at all. Migration **0007** adds `deadline_utc_offset_minutes`, because a `timestamptz` keeps the instant and loses the wall clock the buyer wrote, and "a countdown **in the buyer's time zone**" needs the latter; an offset and never an IANA zone, since neither a notice nor TED publishes one. `POST /bids` and the start form now take the buyer and a deadline, and **refuse a timestamp with no offset rather than assuming UTC**. `BidSummary` gained `open_items`, counted from the matrix rather than from the verdict's gaps so that an unscored bid still reports its work.

Verified in a browser against Frankfurt on the completed FR bid: the row reads **9 Oct · 25 days / 16:00 (UTC+02:00)**, *Ministère de l'éducation nationale*, **Conditional · confirmed**, **142 open items**. The buyer's-clock rendering was checked the only way that discriminates — the offset was flipped to zero and the same instant printed **14:00 (UTC)** on a machine sitting at UTC+02:00, while the countdown stayed at 25 days. Two tiles from the artboard were deliberately **not** built: *Requirements checked / last 7 days* needs history the API has no shape for, and *Go rate* over a handful of decided bids reads as a trend it cannot support. |
| 4 | Every graded requirement covered | Magic-link sign-in, company form, TED search to start (which fills the dashboard's deadline and buyer, built in Increment 3), "ask the tender" with citations, injection guard and rate limits, cost per node, slug switching, feedback thumbs, dev panel (S0.3.1, F1.2, F1.3, F2.3, F3.5, F4.1–F4.4, S4.6.1–S4.6.3, S5.1–S5.3) | pending | — |
| 5 | **Submission-ready.** Evidence for the grader | `evaluations/REPORT.md` on three tenders, ADR per decision, architecture doc, user guide with three walkthroughs, Playwright smoke test green, critique applied, README and `project.md` trimmed (E7; S7.1 reuses the S3.2.3 matcher from Increment 2) | pending | — |
| 6 | Stretch: provider choice and second parser | Bid runs on a user's own key with the provider labelled in `/dev/costs`, falls back with a warning when the key is removed; Docling switchable (S5.4–S5.6, S4.6.4, S2.1.2) | pending | — |
| 7 | Live EU instance (optional) | Vercel + Railway/Fly EU + Supabase EU pass the smoke test (E8) | pending | — |

The line between 5 and 6 is the submission line. Nothing below it is started until Milestone 5 is complete.

---

## Delivery order (one developer, one backlog)

Lanes A–E survive only as tags on stories in the roadmap's story board; they do not mean parallel capacity. One person builds this, so the plan is a single ordered backlog cut into increments. Each increment ends with something a user can click through and a short recorded demo, which also supplies the user guide's screenshots. Content and documentation stories are *wait-fillers*: they are done while an LLM run, a download, or a Docker build is in progress, never as a separate phase.

| Inc | Demoable goal | Stories, in order | Wait-fillers |
|---|---|---|---|
| 0 | Core bet tested | S6.1 (DE pack only), SP.1 | — |
| 1 | Upload a tender, see its requirement list in the browser | S0.1.1, S0.1.2, S0.1.3, S0.1.4, S0.2.1, S0.2.2, S0.2.3, S0.3.2, S0.3.3, S0.4.1, S0.4.2, S2.1.1, S2.1.3, S2.2.1, S2.2.2, S2.2.3, S2.3.2, S3.1.1, S1.1.1, S1.1.3, S3.2.1, S4.0.1 (design canvas, user confirms), S4.1.2, S4.2.2, S4.5.1 (all but the matrix-row criterion) | S6.1 (FR pack), S6.2, S7.2 |
| 2 | Matrix in the browser | S1.1.2, S1.4.1 (with the tools that exist), S2.4.1, S2.4.2, S3.3.1, S3.3.2, S4.5.1 (matrix-row criterion) | S6.3, S6.4, then S3.2.3, S7.2 |
| 3 | Review round-trip | S3.4.1, S3.4.2, S3.4.3, S3.4.4, S2.4.3, S4.5.2, S4.5.3, S4.4.1 | S6.5, S7.3, S7.2 |
| 4 | Every graded requirement covered | S0.3.1, S4.1.1, S4.2.1, S1.2.1, S1.2.2, S3.2.2, S4.3.1, S1.3.1, S2.3.1, S5.3, S2.3.3, S3.5.1, S4.6.1, S5.1, S5.2, S4.6.2, S4.6.3 | S7.2 | *(S4.4.1 moved to Increment 3 — 17 stories, not 18)* |
| 5 | **Submission-ready** | S7.1, S7.7, S7.4, S7.5, S7.6 | S7.2 |
| 6 | Stretch | S5.4, S5.5, S5.6, S4.6.4, S2.1.2 | S7.2 |
| 7 | Optional | S8.1, S8.2 | S7.2 |

**Integration points.**
- I1  S1.4.1 registry + S2.4.2 RAG tools → S3.3.1 `check_reqs` uses real tools (Increment 2).
- I2  S3.1.1 `GET /bids/{id}` shape → S4.5.1 workspace polling (Increment 1).
- I3  S3.4.2 interrupt/resume → S4.5.3 confirm flow (Increment 3).
- I4  S6.3 demo docs → S2.4.3 seed script → first end-to-end run on the demo company (Increment 3).
- I5  S6.4 labels → S3.2.3 recall script → S7.1 eval report (Increments 2 and 5).

**Critical path:** SP.1 → E0 (minus auth) → F2.1, F2.2 → S3.2.1 → S4.0.1 (design confirmed) → F3.3 → F3.4 → S4.5.2 → S7.1 → S7.4.

**Cadence.** One increment per sprint. A sprint ends with a recorded demo of the increment's goal, a one-paragraph retro in `docs/decisions.md` (what slipped and why), and a re-forecast of the remaining increments from measured velocity. Sizes in this plan are estimates; the forecast after Increment 1 replaces them.

**Effort.** 75 stories: 19 S, 50 M, 6 L, plus continuous ADRs. At the plan's own ranges that is 87 to 205 hours against the brief's 18-hour estimate. Time is not a hard constraint (settled decision), but Increments 0–5 are the only ones the grade depends on.

**Re-forecast, 2026-09-14** (the cadence's re-forecast after Increments 1 and 2; the retro is in `docs/decisions.md`). Measured: **43 of 75 stories in five calendar days**, 2026-09-10 to 2026-09-14, covering Increments 0, 1, 2 and S2.4.3. Remaining to the submission line: Increment 3 ~1 day, Increment 4 ~2–3 days (widest, 18 stories, includes the first real sign-in), Increment 5 ~1 day — **~4–5 calendar days to Milestone 5**. This replaces the hour ranges above *as the working forecast only*: it is agent-assisted calendar time with one reviewer and is not comparable to solo developer-hours, so it neither confirms nor refutes the 87–205 h estimate. **R5 is closed as a risk and reopened as a measurement.** The forecast assumes no repeat of the verification work that dominated Increment 2, which is the assumption most likely to be wrong.

---

## Risks

| # | Risk | Likelihood / impact | Mitigation | Owner |
|---|---|---|---|---|
| R1 | Extraction recall on real DE/FR tenders stays below 0.9 | Medium / High | SP.1 first; section size, model, and dedupe tuned before Increment 1; threshold in settings; measured figure reported honestly in `REPORT.md` | SP.1, S3.2.3 |
| R2 | Fixture tender documents not downloadable anonymously (national platforms require registration) | Medium / High | **Closed 2026-09-10 for DE, see ADR-0001.** The original fallback ("notices whose documents are attached on TED itself") does not exist: 0 of 100 sampled German CPV-72 `cn-standard` notices hosted documents on `ted.europa.eu`. The DE pack was instead fetched once by hand from e-Vergabe, which is anonymous under §41 Abs. 1 VgV — a cookie round-trip, no account. FR follows the same route. Remaining fallback if a platform does demand registration: commit that country's notice PDF alone, whose eForms BT-750 fields carry the selection criteria as prose. | S6.1 |
| R3 | pgvector indexes (HNSW, IVFFlat) cap at 2000 dimensions; the default embedding has 3072 | ~~High~~ / Low | **Closed 2026-09-10 (ADR-0004).** The default embedding is now `openai/text-embedding-3-small` at **1536 dims**, under the cap, so HNSW/IVFFlat are usable and the dimension problem does not arise. Switched before anything was embedded, so it cost nothing. If 3-large (3072) is ever chosen back on S7.1 evidence, the escape route is a `halfvec` index — not `baai/bge-m3`, which 404s on this account. | S2.2.1 |
| R4 | Supabase free-tier project pauses after a week idle and the demo fails on review day | Medium / Medium | Wake it the day before review; Compose stack as fallback demo; noted in the user guide | S7.4, S8.1 |
| R5 | Effort is 87–205 h against an 18 h brief and velocity is unknown | High / Medium | Increments 0–5 are the submission line; re-forecast after Increment 1 | this table |
| R6 | Prompt-tuning loops blow the estimate on S3.2.1 and S3.3.1 | High / Medium | Time-box each tuning round to 1 h; fake-model tests protect the row shape; accept the measured recall | S3.3.2 |
| R7 | Magic-link email in development and in Playwright | Medium / Medium | Dev auth mode until Increment 4; pre-issued session or test OTP in S7.7 | S0.3.1, S7.7 |
| R8 | TED API rate limits or schema drift | Low / Medium | Recorded responses in tests; one retry then a typed error | S1.2.1 |
| R9 | Bid run latency: 100 pages, fan-out at concurrency 5 | Medium / Medium | 10-minute budget in S3.1.1; stage shown by polling; concurrency and section size in settings | S3.1.1 |
| R10 | Medium 5 (feedback loop) only half met because learning was cut | High / Low | Claim it as partial; the graded threshold is cleared without it | coverage table |

---

## Graded optional tasks (honest mapping)

The brief awards maximum points for at least 2 medium and 1 hard optional task. This table replaces the coverage table in `project.md` §5 when S7.6 trims it.

| Brief item | Status | Stories |
|---|---|---|
| Easy 1 LLM critique | Must | S7.5 |
| Easy 2 personality / tone | Must | S4.2.1, S3.4.1 |
| Easy 3 choose from a list of LLMs | Must | S5.1, S4.6.2 |
| Easy 4 temperature and max-tokens settings | Must | S0.3.2, S4.6.2 |
| Easy 5 interactive help or guide | Not claimed | user guide only (S7.4) |
| Medium 1 token usage and cost | Must | S5.2 |
| Medium 2 long- and short-term memory | Must | S0.2.2, S2.4.1, S3.5.1 |
| Medium 3 tool calling an external API | Must | S1.1.2, S1.2.2, S1.3.1 |
| Medium 4 authentication and personalisation | Must | S0.3.1, S2.4.1 |
| Medium 5 feedback loop that improves the agent | **Partial**: ratings stored, learning cut | S4.6.3 |
| Medium 6 five tools with enable/disable UI | Must | S1.4.1, S2.4.2, S4.6.2 |
| Medium 7 multi-model | Must via vendor slugs; BYOK is stretch | S5.1 (Must), S5.4–S5.6 (Could) |
| Medium 8 security guard, dev/user separation | Must | S2.3.1–S2.3.3, S4.6.2 |
| Hard 1 agentic RAG | Must | S3.3.1 |
| Hard 2 observability | Must | S0.3.3 |
| Hard 3 evaluation report | Must | S7.1 |
| Hard 4 learns from feedback | Not claimed (cut) | — |
| Hard 5 external data sources | Must | E1 |

---

## Verification

- Increment 0: `backend/scripts/spike_extract.py` output and the go/pivot decision are in `docs/decisions.md`.
- `uv run pytest` green with fakes (`GenericFakeChatModel`, fake TED/eCertis/Frankfurter clients); `uv run pytest -m live` runs the full graph on the DE fixture and stops at the interrupt.
- Manual e2e: seed demo company → search TED for a FR CPV 72 notice → upload fixture pack → wait for matrix → confirm review → dashboard shows final verdict; "ask the tender" answers with page citations in German.
- `uv run scripts/run_eval.py` produces `evaluations/REPORT.md` with recall, faithfulness, translation adequacy for the 3 golden tenders.
- Playwright smoke test for login → bid → confirm.
- Cost per DE fixture bid visible in `/dev/costs` (OpenRouter-reported) and under $2.50; the run reaches `awaiting_review` within 10 minutes (S3.1.1).
- `uv run scripts/recall.py` (S3.2.3) reports mandatory-requirement recall ≥ 0.9 on the DE golden tender.
- CI (S0.1.4) is green on `main` with backend coverage ≥ 80%.
- BYOK: store an invalid OpenAI key → verification fails, nothing saved; store a valid key → hint shown, run a bid → LangSmith trace shows the OpenAI model and `/dev/costs` labels the row `openai`; delete the key → next bid falls back to the app OpenRouter route with a visible warning.
