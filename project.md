# Crossbid — cross-border tender qualification agent for SMEs

> Working title. Rename freely.

## 1. Introduction

Small and medium enterprises win about 60% of EU public contracts by count but only about 30% by value. The gap is widest across borders: TED publishes roughly 700,000 notices a year in 24 languages, yet the share of contracts awarded to a bidder from another member state has stayed in the low single digits for a decade. The single market for public procurement exists on paper. In practice, a Polish IT firm does not bid on a French tender because the file is 100 pages of French legal and technical text, the exclusion grounds and certificate requirements follow French national rules, and one missed mandatory document disqualifies the bid outright. Bid consultants who bridge that gap charge more than the SME expects to profit.

Crossbid is an AI agent that does that judgement work before a bid is written. Given a tender in any EU language and a company profile, it extracts every requirement with a citation to the source page, translates and explains each one in the bidder's language, maps the certificates the tender asks for to their equivalents in the bidder's home country, checks each requirement against what the company can actually prove, and returns a **go / no-go verdict** with a compliance matrix. A human reviews and confirms every verdict before anything moves forward. Only then does the agent help draft the response.

The agent is advisory by design. It never submits, never asserts compliance without a source, and refuses to give a verdict when the documents do not support one.

### Why an agent, not a prompt or plain RAG

| Approach | Why it is not enough alone |
|---|---|
| Prompt engineering | A tender is too long for one context window and has no company knowledge. |
| Plain RAG | Answers questions about a document but cannot decide, loop over requirements, call tools, or pause for approval. |
| Agent (LangGraph) | Multi-step plan, per-requirement tool calls, persistent state across days, human-in-the-loop interrupts, and long-term memory of the company and past decisions. |

### Target users

- **Primary:** EU SMEs (IT services, consulting, engineering, specialised supplies) that bid domestically and want to bid in a second member state, or that receive a foreign-language tender through a partner. Owner, sales lead, or office manager, not a procurement professional.
- **Secondary (post-submission):** UK SMEs on Find a Tender and Contracts Finder, US small businesses on SAM.gov, bid consultants serving several SME clients.

### What it is not (v1)

Not a bid submission tool, not a portal replacement, not a legal advisor, not a generic chatbot, not a tender search engine.

### Competitive positioning

The EU, UK, and US already have qualification tools at SME prices: Lucius, Brainial, and Tenderwolf in the EU, Stotles and Tussell in the UK, GovDash and GovRFP in the US. All of them are single-jurisdiction and assume the bidder reads the tender's language and knows the local rules. Crossbid's wedge is the cross-border case: source-language extraction, bidder-language explanation, and certificate equivalence via the EU's eCertis database. The agent, matrix, review flow, and evaluation are identical for a domestic tender, so a domestic SME can use it too, but the product is sold on the case incumbents do not cover.

---

## 2. Core functionality

### The vertical slice (course deliverable)

1. **Company profile onboarding.** Upload certificates, past bids, capability statements, registration extract, VAT and insurance documents, key staff CVs. Agent extracts a structured profile, including home country and the certificates held, and stores it in long-term memory.
2. **Tender intake.** Connectors behind one interface, in build order: (a) search the **EU TED API** by CPV code, country, and keyword, pull the notice and follow the links to the procurement documents (primary source for the course build: free, structured, multilingual, stable), (b) **upload tender PDFs manually** (any market, always available), (c) **UK Find a Tender and Contracts Finder APIs** and (d) **US SAM.gov Contract Opportunities API** (post-submission connectors).
3. **Requirements extraction.** Structured output in the source language with a translation into the user's language: each requirement typed (mandatory / scored / informational), category (exclusion grounds, suitability, economic and financial standing, technical and professional ability, award criteria, formal: language, format, lots, bid bond), page and quote citation, deadline.
4. **Certificate equivalence.** For each certificate or registration the tender names, the agent looks up the bidder-country equivalent in eCertis and records it in the matrix. Where no equivalent exists, the row is flagged for the reviewer.
5. **Compliance matrix.** For each requirement, RAG over the company's documents returns evidence, a status (met / met via equivalent / not met / unclear / needs document), and the source.
6. **Go / no-go verdict.** Weighted score plus a plain-language explanation in the user's language. Hard fails (any unmet mandatory requirement or exclusion ground) force a "no-go unless…" verdict with the exact gap.
7. **Human review (interrupt).** Reviewer sees the matrix beside the source document, edits statuses, attaches missing evidence, confirms or overrides the verdict. Nothing proceeds without this step.
8. **Response drafting (post-approval).** Section-by-section draft in the tender's language, mapped to the award criteria, reusing approved past-bid text. Second interrupt before export to DOCX.
9. **Ask the tender.** Chat over the tender and matrix with citations, in either language.

