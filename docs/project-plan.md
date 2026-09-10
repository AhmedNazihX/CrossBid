# Crossbid — project plan (Epics → Features → Stories)

> Status: **approved 2026-09-10, implementation not started**. Source of truth for scope, layout, and build order. Supersedes `project.md` §8; `project.md` §2–§5 will be trimmed to match at the start of E0. Decisions come from the 41-question grill session of 2026-09-10.

## Context

Sprint capstone (brief in `135.md`): build a useful AI agent with LangGraph, OpenAI, and Next.js. The project is **Crossbid**, a cross-border EU tender go/no-go agent for SMEs (spec in `project.md`). A grill session on 2026-09-10 settled 41 scope and design questions and verified the external dependencies live. This plan replaces the delivery plan in `project.md` §8 and narrows §2–§4 to the agreed vertical slice. Time is not a hard constraint (user's Q1), so the extra time goes into quality of the slice, not breadth.

**Vertical slice:** a fictional German IT GmbH uploads its document pack, picks a TED notice (DE or FR), uploads the tender documents, and gets a bilingual compliance matrix and a rules-based go/no-go verdict that a human reviews and confirms in a Next.js workspace. Plus "ask the tender" chat.

## Settled decisions (from the grill; do not reopen)

**Cut from course build:** response drafting, second interrupt, DOCX export, OCR, `next-intl`, PDF quote highlighting (jump-to-page only), APScheduler, `deadline_calculator`, `web_search_buyer`, Ragas, RLS-as-isolation claim, feedback few-shot injection, Polish/Dutch tenders, LLM profile extraction, numeric verdict score.

**Kept / decided:**
- Intake = TED notice via API (structured fields, no LLM) + manual upload of procurement documents. TED `document-url-lot` links land on national platforms; never fetch them (no scraping).
- eCertis is criterion-centric: tool is `ecertis_evidence_lookup(criterion_id, bidder_country)`. EU criteria list and DE/FR evidences cached as JSON in repo.
- Five tools: `company_rag_search`, `tender_rag_search`, `search_ted`, `ecertis_evidence_lookup`, `currency_convert` (Frankfurter). Tool registry with manifests + enable/disable toggles.
- LLM access: **OpenRouter is the single provider** (the only key the user holds). Default slugs `openai/gpt-5.6-terra` for extraction/translation and `openai/gpt-5.6-luna` for classification, chat, and the injection guard. Verified 2026-09-10: both expose `structured_outputs`, `response_format`, `tools` through OpenRouter at the same prices as OpenAI direct ($2/$12 and $0.20/$1.20 per 1M). Multi-model has two layers: (1) switching vendor slugs inside OpenRouter (`openai/`, `anthropic/claude-sonnet-5`, `google/…`) from the dev panel; (2) **bring your own key**: a user can store their own OpenAI and/or Anthropic key (or their own OpenRouter key) in Settings and pick which provider their company's bids run through. Keys are encrypted at rest (Fernet, `APP_ENCRYPTION_KEY`), scoped by `company_id`, verified with a one-token test call on save, never returned to the client (last-4 hint only), never logged. Embeddings always run through the app's OpenRouter route so a company's corpus stays in one vector space. Slugs and per-provider role defaults live in one settings file.
- Extraction: map over page-tagged sections (5–8 pages) with structured output, dedupe pass. Extractor assigns nullable `ecertis_criterion_id` from the ~56 EU criteria enum.
- `check_reqs`: LangGraph `Send` fan-out per requirement, concurrency ~5, max 4 tool calls each, returns `MatrixRow`. This is the agentic (ReAct) part; outer graph is a deterministic workflow with one interrupt.
- Verdict: rules only. Unmet mandatory or exclusion ground ⇒ `no_go` with gap list; else `go_with_open_items` or `go`.
- Interrupt/resume: `interrupt()` with matrix+verdict; `Command(resume={row_edits, decision})` → apply edits → re-run scorer → record override if reviewer disagrees → END.
- Persistence: `PostgresSaver` + `PostgresStore` (pgvector) on Supabase EU; **direct connection locally, session pooler in deployment, never transaction pooler**. App read-model tables written after `score_verdict` and after resume.
- Storage: Supabase Storage bucket, prefix per company, signed URLs. Chunks 800 tokens/100 overlap, embeddings via OpenRouter's `/embeddings` endpoint: `openai/text-embedding-3-large` default (3072 dims, $0.13/1M), `baai/bge-m3` as the cheap multilingual switch (1024 dims, $0.01/1M; changing it means re-embedding and a column dimension change). Vector-only retrieval.
- Parsing: `pymupdf4llm` default; Docling (`do_ocr=False`) behind the same `Parser` interface, switchable. Pages with no text flagged "not read".
- Guards: regex/heuristic scan on every chunk → flagged chunks to luna yes/no → excluded and listed to reviewer; document text wrapped in delimited data blocks; `slowapi` rate limit on bid creation; schema validation on tool outputs; scorer refuses `go` without evidence on mandatory rows.
- Auth: Supabase Auth magic link, JWT verified in FastAPI, single company per user. Developer role = env-var email list. `/dev` route gated on both sides.
- Frontend calls FastAPI directly with bearer token; CORS locked; TS types via `openapi-typescript`; poll `/bids/{id}` every 2 s.
- "Ask the tender": separate thread `bid:{id}:chat`, ReAct agent with `tender_rag_search`, `company_rag_search`, `get_matrix`.
- Tenant isolation: application-level `company_id` on every query and Store namespace.
- Observability: LangSmith for traces. Cost figures come from OpenRouter's per-generation usage accounting (`usage: {include: true}` returns cost in the response), not from LangSmith price tables, so any vendor slug is priced correctly. Eval: DeepEval only (GEval faithfulness + translation adequacy, custom recall metric) with the judge wired to OpenRouter through DeepEval's OpenAI-compatible custom model. Golden set: 3 tenders (DE, FR, EN), LLM-assisted labels hand-verified.
- Per-user `language` (default `de` for demo) and `tone` settings applied to explanations and chat. UI chrome English.
- Fixtures: real DE and FR tender packs committed under `backend/tests/fixtures/tenders/{de,fr}/` with `SOURCES.md`; <15 MB each.
- Deployment: Docker Compose first; Vercel + Railway/Fly EU + Supabase EU only at the end.

---

## Repository layout

Two top-level folders, `backend/` and `frontend/`, each a self-contained project with its own dependency file, Dockerfile, tests, and deploy target. No shared package, no monorepo tooling. The Pydantic models in the backend are the single schema source; the frontend consumes them as generated TypeScript types. Inside the API, folders are layered so that dependencies point one way: `routers → agent/ingestion/readmodel → tools/reference/memory/guards → models/db/settings`. Nothing below imports from above.

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
│   │   │   ├── embeddings.py         OpenRouter embeddings client (text-embedding-3-large default) + pgvector insert/search scoped by company/bid
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
├── frontend/                         Next.js 15 App Router · TypeScript · Tailwind · shadcn/ui — its own package.json, Dockerfile
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
│   ├── components/                   matrix/, pdf/, verdict/, ui/ (shadcn)
│   └── lib/                          api.ts (generated by openapi-typescript), supabase.ts, polling hook
├── infra/
│   ├── docker-compose.yml            postgres+pgvector, api, web
│   └── .env.example
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
- `company_chunks` / `tender_chunks(id, document_id, company_id, bid_id, page, text, embedding vector(3072))`
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

**Conventions.** An *epic* states an outcome, why it matters, and an observable "done when". A *feature* is a capability plus the benefit it delivers. A *story* is written from the person who benefits (*As a …, I want …, so that …*), followed by acceptance criteria in Given / When / Then form, a size, and hard prerequisites (`needs`). Implementation pointers sit in *Notes* so the story itself stays about behaviour. Sizes: **S** about 1 h, **M** 1–3 h, **L** 3–6 h.

**Personas.**
- **Bidder** — Sabine, owner and sales lead of a 25-person German IT services GmbH. Bids domestically, wants to bid in France. Not a procurement professional; reads German and some English, no French.
- **Reviewer** — the person who confirms or overrides the agent's verdict. In v1 this is Sabine or a colleague; the role is kept separate because the review step is the product's safety boundary.
- **Operator** — whoever runs the deployment and tunes models, tools, and prompts in the developer panel.
- **Maintainer** — the team building Crossbid. Used only for enabler stories that have no end-user surface of their own.

---

### E0 · Foundations — Lane A, serial gate

**Goal.** A running skeleton in which a signed-in user reaches an authenticated API backed by Postgres with LangGraph persistence.
**Why.** Every lane builds on it, and the API contract (F0.4) lets frontend work start in parallel.
**Done when.** `docker compose up` starts API, web, and database; a magic-link login yields a token accepted by `GET /companies/me`; an empty graph run leaves a checkpoint that survives a restart; `frontend/lib/api.ts` is generated from the live OpenAPI schema.

**F0.1 Repository and tooling** — each app starts and tests with one command, independently of the other.

- **S0.1.1** (S) *As a maintainer, I want `backend/` and `frontend/` scaffolded as independent projects, so that either can be developed, tested, and deployed on its own.*
  - Given a fresh clone, when I run `uv sync` in `backend/` and `npm install` in `frontend/`, then each succeeds without the other's toolchain installed.
  - Given either folder opened alone, then it contains its own dependency file, Dockerfile, and README section.
  - Notes: `uv init` with Python 3.12; `create-next-app` with TypeScript, Tailwind, App Router; shadcn/ui init.
- **S0.1.2** (M) *As a maintainer, I want one command to start Postgres with pgvector, the API, and the web app, so that local development mirrors the deployed topology.* `needs S0.1.1`
  - Given `.env` copied from `infra/.env.example`, when I run `docker compose up`, then the API answers on :8000, the web app on :3000, and Postgres has the `vector` extension.
  - Given the README, then `dev`, `test`, `migrate`, and `eval` tasks are documented and work.
- **S0.1.3** (S) *As a maintainer, I want linting, type checks, and test runners configured, so that quality checks run identically on every machine.* `needs S0.1.1`
  - Given the empty skeleton, when I run `ruff`, `pyright`, `pytest`, and `npm run lint`, then all pass.
  - Given a commit, then a pre-commit hook runs ruff and prettier.

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

### E1 · Reference data and external clients — Lane A

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

**F1.4 Tool registry** — operators decide which tools the agent may call.

- **S1.4.1** (M) *As an operator, I want to enable or disable tools without redeploying, so that I can constrain what the agent may reach.* `needs F1.1–F1.3`
  - Given `enabled_tools` in settings, when the graph builds, then only those tools are bound.
  - Given a tool module, then it exports `MANIFEST` with name, description, `external`, and `default_enabled`, and `GET /dev/settings` lists all manifests.

---

### E2 · Ingestion and company memory — Lane B

**Goal.** Every PDF a bidder uploads becomes page-cited, guarded, searchable text, and the company's facts are remembered.
**Why.** The matrix is only as trustworthy as the evidence it can find and cite.
**Done when.** The demo GmbH pack is seeded; a French query for information-security certification returns the German ISO 27001 page; the adversarial fixture is flagged.

**F2.1 Parsing and chunking** — page-faithful text from PDFs.

- **S2.1.1** (M) *As a bidder, I want my PDFs read page by page, so that every finding can point to a page I can open.* `needs S0.1`
  - Given a text PDF, when parsed, then the result has one entry per page.
  - Given a page without extractable text, then its number appears in `unread_pages` and parsing continues.
- **S2.1.2** (M) *As a maintainer, I want Docling available behind the same parser interface, so that table-heavy tenders can be re-parsed by changing a setting.* `needs S2.1.1`
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

- **S2.4.1** (M) *As a bidder, I want to record my company's country, legal form, turnover, and certificates with expiry dates, so that requirements are checked against facts I control.* `needs S0.3.1`
  - Given the form, when I save, then `GET /companies/me` returns the profile and the Store namespace `profile/{company_id}` is written.
  - Given a certificate whose expiry has passed, then it is flagged on the profile.
- **S2.4.2** (M) *As a maintainer, I want retrieval tools over company and tender chunks, so that the agent gathers evidence itself.* `needs S2.2.1`
  - Given a query, then each tool returns document id, page, quote, and score for the top results, scoped by company and bid.
- **S2.4.3** (M) *As a maintainer, I want a one-command seed of the demo GmbH, so that any environment can run the walkthrough.* `needs S6.3`
  - Given an empty database, when the seed runs, then the company, profile, and all documents exist and are `ready`; a second run changes nothing.

---

### E3 · Agent graph — Lane B

**Goal.** A bidder receives a page-cited bilingual requirement matrix and a rules-based go/no-go that pauses for human review and continues with the reviewer's decisions.
**Why.** This is the product: judgement work before a bid is written, with a human holding the final word.
**Done when.** The DE fixture run stops at the interrupt with at least 90% of golden mandatory requirements found; a review resumes to a final state; every listed failure mode is handled.

**F3.1 Run lifecycle** — start a bid and follow it.

- **S3.1.1** (M) *As a bidder, I want to start a bid and follow its progress, so that I know the agent is working and when it needs me.* `needs S0.2.2`
  - Given a notice number and ready documents, when I post a bid, then 202 with an id and the graph runs in the background.
  - Given polling, then status is one of `queued, parsing, extracting, checking, scoring, awaiting_review, finalizing, done, failed`.
  - Given an API restart mid-run, then the run resumes from its last checkpoint.

**F3.2 Requirement extraction** — everything the tender asks, typed, cited, and explained.

- **S3.2.1** (L) *As a bidder, I want every requirement listed with its type, category, page, and quote, and explained in German, so that I understand a French tender without reading 100 pages of French.* `needs S1.1.3, S2.3.2`
  - Given a parsed tender, when extraction runs, then each requirement has kind, category, page, source quote, translation, and a nullable criterion id.
  - Given the DE golden tender, then recall on mandatory requirements is at least 0.9.
  - Given an extracted row without a quote, then it is rejected and re-asked once.
  - Notes: sections of 5–8 pages, structured output per section, dedupe by quote similarity and page proximity.
- **S3.2.2** (S) *As a bidder, I want the buyer's structured notice data used directly, so that the deadline, languages, and stated criteria are never mis-read.* `needs S1.2.1`
  - Given a TED notice, then its criteria descriptions, submission language, and deadline become requirements tagged `source: notice` before LLM extraction, and the deadline is stored on the bid.

**F3.3 Per-requirement checking** — the agentic core.

- **S3.3.1** (L) *As a bidder, I want each requirement checked against my documents and, where relevant, against the German equivalent evidence, so that I see exactly what I can prove and what I cannot.* `needs S1.4.1, S2.4.2`
  - Given the requirement list, when checking runs, then each requirement yields a matrix row with status in `met, met_via_equivalent, not_met, unclear, needs_document`, evidence quotes with pages, eCertis evidence when a criterion id is set, and a rationale.
  - Given any row with status `met`, then it has at least one evidence quote.
  - Given the run, then no requirement uses more than 4 tool calls and no more than 5 run concurrently.
  - Notes: LangGraph `Send` fan-out; a small ReAct loop per requirement.
- **S3.3.2** (M) *As a maintainer, I want deterministic tests for every status branch, so that a prompt change cannot silently break the matrix.* `needs S3.3.1`
  - Given a fake model scripted for each of the five statuses, then the row shape and tool-call limits are asserted.

**F3.4 Verdict, interrupt, review** — the human decides.

- **S3.4.1** (M) *As a bidder, I want a clear go or no-go with the exact gaps in my language, so that I can decide in minutes.* `needs S3.3.1`
  - Given any mandatory row `not_met` or any exclusion ground unmet, then the verdict is `no_go` with the gap list.
  - Given mandatory rows `unclear`, then the verdict is `go_with_open_items` naming them.
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
  - Given a schema violation, then one re-ask, then the row is `unclear`.
  - Given no eCertis entry, then the row is flagged for the reviewer.
  - Given an expired certificate used as evidence, then a warning with the date.

**F3.5 Ask the tender** — questions with citations.

- **S3.5.1** (M) *As a bidder, I want to ask questions about the tender and my matrix and get cited answers in German, so that I can clarify a point without re-reading.* `needs S2.4.2, S3.4.3`
  - Given a question, then the answer cites document and page.
  - Given nothing relevant in the documents, then the answer says so instead of guessing.
  - Notes: separate thread `bid:{id}:chat` with `tender_rag_search`, `company_rag_search`, `get_matrix`.

---

### E4 · Web app — Lane C

**Goal.** A non-procurement user completes onboarding, starts a bid, reviews the matrix beside the source document, and confirms a verdict without training.
**Why.** The review step is the product's safety boundary; it has to be fast and legible for someone who is not a lawyer.
**Done when.** The Playwright smoke test passes and a first-time user completes the DE walkthrough from the user guide unaided.

**F4.1 Shell and sign-in** — a place to work, in plain English.

- **S4.1.1** (M) *As a bidder, I want to sign in by clicking a link in my email and land on my dashboard, so that I start working within a minute.* `needs S0.4.2`
  - Given the login page, when I enter my email, then a link arrives and following it opens the dashboard with a persisted session.
  - Given a protected route without a session, then I am redirected to login.
- **S4.1.2** (S) *As a bidder, I want a consistent layout with clear navigation, so that I always know where bids, company, and settings are.* `needs S4.1.1`
  - Given any page, then navigation shows Dashboard, Company, Settings, and New bid; empty states explain the next step.

**F4.2 Onboarding** — tell Crossbid about the company.

- **S4.2.1** (M) *As a bidder, I want to fill in my company's country, legal form, turnover, and certificates, so that checks run against my facts.* `needs S4.1.1`
  - Given the form, when I save, then values persist and validation errors name the field.
- **S4.2.2** (M) *As a bidder, I want to upload company documents by type and watch them become ready, so that I know the agent can use them.* `needs S4.1.1`
  - Given a file, when I upload it with a type, then a row shows status until `ready` or `failed` with a reason and unread-page count.

**F4.3 New bid** — from tender search to a running check.

- **S4.3.1** (M) *As a bidder, I want to search TED, pick a notice, upload its documents, and start the check in one flow, so that I never leave the app to begin.* `needs S4.1.1`
  - Given search filters, then results show buyer, deadline, and languages, and a link to the platform hosting the documents.
  - Given a picked notice, then Start is disabled until at least one tender document is `ready`.

**F4.4 Dashboard** — the state of every bid at a glance.

- **S4.4.1** (M) *As a bidder, I want to see each bid's status, verdict, days to deadline, and open items, so that I know what needs me today.* `needs S4.1.1`
  - Given bids, then each row shows a verdict badge, a deadline countdown in the buyer's time zone, and the count of open items.

**F4.5 Bid workspace** — verify every claim in one click.

- **S4.5.1** (L) *As a reviewer, I want the source PDF beside the matrix with jump-to-page from every citation, so that I can verify a claim without searching.* `needs S3.1.1`
  - Given a citation, when I click it, then the viewer opens that page.
  - Given a running bid, then the page polls and shows the current stage.
- **S4.5.2** (L) *As a reviewer, I want to change a row's status, give a reason, attach a document, and switch each row between French and German, so that my judgement is recorded next to the agent's.* `needs S3.4.3`
  - Given a row, when I edit status or attach a document, then the change is held locally until I confirm and the agent's original stays visible.
  - Given a row with eCertis evidence, then a card names the German document and issuer.
  - Given flagged chunks or unread pages, then a notice lists them.
- **S4.5.3** (M) *As a reviewer, I want to confirm the verdict or override it with a reason, so that nothing proceeds without my decision.* `needs S3.4.2`
  - Given my edits, when I confirm or override, then the review is submitted once and the final state is shown.

**F4.6 Chat, developer panel, settings** — the supporting surfaces.

- **S4.6.1** (M) *As a bidder, I want to ask questions about the tender and see cited answers, so that I clarify without re-reading.* `needs S3.5.1`
  - Given a question, then the answer shows citations that jump to the page.
- **S4.6.2** (M) *As an operator, I want a developer panel to pick models per role, tune temperature and max tokens, edit the system prompt, toggle tools, and see cost per bid and node, so that I tune the agent without touching code.* `needs S5.2`
  - Given a non-developer account, then the route is not reachable.
  - Given a change, when saved, then the next bid uses it.
- **S4.6.3** (S) *As a bidder, I want to rate a matrix row or chat answer and add a comment, so that my corrections are kept for later improvement.*
  - Given a thumbs rating, then it is stored with the row or answer id.
- **S4.6.4** (M) *As a bidder, I want to add my own OpenAI, Anthropic, or OpenRouter key and choose which one my bids use, so that I control the provider and the bill.* `needs S5.4`
  - Given a key, when I press Test and save, then it is verified and only the last four characters are shown afterwards.
  - Given an invalid key, then nothing is saved and the error names the provider.
  - Given the page, then it states that embeddings always use the app's route. Language and tone are set on the same page.

---

### E5 · Multi-model, bring your own key, observability, cost — Lane A

**Goal.** Operators choose models, users may bring their own keys, and every run's cost is visible and attributed.
**Why.** Model choice and cost transparency are graded, and a bidder paying their own provider is a real deployment path.
**Done when.** A bid runs on a user's OpenAI key with the correct provider in the cost view, and falls back with a warning when the key is removed.

- **S5.1** (M) *As an operator, I want to switch the model for each role among OpenAI, Anthropic, and Google slugs on OpenRouter, so that I can compare quality and cost.* `needs S1.4.1`
  - Given a slug change, then the next bid uses it and structured output still validates.
- **S5.2** (M) *As an operator, I want tokens and cost per bid and per node, so that I can see where the money goes.* `needs S5.6`
  - Given a finished bid, then `GET /dev/costs` shows tokens and cost per node with the provider used.
- **S5.3** (S) *As a reviewer, I want flagged chunks confirmed by a cheap model, so that false positives from heuristics do not hide legitimate text.* `needs S2.3.1`
  - Given a heuristically flagged chunk, then the classifier's yes/no is stored with it.
- **S5.4** (M) *As a bidder, I want my provider key stored securely and verified when I save it, so that I can trust it is never exposed.* `needs S0.2.3, S0.3.1`
  - Given a key, when saved, then a one-token call verifies it first, it is encrypted at rest, and only a last-four hint is ever returned.
  - Given logs and traces, then the key never appears.
  - Given repeated attempts, then the endpoint is rate-limited.
- **S5.5** (M) *As a bidder, I want my bids to run on the provider I selected, and to fall back safely if my key stops working, so that a broken key never blocks a deadline.* `needs S5.4`
  - Given an active own key, then the model factory uses it for that company.
  - Given a missing or invalid key, then the bid runs on the app route and shows a warning.
- **S5.6** (S) *As an operator, I want costs for direct providers computed from tokens and a price table, so that every provider is accounted for.* `needs S5.5`
  - Given a direct-provider run, then `llm_usage` rows carry tokens and computed cost; OpenRouter runs carry the reported cost.

---

### E6 · Content: fixtures, demo company, golden set — Lane D

**Goal.** Real, verifiable material to build and judge against.
**Why.** Without real tenders and labelled requirements, no quality claim can be made.
**Done when.** Two real tender packs and one EN notice are committed with sources, the demo GmbH pack exists, and the golden set is labelled and verified.

- **S6.1** (M) *As a maintainer, I want one German and one French CPV 72 tender pack downloaded from platforms that allow anonymous access and committed with their sources, so that every test and demo uses real documents.*
  - Given `tests/fixtures/tenders/{de,fr}/`, then each holds the pack under 15 MB and `SOURCES.md` lists the TED number and platform URL.
- **S6.2** (M) *As a maintainer, I want one English TED notice for the golden set, so that recall is measured on a language every grader can read.*
- **S6.3** (L) *As a bidder, I want a believable document pack for the demo GmbH, so that the walkthrough shows real evidence rather than placeholders.*
  - Given the pack, then it contains a register extract, tax certificate, ISO 27001 certificate, liability insurance, three past-bid summaries, two reference letters, and `profile.yaml`, all in German.
- **S6.4** (L) *As an evaluator, I want each golden tender's requirements labelled with category, kind, page, quote, and criterion, so that extraction can be scored.* `needs S6.1, S6.2`
  - Given the YAML, then labels were produced with LLM assistance and each was verified by a human, and the method is stated in the file header.
- **S6.5** (S) *As a maintainer, I want PDFs with planted instructions, so that the injection guard has something to catch.*

---

### E7 · Evaluation and documentation — Lane E

**Goal.** Evidence of quality, and documentation a reviewer can follow without the author present.
**Why.** The course grades understanding and reflection as much as the build.
**Done when.** `evaluations/REPORT.md` reports the metrics on three tenders, every decision has an ADR, and the user guide walks through three bids.

- **S7.1** (M) *As an evaluator, I want requirement recall, citation faithfulness, and translation adequacy measured on the golden set, so that quality is a number, not a claim.* `needs E3, S6.4`
  - Given the eval script, then `REPORT.md` shows the three metrics per tender, and the judge model is from a different vendor than the model under test.
- **S7.2** (S each, continuous) *As a maintainer, I want an ADR for every settled decision, written when the decision lands, so that the reasoning survives the session that made it.*
- **S7.3** (M) *As a reviewer of the project, I want an architecture document with the graph and a plain statement of what is a workflow and what is an agent, so that I can judge the design.* `needs F3.4`
- **S7.4** (M) *As a bidder, I want a user guide with three worked examples, so that I can run my first bid without help.* `needs E4`
  - Given the guide, then it covers a German domestic bid, a French cross-border bid, and a no-go case, each with screenshots.
- **S7.5** (S) *As a maintainer, I want an LLM critique of usability, security, and prompt engineering with the fixes applied, so that obvious gaps are closed before review.*
- **S7.6** (S) *As a maintainer, I want the README quick start and `project.md` trimmed to what was built, so that the repository tells one story.*
- **S7.7** (M) *As a maintainer, I want a browser smoke test of login, bid, and confirm, so that the critical flow is guarded against regressions.* `needs E4`

---

### E8 · Deployment — optional, last

**Goal.** A live EU-hosted instance for the portfolio.
**Done when.** The web app on Vercel reaches the API on Railway or Fly in an EU region through the session pooler, and the smoke test passes against it.

- **S8.1** (M) *As a bidder, I want to use Crossbid from a public URL, so that I can try it without installing anything.* `needs all`

---

## Parallelism map

```
Day 0 ─ E0 Foundations (serial, gate) ─────────────────────────┐
                                                               │
   Lane A  E1 reference/TED/currency/registry → E5 multi-model, costs
   Lane B  E2 ingestion, guards, memory → E3 graph (mocks E1 tools until ready) → S3.5 chat
   Lane C  E4 web shell + onboarding + new-bid (from S0.4.2 contracts, mock API) → workspace (needs S3.4.2) → chat/dev
   Lane D  E6 fixtures, demo docs, golden set  ← starts before E0 is finished; zero code dependency
   Lane E  E7 ADRs and architecture doc alongside; eval run after E3 + S6.4; user guide + Playwright after E4

Integration points
   I1  S1.4.1 registry + S2.4.2 RAG tools → S3.3.1 check_reqs uses real tools
   I2  S3.1.1 GET /bids/{id} shape → S4.5.1 workspace polling
   I3  S3.4.2 interrupt/resume → S4.5.3 confirm flow
   I4  S6.3 demo docs → S2.4.3 seed script → first end-to-end run
   I5  E3 + S6.4 → S7.1 eval report
```

**Critical path:** E0 → E2 (parser, chunks, embeddings) → E3 (extract, check, score, interrupt) → S4.5 workspace → S7.1 eval → S7.4 guide.

**What runs in parallel for a solo developer:** E6 content work fills every wait (LLM runs, downloads, Docker builds). E4 shell/onboarding/new-bid can be built against mocked API responses whenever backend work stalls. ADRs are written the moment a decision is implemented, never batched.

---

## Verification

- `uv run pytest` green with fakes (`GenericFakeChatModel`, fake TED/eCertis/Frankfurter clients); `uv run pytest -m live` runs the full graph on the DE fixture and stops at the interrupt.
- Manual e2e: seed demo company → search TED for a FR CPV 72 notice → upload fixture pack → wait for matrix → confirm review → dashboard shows final verdict; "ask the tender" answers with page citations in German.
- `uv run scripts/run_eval.py` produces `evaluations/REPORT.md` with recall, faithfulness, translation adequacy for the 3 golden tenders.
- Playwright smoke test for login → bid → confirm.
- Cost per DE fixture bid visible in `/dev/costs` (OpenRouter-reported) and under $2.50.
- BYOK: store an invalid OpenAI key → verification fails, nothing saved; store a valid key → hint shown, run a bid → LangSmith trace shows the OpenAI model and `/dev/costs` labels the row `openai`; delete the key → next bid falls back to the app OpenRouter route with a visible warning.
