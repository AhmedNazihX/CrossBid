# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## State of the repo

Pre-code. The repository holds two documents and nothing else:

- `135.md` — the course brief (Sprint capstone: build an AI agent with LangGraph/LangChain, OpenAI API, Streamlit or Next.js). Graded on problem definition, understanding of agent concepts, technical implementation, and reflection. Bonus requires at least 2 medium and 1 hard optional task.
- `project.md` — the project spec for **Crossbid**, a cross-border EU tender go/no-go qualification agent for SMEs. Sections 3 and 4 describe the intended LangGraph graph and tech stack; section 5 maps the brief's optional tasks; section 9 logs decisions.

There are no build, lint, or test commands yet. When the code lands, add them here. Intended layout: `backend/` (FastAPI, `uv`, own pyproject and Dockerfile), `frontend/` (Next.js, own package.json and Dockerfile), `infra/` (Docker Compose), `docs/`, plus a root `Makefile` (`dev`, `test`, `lint`, `deps`, `deps-check`, `migrate`, `eval`) and `scripts/gen_dependencies.py`, which writes the generated `dependencies.txt` from `backend/uv.lock` and `frontend/package-lock.json`. The two apps share nothing but the OpenAPI contract, which generates `frontend/lib/api.ts`. Full tree and layering rules are in `docs/project-plan.md` → Repository layout.

## Settled product decisions (do not reopen without new facts)

- Wedge is **cross-border EU bidding**: source-language requirement extraction, bidder-language explanation, evidence mapping via eCertis. Domestic use works but is not the positioning. Egypt/MENA and domestic-only positioning were rejected on 2026-09-09.
- Course build is **EU only**: TED API plus manual PDF upload. UK (Find a Tender) and US (SAM.gov) are post-submission connectors.
- Agent is **advisory only**: never submits, every matrix cell carries a citation or is marked unclear, a human review interrupt gates every verdict.
- **No scraping anywhere.** Only public, documented APIs (TED, eCertis, ECB/Frankfurter).
- Demo company: fictional German IT services GmbH. UI language English in v1.

## Verified external facts (2026-09-10)

These were checked against live endpoints; rely on them rather than re-deriving.

- **eCertis REST**: base `https://ec.europa.eu/growth/tools-databases/ecertisrest/`, GET only, no key. `criteria?nationalEntity=de` lists national criteria; `criteria/{uuid}?countryFilter=xx` returns the evidences for a criterion per country. The model is criterion-centric (the ~56 ESPD exclusion grounds and selection criteria), not certificate-centric: "equivalence" means the same EU criterion with different national evidence. It does not map arbitrary standards like ISO 27001. Spec is v0.6 (2023); cache responses as JSON in the repo.
- **TED Search API v3**: `POST https://api.ted.europa.eu/v3/notices/search`, no key. Expert query syntax; `IN (...)` does not accept `OR` inside the parentheses. Useful returnable fields: `document-url-lot`, `official-language`, `submission-language`, `selection-criterion-description-lot`, `deadline-receipt-tender-date-lot`, `links` (notice XML/PDF/HTML in all 24 languages). `document-url-lot` points to national platform HTML pages (TenderNed, Vergabemarktplatz, eb2b, ezamowienia), so procurement documents cannot be fetched automatically under the no-scraping rule; the user uploads them.
- **LLM provider is OpenRouter only** (the user holds no OpenAI or Anthropic key). Verified 2026-09-10 against `https://openrouter.ai/api/v1/models`: `openai/gpt-5.6-terra` ($2/$12 per 1M) and `openai/gpt-5.6-luna` ($0.20/$1.20) support `structured_outputs`, `response_format`, and `tools`; `anthropic/claude-sonnet-5` ($2/$10) is available for the eval judge and multi-model demo. OpenRouter's `/api/v1/embeddings` serves `openai/text-embedding-3-large` ($0.13/1M) and `baai/bge-m3` ($0.01/1M). `gpt-4o` is legacy. Use `ChatOpenAI(base_url="https://openrouter.ai/api/v1")` with `extra_body={"usage": {"include": true}}` for per-response cost. Keep slugs in `backend/settings.default.yaml`; never hard-code a model name. Users may store their own OpenAI/Anthropic/OpenRouter key (bring your own key): encrypted with Fernet, scoped by company, last-4 hint only, verified on save, never logged; embeddings always use the app's OpenRouter route.
- **Supabase + LangGraph Postgres checkpointer/Store**: the transaction pooler does not support prepared statements. Use the direct connection locally and the session pooler in deployment.
- **Docling** supports `do_ocr=False`; OCR engines are Tesseract, EasyOCR, RapidOCR, ocrmac. **Frankfurter** (`api.frankfurter.dev`) serves ECB reference rates without a key.
- **TenderWolf** (BE/NL/LU/FR plus TED, €79–149/month) already sells "may we participate?" analysis. Crossbid's differentiator must be bidder-side evidence mapping, not tender-side analysis.

## Project plan

`docs/project-plan.md` is the source of truth for scope, repository layout, the frontend/backend boundary and Supabase's role, build order (Epics → Features → Stories, lanes A–E), and the 41 settled grill decisions of 2026-09-10. Approved by the user on 2026-09-10; implementation has not started. Read it before proposing any work. `docs/roadmap.mdx` holds the Mermaid diagrams (folder tree, layer rules, bid sequence, feature dependency graph with critical path, Gantt by lane, story board). Items listed as cut there (drafting, OCR, next-intl, quote highlighting, APScheduler, deadline/buyer tools, Ragas, numeric verdict score, few-shot learning from feedback, PL/NL tenders) are out of the course build.

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