### User interactions

- Dashboard: bids in progress, verdict, deadline countdown with the buyer's local time zone, missing documents.
- Bid workspace: source document viewer with highlighted citations on the left, compliance matrix on the right, language toggle for every requirement.
- Review actions: confirm, override with reason, request re-check, attach document, mark equivalence accepted.
- Settings (user): interface language, tone, notification preferences, home country.
- Settings (developer, separate route, role-gated): model, temperature, max tokens, system prompt, tool toggles, cost display.

---

## 3. Architecture

### LangGraph graph

```
                ┌──────────────┐
  intake ─────▶ │ parse_docs   │ (Docling, OCR per tender language)
                └──────┬───────┘
                       ▼
                ┌──────────────┐
                │ extract_reqs │ structured output + citations + translation
                └──────┬───────┘
                       ▼
                ┌──────────────┐   per requirement, tool calls:
                │ check_reqs   │◀──  company_rag_search, ecertis_lookup,
                └──────┬───────┘     deadline_calc, currency_convert…
                       ▼
                ┌──────────────┐
                │ score_verdict│ rules + LLM explanation
                └──────┬───────┘
                       ▼
             ╔═════════════════╗
             ║ INTERRUPT: review║  human confirms / edits / overrides
             ╚════════╤════════╣
                      ▼
                ┌──────────────┐
                │ draft_reply  │ only if verdict == go
                └──────┬───────┘
                       ▼
             ╔═════════════════╗
             ║ INTERRUPT: approve║
             ╚════════╤════════╣
                      ▼
                ┌──────────────┐
                │ export_docx  │
                └──────────────┘
```

Plus a separate lightweight `ask_tender` ReAct subgraph for Q&A that shares the same thread state.

### State and memory

| Layer | Mechanism | Holds |
|---|---|---|
| Short-term (per bid thread) | LangGraph `PostgresSaver` checkpointer | Parsed docs, requirements, matrix, verdict, reviewer edits, conversation. Survives restarts and multi-day pauses at interrupts. |
| Long-term (per company) | LangGraph `PostgresStore` + pgvector | Company profile, home country, certificates with expiry, accepted equivalences, past bids, approved boilerplate, reviewer corrections. |
| Learning from feedback | Store namespace `corrections/{company_id}` | Every override ("this requirement was misread", "our ISO 27001 covers this") is stored and injected as few-shot context on the next extraction. Accepted equivalences are remembered per country pair. Ratings on drafts adjust which boilerplate is preferred. |

### Tools (function calling)

| Tool | Purpose | Calls external API? |
|---|---|---|
| `company_rag_search` | Evidence retrieval over the company's own documents | No (pgvector) |
| `tender_rag_search` | Retrieval over the current tender documents | No |
| `search_ted` | Query the EU TED API by CPV code, country, keyword; fetch notice and document links | Yes |
| `ecertis_lookup` | Map a certificate or registration named in the tender to the bidder-country equivalent | Yes (EU eCertis) |
| `deadline_calculator` | Working-day deadline math with the buyer country's public holidays and time zone | Yes (public holiday API) |
| `currency_convert` | EUR / GBP / USD / PLN and others for bid bond and turnover thresholds | Yes (ECB reference rates) |
| `web_search_buyer` | Background on the contracting authority | Yes |
| `search_find_a_tender`, `search_sam_gov` | UK and US connectors | Yes (post-submission) |

Users can enable or disable the external tools from the developer panel (plugin-style registry; each tool is a module with a manifest).

---

