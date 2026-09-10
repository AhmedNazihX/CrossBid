# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## State of the repo

**Increment 1 of 7, in progress.** Increment 0 (the SP.1 extraction spike) is complete — see
`docs/decisions.md` ADR-0003 for the recall result and its caveats.

Both apps are scaffolded and independently runnable. `backend/` holds the FastAPI app factory
with a `/health` route and the disposable SP.1 spike; `frontend/` holds a Next.js 15 scaffold
with a placeholder page. Route folders, graph nodes, models, migrations and routers arrive with
their stories — do not create them speculatively.

### Commands

Run from the repository root; `make help` lists everything.

| Command | What it does |
|---|---|
| `make install` | `uv sync --extra dev` in `backend/`, `npm install` in `frontend/` |
| `make dev` | db + api + web in Docker (needs `.env`; copy from `infra/.env.example`) |
| `make dev-api` / `make dev-web` | One app on the host with reload |
| `make lint` | ruff, ruff format, pyright, eslint, `tsc --noEmit`, and `deps-check` |
| `make test` | `pytest`, excluding tests marked `live` |
| `make test-live` | Only tests that hit real services or an LLM (costs money) |
| `make deps` / `make deps-check` | Regenerate / verify `dependencies.txt` |
| `make migrate` | Not built yet — lands with S0.2.1 |
| `make eval` | Not built yet — lands with S7.1 |

Backend-only equivalents, from `backend/`: `uv run ruff check .`, `uv run pyright`,
`uv run pytest`, `uv run uvicorn crossbid.main:app --reload`. Frontend-only, from `frontend/`:
`npm run lint`, `npm run typecheck`, `npm run build`, `npm run gen:api`.

Enable the pre-commit hook once per clone: `git config core.hooksPath .githooks`. It blocks
staged `.env` files and key-shaped strings, and runs ruff, prettier and `deps-check` on the
paths they apply to.

### Layout

`backend/` (FastAPI, `uv`, Python 3.12, own pyproject and Dockerfile), `frontend/` (Next.js 15,
own package.json and Dockerfile), `infra/` (Docker Compose, `.env.example`), `docs/`, plus a
root `Makefile` and `scripts/gen_dependencies.py`, which writes the generated
`dependencies.txt` from `backend/uv.lock` and `frontend/package-lock.json`. The two apps share
nothing but the OpenAPI contract, which generates `frontend/lib/api.ts` (generated, never
hand-edited; CI fails when it is stale). Full tree and layering rules are in
`docs/project-plan.md` → Repository layout.

Model slugs, chunking and agent defaults live in `backend/settings.default.yaml` — the only
place a slug is written down.

### Source documents

- `135.md` — the course brief (Sprint capstone: build an AI agent with LangGraph/LangChain, OpenAI API, Streamlit or Next.js). Graded on problem definition, understanding of agent concepts, technical implementation, and reflection. Bonus requires at least 2 medium and 1 hard optional task.
- `project.md` — the original project spec. Superseded by `docs/project-plan.md` for scope and delivery; trimmed to match at S7.6.

## Settled product decisions (do not reopen without new facts)

- Wedge is **cross-border EU bidding**: source-language requirement extraction, bidder-language explanation, evidence mapping via eCertis. Domestic use works but is not the positioning. Egypt/MENA and domestic-only positioning were rejected on 2026-09-09.
- Course build is **EU only**: TED API plus manual PDF upload. UK (Find a Tender) and US (SAM.gov) are post-submission connectors.
- Agent is **advisory only**: never submits, every matrix cell carries a citation or is marked unclear, a human review interrupt gates every verdict.
- **No scraping anywhere.** Only public, documented APIs (TED, eCertis, ECB/Frankfurter).
- Demo company: fictional German IT services GmbH. UI language English in v1.

## Verified external facts (2026-09-10)

These were checked against live endpoints; rely on them rather than re-deriving.