## 4. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | **Next.js 15 (App Router), TypeScript, Tailwind, shadcn/ui** | Review-screen UI with a PDF viewer and an editable bilingual matrix is beyond Streamlit. |
| PDF viewer | `react-pdf` (pdf.js) | Jump-to-page highlighting for citations. |
| i18n | `next-intl` | Interface in English, German, French, Polish and others over time; every requirement carries source and target language. |
| Backend | **FastAPI, Python 3.12, `uv`** | Async, Pydantic v2 models shared with LangGraph structured outputs. |
| Agent framework | **LangGraph + LangChain** | Required by the brief; interrupts, checkpointer, and Store map directly onto the features above. |
| LLM (default) | **OpenAI `gpt-4o` for extraction and translation, `gpt-4o-mini` for classification and chat** | Required by the brief; strong across EU languages; structured outputs. |
| Multi-model | LangChain `init_chat_model` with OpenAI, Anthropic, Google, plus **OpenRouter** as a single-key fallback | Satisfies the multi-model optional task. |
| Embeddings | **OpenAI `text-embedding-3-large`** (default), `BAAI/bge-m3` as a self-hosted alternative | Multilingual retrieval across 24 tender languages; monolingual embeddings would silently break recall. |
| Database | **Postgres on Supabase, EU region** with `pgvector` | One database for app data, vectors, checkpoints, and Store. Row-level security gives per-company tenant isolation. EU region for GDPR data residency. |
| Auth | **Supabase Auth** (email magic link), JWT verified in FastAPI | Cheapest secure path; role claim separates `user` from `developer`. |
| Document parsing | **Docling** with OCR (Tesseract language packs per tender language), PyMuPDF fallback | Annexes are often scanned. Docling preserves tables and page numbers, which citations depend on. |
| Tender data | **TED API** (primary), manual upload; **Find a Tender / Contracts Finder** and **SAM.gov** APIs post-submission | All public, structured APIs. No scraping anywhere in the system. |
| Reference data | **eCertis** (certificate equivalence), **ECB** reference rates, public holiday API | Free EU and public data sources. |
| Structured extraction | OpenAI structured outputs via Pydantic schemas | Requirements and matrix rows are typed objects, not prose. |
| Background jobs | **APScheduler** inside FastAPI for v1; **Celery + Redis** when there are real users | Saved-search scans and long document processing without blocking requests. |
| Observability | **LangSmith** (default with LangGraph) or **Langfuse** (open source, self-hostable in the EU) | Hard optional task 2. Langfuse preferred if EU data residency becomes a customer requirement. |
| Evaluation | **DeepEval** for LLM-as-judge on extraction faithfulness, translation adequacy, verdict correctness; **Ragas** for retrieval metrics | Hard optional task 3. |
| Guards | Prompt-injection classifier on ingested tender text (indirect injection), PII minimisation on staff CVs, rate limiting, output schema validation, refusal when citations are missing | Medium optional task 8. Tender documents are untrusted input. |
| Export | `python-docx` | Word and PDF submissions are the norm. |
| Testing | `pytest`, `pytest-asyncio`, fixture tenders in `tests/fixtures/` in at least three languages; Playwright e2e for the review flow | |
| Local dev | Docker Compose: Postgres+pgvector, backend, frontend | |
| Deployment | **Vercel** (frontend), **Railway** or **Fly.io** EU region (FastAPI), **Supabase** EU | Live link for the portfolio; EU hosting end to end. |
| Payments (business track, later) | Stripe | |

### Repository layout

```
/
├── apps/
│   ├── web/                # Next.js
│   └── api/                # FastAPI
│       ├── agent/          # graph.py, state.py, nodes/, tools/, prompts/
│       ├── ingestion/      # connectors/ (ted, upload, fat, sam), docling pipeline
│       ├── reference/      # ecertis client, holidays, ecb rates
│       ├── memory/         # store namespaces, profile schema
│       ├── guards/         # injection, pii, rate limit
│       ├── routers/        # bids, companies, dev-settings, feedback
│       └── evaluations/    # deepeval + ragas suites, golden set
├── docs/                   # architecture.md, decisions.md, user-guide.md
├── infra/                  # docker-compose, env templates
└── project.md              # this file
```

---

## 5. Requirement and optional-task coverage

### Required tasks

| Requirement | How it is met |
|---|---|
| Agent purpose | Section 1: problem, users, why an agent, positioning. |
| Core functionality | Section 2: the nine-step vertical slice. |
| User interface | Next.js dashboard, bilingual bid workspace, review actions, separate dev panel. |
| Technical implementation | LangGraph with checkpointer and Store, typed tools, structured outputs, guards, retries and fallbacks on parsing and external APIs. |
| Documentation | `README.md` quick start, `docs/user-guide.md` with three worked examples (one domestic, two cross-border), `docs/decisions.md` (ADR style) for every choice in Section 4. |