- **eCertis REST**: base `https://ec.europa.eu/growth/tools-databases/ecertisrest/`, GET only, no key. Spec v0.6 (2023). The model is criterion-centric (the 56 ESPD exclusion grounds and selection criteria), not certificate-centric: "equivalence" means the same EU criterion with different national evidence. Confirmed 2026-09-10: it does **not** map arbitrary standards — zero occurrences of ISO 27001 / 9001 / 14001 across the complete DE+FR payloads. Cached as JSON in the repo (`backend/crossbid/reference/data/ecertis/`, ~500 KB), so run time never touches the network.

  Corrections from implementing S1.1.1 (ADR-0007) — the earlier notes were wrong in ways that matter:
  - **Never key anything on a national criterion id.** `criteria?nationalEntity=de` returns the same 56 criteria under *country-scoped* UUIDs, and the DE and FR sets are disjoint from each other and from the bare `criteria` set. The only cross-border identifier is the **EU-level UUID from the bare `GET criteria` call** — that is what `criteria.json` and the `EcertisCriterionId` Literal use. National ids live inside `evidence_*.json` as `sub_criteria[].id`, a separate id space with **zero** overlap with the EU ids.
  - `criteria/{uuid}?countryFilter=xx` **only works with an EU-level uuid**. Given a national uuid, `countryFilter` is silently ignored and you get that country's payload back regardless of what you asked for.
  - The model is **three levels deep, not two**: criterion → national `sub_criteria` → `RequirementGroup` (these are *alternatives*, "any one of these papers") → `TypeOfEvidence`. The group layer carries real meaning and is preserved in the cache.
  - **HTTP 200 with an empty body is a valid answer meaning "this country has no national entry"** — 17 of 56 criteria for FR, 1 of 56 for DE. Transient emptiness also happens and is indistinguishable at the wire level, so the client retries 3× with backoff and refuses to overwrite a cached criterion that previously had evidence and now has none.
  - `GET criteria` omits `CriteriaTypeName`, sending only a meaningless `CriteriaTypeID`, so the bare list cannot distinguish an exclusion ground from a selection criterion. The taxonomy is stitched in from one extra `criteria?nationalEntity=eu` call (labels are byte-identical across countries). `nationalEntity=eu` returns 58 rows, not 56.
  - Undocumented `?lang=de` returns German, marked `(Automatische Übersetzung)`. `languageID`, `language`, `languageFilter` and `Accept-Language` are all ignored. This is the cheap route to S1.1.2's bilingual requirement; not cached.
- **TED Search API v3**: `POST https://api.ted.europa.eu/v3/notices/search`, no key. Expert query syntax; `IN (...)` does not accept `OR` inside the parentheses. Useful returnable fields: `document-url-lot`, `official-language`, `submission-language`, `selection-criterion-description-lot`, `deadline-receipt-tender-date-lot`, `links` (notice XML/PDF/HTML in all 24 languages). `document-url-lot` points to national platform HTML pages (TenderNed, Vergabemarktplatz, eb2b, ezamowienia), so procurement documents cannot be fetched automatically under the no-scraping rule; the user uploads them.

  Corrections and additions from ~1 000 live queries on 2026-09-10 (DE, FR, EN samples):
  - `SORT BY publication-date ASC` returns **HTTP 400**. Only `DESC` works.
  - Pagination caps at **600 results** — `limit=100, page=7` is HTTP 400 even when `totalNoticeCount` is higher. Narrow the query rather than paging past it.
  - `selection-criterion-description-lot` is **much sparser than assumed**: populated on 14% of French and 17% of English CPV-72 notices; 496 of 600 English notices had none. Notices routinely answer "Sources: Procurement Document" for both criteria fields. This is the strongest evidence for the upload-the-pack design — the notice usually does not carry the requirements.
  - `links` also exposes `links.pdfs.<official-language>` and `links.htmlDirect.<LANG>` alongside `links.pdf.<LANG>`.
  - **No German or French CPV-72 notice sampled hosts its documents on TED.** The EU Funding & Tenders Portal (EU institutions and agencies, notices in English) is the only platform found that serves procurement documents as plain unauthenticated `GET` URLs, including a download-all zip. Its JSON APIs are not usable — `api.sedia-backoffice-production.eu/.../{uuid}-CN` is 403 and `api.tech.ec.europa.eu/search-api` does not index tender records.