### Optional tasks: proposed scope

Legend: **Must** = in the course build. **Should** = if time allows in the 18 h. **Later** = post-submission.

**Easy**

| # | Task | Scope | Notes |
|---|---|---|---|
| 1 | LLM critique of usability, security, prompt engineering | Must | Run it, record findings and fixes in `docs/critique.md`. |
| 2 | Personality / tone | Must | Formal vs. concise register per language; user setting. |
| 3 | Choose from a list of LLMs | Must | Dev panel dropdown; falls out of multi-model. |
| 4 | Temperature, max tokens sliders | Must | Dev panel only, hidden from users. |
| 5 | Interactive help / guide | Should | Guided first-bid walkthrough in the UI. |

**Medium**

| # | Task | Scope | Notes |
|---|---|---|---|
| 1 | Token usage and cost | Must | Per bid and per node, shown in dev panel via LangSmith callbacks. |
| 2 | Long- and short-term memory | Must | Core architecture, Section 3. |
| 3 | Function tool calling an external API | Must | TED, eCertis, ECB rates, holiday API. |
| 4 | Authentication and personalisation | Must | Supabase Auth; company profile and home country are the personalisation. |
| 5 | Feedback loop with ratings | Must | Thumbs and override reasons on every matrix row and draft section. |
| 6 | 5+ tools with enable/disable UI, plugin system | Should | Tool registry with manifests; toggles in dev panel. Seven tools in v1. |
| 7 | Multi-model support | Should | `init_chat_model` plus OpenRouter. |
| 8 | Security guard, dev vs. user settings separation | Must | Section 4 guards row; `/dev` route role-gated. |

**Hard**

| # | Task | Scope | Notes |
|---|---|---|---|
| 1 | Agentic RAG | Must | The agent decides per requirement whether to retrieve, which corpus, whether to consult eCertis, and whether evidence is sufficient. This is the product. |
| 2 | Observability (LangSmith / Langfuse) | Must | Zero-config with LangGraph. |
| 3 | Evaluation report (Ragas / DeepEval) | Must | Golden set of 10 TED tenders across at least 4 countries, at least 5 non-English, with hand-labelled requirements; report recall, faithfulness, translation adequacy, verdict accuracy. |
| 4 | Agent learns from feedback | Should | Corrections and accepted equivalences in Store injected into extraction prompts; measurable on the golden set before and after. |
| 5 | External data source integration | Must | TED, eCertis, ECB, holidays (course build); Find a Tender and SAM.gov after submission. |

This exceeds the "2 medium + 1 hard" bonus threshold with margin. If time runs short, drop in this order: Medium 6, Medium 7, Hard 4, Easy 5.

---

## 6. Security and error handling

- **Indirect prompt injection.** Tender PDFs are untrusted. All extracted text passes an injection classifier and is wrapped as data, never as instructions. Tool outputs are schema-validated.
- **No verdict without evidence.** Every matrix cell must carry a citation or be marked "unclear". The scorer refuses to output "go" if any mandatory row or exclusion ground lacks evidence.
- **Tenant isolation.** RLS on every table keyed by `company_id`; Store namespaces include `company_id`.
- **GDPR.** EU hosting end to end, per-company data export and deletion endpoint, staff CVs minimised to the fields the matrix needs, no training on customer data.
- **Rate limiting and cost caps** per user; external API calls cached and retried with backoff.
- **Failure modes handled:** TED document link points to a national platform requiring login (prompt the user to upload manually), OCR failure (flag pages, continue), unsupported tender language (translate for reasoning, cite original, warn), LLM timeout (retry, then smaller model), schema violation (re-ask once, then mark row unclear), eCertis has no entry (flag for reviewer), expired certificates (warn with date).

---

## 7. Evaluation plan

| Metric | Method | Target |
|---|---|---|
| Requirement recall | Golden set vs. extracted, per tender | ≥ 0.9 on mandatory requirements |
| Citation faithfulness | DeepEval faithfulness on each requirement quote | ≥ 0.95 |
| Translation adequacy | DeepEval judge, source vs. target requirement text | ≥ 0.9 |
| Compliance status accuracy | Human-labelled matrix vs. agent | ≥ 0.85 |
| Equivalence correctness | eCertis-backed rows vs. reviewer acceptance | Report |
| Verdict agreement | Agent go / no-go vs. reviewer final | Report, no target in v1 |
| Retrieval quality | Ragas context precision and recall | Report |
| Cost per bid | LangSmith | < $2.50 for a 100-page tender including translation |

The report ships in `evaluations/REPORT.md` with before/after numbers for the feedback-learning feature.

---

## 8. Delivery plan (18 h core, then iterations)

| Block | Hours | Output |
|---|---|---|
| 1. Skeleton | 2 | Monorepo, Docker Compose, Supabase EU, auth, empty graph with checkpointer. |
| 2. Ingestion | 2 | TED client with document-link following, manual upload, Docling parse with OCR, connector interface. |
| 3. Extraction, equivalence, matrix | 4 | Structured bilingual extraction, eCertis tool, company RAG tool, matrix, scorer. |
| 4. Interrupt and review UI | 4 | Bid workspace, PDF viewer with citation jump, language toggle, confirm / override, resume graph. |
| 5. Drafting and export | 2 | Draft node, second interrupt, DOCX. |
| 6. Guards, dev panel, observability, cost | 2 | Injection guard, settings, LangSmith, token display. |
| 7. Evals and docs | 2 | Golden set of 10 tenders, DeepEval run including translation adequacy, README, user guide, decisions. |

Iteration after submission: Find a Tender and SAM.gov connectors with UK and US rule packs, feedback learning, tool plugin toggles, multi-model, additional interface languages.

---

## 9. Risks and open questions

| Risk | Mitigation |
|---|---|
| Crowded market; "another tender tool" | Cross-border wedge stated on every surface; eCertis equivalence is a feature no incumbent ships. |
| TED notices link to documents on national platforms, some behind login | Manual upload is a first-class path; the agent tells the user exactly which documents it could not fetch. |
| Extraction and translation quality across languages | Golden set spans at least 4 countries and 5 non-English tenders; gpt-4o for extraction; translation adequacy is a tracked metric. |
| Adding UK and US rule packs triples legal complexity | Kept out of the course build; connectors added only after the EU version is evaluated. |
| Scope creep in 18 h | Drop order defined in Section 5. |
| Business: SMEs' willingness to pay when Lucius is ~€100/month | Validation track below; course value is independent of this. |

Decisions taken (2026-09-09):
1. **Wedge:** cross-border EU bidding. Domestic use works but is not the positioning.
2. **Course build scope:** EU only, TED plus manual upload. UK and US connectors after submission.
3. **Golden set:** 10 TED tenders across at least 4 countries, at least 5 non-English.
4. **Demo company:** a fictional German IT services SME (GmbH) with a realistic document pack (Handelsregisterauszug, tax certificate, ISO 27001, liability insurance, three past bids, two reference letters) bidding on tenders in France, Poland, and the Netherlands.
5. **UI language:** English in v1; German next.

---

## 10. Business track (parallel, not part of the course grade)

- **Weeks 1–4:** 10 conversations with EU SMEs that have considered but not attempted a cross-border bid, sourced via Enterprise Europe Network contacts, chambers of commerce, and bid consultants. Questions: what stopped you, who would read the foreign file today, what a disqualification cost you last time, what you would pay.
- **Wedge:** cross-border qualification, certificate equivalence, bilingual matrix. Not monitoring (portals and Stotles do it), not drafting (ChatGPT does it), not domestic qualification (Lucius does it).
- **Pricing hypothesis:** per-bid credit (€29–49) to undercut monthly subscriptions for occasional bidders; €79/month for firms bidding monthly.
- **Moat:** accepted-equivalence data per country pair, multilingual requirement corpus, outcome data from reviewer confirmations. Thinner than a language or portal moat; the honest answer is speed and focus on a case incumbents treat as an edge case.
- **Next markets:** UK via Find a Tender for EU firms bidding post-Brexit, US via SAM.gov for EU firms with a US entity. Both are connector additions, not rewrites.
- **Rejected alternatives:** domestic-only EU, UK, or US SME qualification (incumbents at SME prices), Egypt and MENA (chosen against by the founder on 2026-09-09; the connector architecture keeps it possible later).