- **ESPD / DUME XML is the bridge to eCertis, confirmed on real data.** A French buyer's `DUME_acheteur.xml` (committed in the FR fixture) declares 30 `ccv:Criterion` elements carrying the canonical ESPD criterion UUIDs — e.g. `499efc97-2ac1-4af2-9e84-323c2ca67747` "Chiffre d'affaires annuel général", `1f49b3f0-d50f-43f6-8b30-4bafab108b9b` "Effectifs moyens annuels". These are the same ids eCertis is keyed on, so where a tender publishes a DUME the criterion mapping needs no LLM inference at all. Treat a published DUME as a high-confidence structured input, not as prose to extract.
- **LLM provider is OpenRouter only** (the user holds no OpenAI or Anthropic key). Verified 2026-09-10 against `https://openrouter.ai/api/v1/models`: `openai/gpt-5.6-terra` ($2/$12 per 1M) and `openai/gpt-5.6-luna` ($0.20/$1.20) support `structured_outputs`, `response_format`, and `tools`; For the eval judge and the multi-model demo, **`anthropic/claude-sonnet-5` is NOT available on this account** (HTTP 404). Re-probed with live calls 2026-09-10 — the account's data policy filters most providers. The non-OpenAI models that actually answer are `anthropic/claude-haiku-4.5` ($1/$5, the eval judge), `google/gemini-2.5-flash` ($0.30/$2.50) and `google/gemini-2.5-flash-lite` ($0.10/$0.40). Also 404: `claude-opus-5`, `claude-sonnet-4.5`, `gemini-2.5-pro`, `deepseek-chat-v3.1`, `llama-4-maverick`, `qwen3-235b`, `mistral-medium-3.1`, `nova-pro-v1`, `command-a`. **Presence in `/models` does not mean usable — always probe with a live call** (ADR-0005). OpenRouter's `/api/v1/embeddings`, probed 2026-09-10, serves exactly three usable embeddings on this account: **`openai/text-embedding-3-small` (1536 dims, ~$0.027/1M) — the default**, `openai/text-embedding-3-large` (3072 dims, $0.13/1M) as the quality switch, and `qwen/qwen3-embedding-8b` (4096 dims, ~$0.057/1M) as the non-OpenAI multilingual option. 3-small is the default because 1536 dims is under pgvector's 2000-dim index cap (ADR-0004). `baai/bge-m3`, `google/gemini-embedding-001` and `openai/text-embedding-ada-002` return **HTTP 404** on this account's data policy; Cohere, Voyage, Mistral, Jina and Nomic embeddings do not exist on OpenRouter at all. There is no `/models` listing for embeddings — probe the endpoint. `gpt-4o` is legacy. Use `ChatOpenAI(base_url="https://openrouter.ai/api/v1")` with `extra_body={"usage": {"include": true}}` for per-response cost. Keep slugs in `backend/settings.default.yaml`; never hard-code a model name. Users may store their own OpenAI/Anthropic/OpenRouter key (bring your own key): encrypted with Fernet, scoped by company, last-4 hint only, verified on save, never logged; embeddings always use the app's OpenRouter route.
- **Supabase + LangGraph Postgres checkpointer/Store**: the transaction pooler does not support prepared statements. Use the direct connection locally and the session pooler in deployment.
- **Docling** supports `do_ocr=False`; OCR engines are Tesseract, EasyOCR, RapidOCR, ocrmac. **Frankfurter** (`api.frankfurter.dev`) serves ECB reference rates without a key.
- **TenderWolf** (BE/NL/LU/FR plus TED, €79–149/month) already sells "may we participate?" analysis. Crossbid's differentiator must be bidder-side evidence mapping, not tender-side analysis.

## Project plan

`docs/project-plan.md` is the source of truth for scope, repository layout, the frontend/backend boundary and Supabase's role, build order (Epics → Features → Stories, delivered as Increments 0–7 for one developer; lanes A–E are grouping tags only), the Risks table, the graded-coverage table, and the 41 settled grill decisions of 2026-09-10. Increment 0 is a feasibility spike; the submission line is the end of Increment 5; BYOK, Docling, and deploy are stretch. Approved by the user on 2026-09-10; implementation has not started. Read it before proposing any work. `docs/roadmap.md` holds the Mermaid diagrams (folder tree, layer rules, bid sequence, feature dependency graph with critical path, single-track Gantt by increment, story board with increment column). Items listed as cut there (drafting, OCR, next-intl, quote highlighting, APScheduler, deadline/buyer tools, Ragas, numeric verdict score, few-shot learning from feedback, PL/NL tenders) are out of the course build.

## Historical: open scope questions (grill session 2026-09-10, now resolved in docs/project-plan.md)

`project.md` still contains items that a review of the 18-hour budget put in question. Do not implement these until the user decides: response drafting and DOCX export (contradicts the "never drafting" wedge), OCR, `next-intl`, citation highlighting in the PDF viewer, APScheduler, `deadline_calculator` and `web_search_buyer` tools, the 10-tender golden set (proposed: 3, DE/FR/EN), the weighted verdict score (proposed: rules only), and feedback-driven few-shot learning. Also proposed: PyMuPDF as the default parser with Docling switchable, application-level tenant isolation instead of RLS claims, developer role via an env-var email list.

## Conventions the spec commits to

- Structured outputs via Pydantic schemas for requirements and matrix rows; no prose where a typed object is expected.
- Tender text is untrusted input: wrap as data, never as instructions; schema-validate tool outputs.
- Outer LangGraph graph is a deterministic workflow with a human interrupt; per-requirement checking inside `check_reqs` is the agentic (ReAct) part. Describe it that way in docs and code comments.
- Every architectural choice gets an ADR-style entry in `docs/decisions.md`.

# Rules

- Never add "Co-Authored-By" lines to commits or include Claude attribution in commit messages and PR descriptions.
- Do NOT Commit any secrets — no API keys, passwords, or tokens in the files.
- Never Push without my approval first.
- After any dependency change, regenerate `dependencies.txt` with `make deps` (or `python3 scripts/gen_dependencies.py`) — never edit it by hand.
- Don't add any external libraries or packages without asking me first. Exception: everything named in the tech stack and settled decisions of `docs/project-plan.md` is pre-approved (user, 2026-09-10); anything outside that list needs a question first.
- Never delete anything without asking for permission while providing a sentance summary of why you are deleting it.
- If anything is unclear, ask me a question before making assumptions.
