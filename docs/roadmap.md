# Crossbid — structure and roadmap

Visual companion to `project-plan.md`. Diagrams are Mermaid fences, so they render in GitHub and in VS Code (Markdown Preview Mermaid Support). Sizes use the plan's scale: S about 1 h, M 1–3 h, L 3–6 h. One roadmap "day" is a 4-hour block. Lanes A–E are tags for grouping only; one developer builds this, so the Gantt is a single track ordered by increment (see *Delivery order* in the plan).

## 1. Folder structure

```mermaid
flowchart LR
  root["/"]
  root --> BE["backend/  ·  FastAPI · Python 3.12 · uv"]
  root --> FE["frontend/  ·  Next.js 15 · TypeScript · Tailwind · shadcn"]
  root --> INFRA["infra/  ·  docker-compose.yml · .env.example"]
  root --> DOCS["docs/  ·  project-plan · roadmap · architecture · decisions · user-guide · critique"]
  root --> TOP["135.md · project.md · CLAUDE.md · README.md"]

  subgraph backend
    BE --> BEcfg["pyproject.toml · Dockerfile · settings.default.yaml"]
    BE --> PKG["crossbid/  (the package)"]
    BE --> MIG["migrations/  plain SQL"]
    BE --> SCR["scripts/  migrate · build_ecertis_cache · seed_demo_company · run_eval"]
    BE --> EVAL["evaluations/  golden yaml · deepeval suite · REPORT.md"]
    BE --> TST["tests/  unit · integration (live) · fixtures"]
    TST --> FIX["fixtures/  tenders de fr en · company pack · adversarial PDFs"]

    PKG --> CORE["main.py · llm.py · settings.py · auth.py · crypto.py · db.py"]
    PKG --> MODELS["models/  requirement · matrix · verdict · company · tender · review · provider"]
    PKG --> AGENT["agent/"]
    AGENT --> AG1["state.py · graph.py · chat_graph.py"]
    AGENT --> AG2["nodes/  parse_docs · extract_reqs · check_reqs · score_verdict · apply_review · finalize"]
    AGENT --> AG3["tools/  registry · company_rag · tender_rag · search_ted · ecertis_evidence · currency"]
    AGENT --> AG4["prompts/  extract · check · explain · chat · guard"]
    PKG --> ING["ingestion/  parser · pymupdf · docling · chunker · embeddings · storage · ted_client"]
    PKG --> REF["reference/  ecertis_client · frankfurter · data/ecertis/*.json"]
    PKG --> MEM["memory/  Store namespaces"]
    PKG --> GRD["guards/  injection · wrap"]
    PKG --> RM["readmodel/  bids · requirements · matrix_rows · reviews · llm_usage"]
    PKG --> RT["routers/  companies · documents · tenders · bids · review · chat · provider_keys · dev_settings · feedback"]
  end

  subgraph frontend
    FE --> FEcfg["package.json · Dockerfile"]
    FE --> APP["app/"]
    APP --> A1["(auth)/login"]
    APP --> A2["(app)/  dashboard · company · settings · bids/new · bids/[id] · bids/[id]/chat"]
    APP --> A3["dev/  settings · tool toggles · costs"]
    FE --> CMP["components/  matrix · pdf · verdict · ui"]
    FE --> LIB["lib/  api.ts (generated) · supabase.ts · usePolling"]
  end
```

## 2. Dependency direction inside the backend

Arrows mean "may import from". Nothing points upward.

```mermaid
flowchart TD
  R["routers/"] --> A["agent/  (graph, nodes, chat)"]
  R --> I["ingestion/"]
  R --> RM["readmodel/"]
  A --> T["agent/tools/"]
  A --> REF["reference/"]
  A --> MEM["memory/"]
  A --> G["guards/"]
  A --> RM
  I --> G
  T --> I
  T --> REF
  T --> MEM
  A --> BASE["models/ · db.py · settings.py · llm.py · crypto.py"]
  I --> BASE
  T --> BASE
  REF --> BASE
  MEM --> BASE
  G --> BASE
  RM --> BASE
  R --> BASE
  classDef base fill:#eef,stroke:#446,color:#1B2430;
  class BASE base;
```

## 3. One bid, across the folders

```mermaid
sequenceDiagram
  autonumber
  participant B as Browser (frontend)
  participant SB as Supabase Auth / Storage
  participant RT as routers/bids.py
  participant GR as agent/graph.py
  participant ING as ingestion/
  participant TL as agent/tools/
  participant RM as readmodel/

  B->>SB: magic-link login → JWT
  B->>RT: POST /bids (JWT, notice number, document ids)
  RT-->>B: 202 + bid id
  RT->>GR: background run, thread bid:id
  GR->>ING: parse_docs → chunks (pymupdf, guards, embeddings)
  GR->>GR: extract_reqs (sections → Requirement[], criterion enum)
  loop check_reqs · Send fan-out per requirement
    GR->>TL: company_rag_search · ecertis_evidence_lookup · currency_convert
    TL-->>GR: MatrixRow
  end
  GR->>GR: score_verdict (rules + explanation)
  GR->>RM: write snapshot
  GR-->>GR: interrupt()
  B->>RT: GET /bids/id (poll every 2 s) → awaiting_review
  B->>SB: load PDF via signed URL
  B->>RT: POST /bids/id/review (row edits, decision)
  RT->>GR: Command(resume)
  GR->>GR: apply_review → re-score → override record
  GR->>RM: write final
  B->>RT: GET /bids/id → final verdict
```

## 4. Feature dependency graph and critical path

Feature-level (stories roll up). Thick red edges are the critical path. Dashed edges are content or contract inputs that carry no code dependency. Corrections from the PM review of 2026-09-10: F1.x depend on the repo (F0.1), not the database; F3.1 depends on the checkpointer (F0.2), not on F2.4; F0.3 (auth) is no longer on the path to F0.4; the spike precedes everything.

```mermaid
flowchart LR
  classDef crit fill:#fde8e8,stroke:#c0392b,stroke-width:2px,color:#1B2430;
  classDef laneA fill:#eaf4ff,stroke:#2c6fbb,color:#1B2430;
  classDef laneB fill:#eafbea,stroke:#2e8b57,color:#1B2430;
  classDef laneC fill:#fff4e5,stroke:#d98b00,color:#1B2430;
  classDef laneD fill:#f5eaff,stroke:#7b4bb5,color:#1B2430;
  classDef laneE fill:#f0f0f0,stroke:#666,color:#1B2430;

  SP["SP.1 spike: extraction feasibility"]:::crit

  subgraph E0["E0 Foundations (gate)"]
    F01["F0.1 repo · tooling · CI"]:::crit
    F02["F0.2 db & persistence"]:::crit
    F03["F0.3 auth & settings"]
    F04["F0.4 contracts (Pydantic → OpenAPI → TS)"]
  end

  subgraph LaneA["Lane A"]
    F11["F1.1 eCertis cache + tool"]:::laneA
    F12["F1.2 TED client + tool"]:::laneA
    F13["F1.3 currency tool"]:::laneA
    F14["F1.4 tool registry"]:::laneA
    E5["E5 multi-model · BYOK · costs"]:::laneA
  end

  subgraph LaneB["Lane B"]
    F21["F2.1 parsing & chunking"]:::crit
    F22["F2.2 embeddings & storage"]:::crit
    F23["F2.3 guards"]:::laneB
    F24["F2.4 profile & memory · RAG tools"]:::laneB
    F31["F3.1 state & skeleton"]:::crit
    F32["F3.2 extraction · S3.2.3 recall script"]:::crit
    F33["F3.3 check_reqs (Send)"]:::crit
    F34["F3.4 verdict · interrupt · review"]:::crit
    F35["F3.5 ask the tender"]:::laneB
  end

  subgraph LaneC["Lane C"]
    F41["F4.1 shell & auth"]:::laneC
    F42["F4.2 onboarding"]:::laneC
    F43["F4.3 new bid"]:::laneC
    F44["F4.4 dashboard"]:::laneC
    F40["F4.0 design canvas · user confirms"]:::crit
    F45["F4.5 bid workspace (review UI)"]:::crit
    F46["F4.6 chat · dev panel · settings/BYOK"]:::laneC
  end

  subgraph LaneD["Lane D · content"]
    S61["S6.1/6.2 fixture tenders DE FR EN"]:::laneD
    S63["S6.3 demo GmbH document pack"]:::laneD
    S64["S6.4 golden set labels"]:::laneD
  end

  subgraph LaneE["Lane E · eval & docs"]
    S71["S7.1 DeepEval report"]:::crit
    S72["S7.2/7.3 ADRs · architecture"]:::laneE
    S74["S7.4 user guide · S7.7 Playwright"]:::laneE
    E8["E8 deploy (optional)"]:::laneE
  end

  S61 -.-> SP
  SP ==> F01 ==> F02 ==> F21 ==> F22 ==> F32 ==> F33 ==> F34 ==> F45 ==> S71
  F02 --> F03
  F02 --> F04
  F02 --> F31 --> F32
  F01 --> F11 & F12 & F13
  F11 & F12 & F13 --> F14
  F14 --> F33
  F23 --> F32
  F22 --> F23
  F22 --> F24 --> F33
  F03 --> F24
  F03 --> E5
  F14 --> E5
  F04 -.-> F41 --> F42 & F43
  F04 --> F40
  F40 ==> F45
  F40 --> F44
  F41 --> F44
  F31 -.-> F45
  F34 --> F46
  F35 --> F46
  E5 --> F46
  F33 --> F35
  S61 -.-> F21
  S63 -.-> F24
  S64 -.-> F32
  S64 -.-> S71
  F45 --> S74
  S74 --> E8
  F01 -.-> S72
```

## 5. Roadmap by increment (single track)

Dates are placeholders from a nominal start on 2026-09-14; only the order matters. One row per feature-sized chunk, sequential, because one person does the work. The *content* section shows wait-fillers that run inside gaps of the same blocks, not in extra time. The milestone after Increment 5 is the submission line; Increments 6 and 7 are stretch.

```mermaid
gantt
  title Crossbid roadmap (1 day = one 4-hour block, single developer)
  dateFormat YYYY-MM-DD
  axisFormat %d %b
  excludes weekends

  section Inc 0 · core bet
  S6.1 DE fixture pack               :crit, i0a, 2026-09-14, 1d
  SP.1 spike extract + check         :crit, i0b, after i0a, 1d
  Go / pivot recorded                :milestone, m0, after i0b, 0d

  section Inc 1 · requirement list in browser
  F0.1 repo · tooling · CI           :crit, i1a, after i0b, 2d
  F0.2 db · checkpointer · tables    :crit, i1b, after i1a, 2d
  S0.3.2/3 settings · tracing        :i1c, after i1b, 1d
  F0.4 contracts → TS types          :i1d, after i1c, 1d
  F2.1 parsing · chunking            :crit, i1e, after i1d, 1d
  F2.2 embeddings · storage · upload :crit, i1f, after i1e, 2d
  S3.1.1 graph skeleton · POST/GET   :crit, i1g, after i1f, 1d
  S1.1.1/3 eCertis cache · enum      :i1h, after i1g, 1d
  S3.2.1 extraction (S2.3.2 wrap)    :crit, i1i, after i1h, 2d
  S4.0.1 design canvas (/design)     :crit, i1k, after i1i, 1d
  Design confirmed by user           :milestone, md, after i1k, 0d
  S4.1.2 · S4.2.2 · S4.5.1 shell     :i1j, after i1k, 2d
  M1 requirement list                :milestone, m1, after i1j, 0d

  section Inc 2 · matrix in browser
  S1.1.2 eCertis tool · F1.4 registry:i2a, after i1j, 1d
  F2.4 profile · RAG tools           :i2b, after i2a, 2d
  F3.3 check_reqs Send + tests       :crit, i2c, after i2b, 2d
  S4.5.1 matrix rows (read-only)     :i2d, after i2c, 1d
  M2 matrix                          :milestone, m2, after i2d, 0d

  section Inc 3 · review round-trip
  F3.4 verdict · interrupt · review  :crit, i3a, after i2d, 2d
  S3.4.4 failure handling · S2.4.3 seed :i3b, after i3a, 1d
  S4.5.2/3 row editor · confirm      :crit, i3c, after i3b, 2d
  S7.3 architecture.md               :i3d, after i3c, 1d
  M3 review round-trip               :milestone, m3, after i3d, 0d

  section Inc 4 · graded coverage
  S0.3.1 auth · S4.1.1 login         :i4a, after i3d, 1d
  S4.2.1 company form                :i4b, after i4a, 1d
  F1.2 TED · S3.2.2 · S4.3.1 new bid :i4c, after i4b, 2d
  S4.4.1 dashboard · S1.3.1 currency :i4d, after i4c, 1d
  F2.3 guards · S5.3 classifier      :i4e, after i4d, 1d
  F3.5 chat · S4.6.1                 :i4f, after i4e, 1d
  S5.1 · S5.2 · S4.6.2 dev panel     :i4g, after i4f, 2d
  S4.6.3 feedback                    :i4h, after i4g, 1d
  M4 graded coverage                 :milestone, m4, after i4h, 0d

  section Inc 5 · submission-ready
  S7.1 DeepEval report               :crit, i5a, after i4h, 2d
  S7.7 Playwright smoke              :i5c, after i5a, 1d
  S7.4 user guide                    :crit, i5d, after i5c, 1d
  S7.5/7.6 critique · README         :i5e, after i5d, 1d
  M5 SUBMISSION LINE                 :milestone, m5, after i5e, 0d

  section Inc 6–7 · stretch
  E5 BYOK (S5.4–5.6, S4.6.4)         :i6a, after i5e, 3d
  S2.1.2 Docling parser              :i6b, after i6a, 1d
  E8 deploy (optional)               :i7, after i6b, 1d

  section Content · wait-fillers
  S6.1 FR pack · S6.2 EN notice      :c1, after i1a, 2d
  S6.3 demo GmbH documents           :c2, after i2a, 2d
  S6.4 golden labels · S3.2.3 recall :c3, after c2, 3d
  S6.5 adversarial PDFs              :c4, after i3a, 1d
  S7.2 ADRs (continuous)             :c5, 2026-09-14, 45d
```

## 6. Story board

Sorted by increment (the plan's *Delivery order*); lane is a grouping tag only. `needs` lists hard prerequisites. Priority Could rows are never started before the submission line (end of Increment 5).

| Inc | Lane | Story | Size | Priority | needs |
|---|---|---|---|---|---|
| 0 | gate | SP.1 spike: extract + check on DE fixture, recall figure, go/pivot ADR | M | Must | S6.1 (DE) |
| 0 | D | S6.1 DE + FR fixture tenders, SOURCES.md | M | Must | — |
| 1 | gate | S0.1.4 GitHub Actions: lint, types, pytest ≥80% cov, deps-check, api.ts drift | M | Must | S0.1.3 |
| 1 | gate | S0.1.1 layout, uv, create-next-app, shadcn | S | Must | — |
| 1 | gate | S0.1.2 docker-compose, env, task runner | M | Must | — |
| 1 | gate | S0.1.3 ruff, pyright, pytest, eslint, pre-commit, `make deps` / `deps-check` guard | M | Must | — |
| 1 | gate | S0.2.1 Supabase EU project, bucket, migrations runner | M | Must | — |
| 1 | gate | S0.2.2 db.py pool, checkpointer + store factories | M | Must | S0.2.1 |
| 1 | gate | S0.2.3 read-model tables incl. provider_keys, llm_usage | M | Must | S0.2.1 |
| 1 | gate | S0.3.2 settings.default.yaml, llm.py factory (OpenRouter) | S | Must | — |
| 1 | gate | S0.3.3 LangSmith wiring | S | Must | — |
| 1 | gate | S0.4.1 Pydantic contracts and enums | M | Must | — |
| 1 | gate | S0.4.2 router stubs, openapi-typescript → api.ts | S | Must | S0.4.1 |
| 1 | A | S1.1.1 build_ecertis_cache.py | M | Must | S0.1 |
| 1 | A | S1.1.3 criterion enum from cache | S | Must | S1.1.1 |
| 1 | B | S2.1.1 Parser protocol, pymupdf parser | M | Must | S0.1 |
| 1 | B | S2.1.3 chunker 800/100 | S | Must | S2.1.1 |
| 1 | B | S2.2.1 embeddings via OpenRouter, pgvector helpers | M | Must | S0.2.2 |
| 1 | B | S2.2.2 Storage upload, signed URLs | M | Must | S0.2.1 |
| 1 | B | S2.2.3 POST /documents pipeline | M | Must | S2.2.1, S2.2.2 |
| 1 | B | S2.3.2 data-block wrapper | S | Must | — |
| 1 | B | S3.1.1 BidState, graph skeleton, POST/GET bids | M | Must | S0.2.2 |
| 1 | B | S3.2.1 extract_reqs sections + dedupe | L | Must | S1.1.3, S2.3.2 (recall via S3.2.3) |
| 1 | C | S4.0.1 design canvas via `/design`; user confirms before workspace components are coded | M | Must | S0.4.1 |
| 1 | C | S4.1.2 layout, nav, theme | S | Must | S0.4.2 (hand-written types ok) |
| 1 | C | S4.2.2 document upload with status | M | Must | S4.1.2, S2.2.3 |
| 1 | C | S4.5.1 workspace two-pane, react-pdf, polling (matrix-row criterion finishes in Inc 2) | L | Must | S3.1.1, S4.0.1 |
| 1 | D | S6.2 EN golden tender | M | Must | — |
| 2 | B | S3.2.3 recall script against golden labels (reused by S7.1) | S | Must | S3.2.1, S6.4 |
| 2 | A | S1.1.2 ecertis_evidence_lookup tool | M | Must | S1.1.1 |
| 2 | A | S1.4.1 tool registry with manifests | M | Must | S1.1.2, S2.4.2 (S1.2.2, S1.3.1 join in Inc 4) |
| 2 | B | S2.4.1 company profile endpoints, Store namespace | M | Must | S0.2.3 (dev auth until S0.3.1) |
| 2 | B | S2.4.2 company_rag_search, tender_rag_search tools | M | Must | S2.2.1 |
| 2 | B | S3.3.1 check_reqs Send fan-out | L | Must | S1.4.1, S2.4.2 |
| 2 | B | S3.3.2 fake-model tests per status branch | M | Must | S3.3.1 |
| 2 | D | S6.3 demo GmbH document pack | L | Must | — |
| 2 | D | S6.4 golden set labels (LLM-assisted, verified) | L | Must | S6.1, S6.2 |
| 3 | B | S2.4.3 seed_demo_company.py | M | Must | S6.3 |
| 3 | B | S3.4.1 score_verdict rules + explanation | M | Must | S3.3.1 |
| 3 | B | S3.4.2 interrupt, apply_review, POST review | M | Must | S3.4.1 |
| 3 | B | S3.4.3 read-model writers | M | Must | S3.4.2 |
| 3 | B | S3.4.4 failure handling | M | Must | S3.4.2 |
| 3 | C | S4.5.2 matrix rows editor, evidence, eCertis card | L | Must | S3.4.3, S4.0.1 |
| 3 | C | S4.5.3 verdict panel, confirm/override | M | Must | S3.4.2, S4.0.1 |
| 3 | D | S6.5 adversarial injection PDFs | S | Must | — |
| 3 | E | S7.3 architecture.md | M | Must | S3.4 |
| 4 | gate | S0.3.1 Supabase Auth, JWT deps, is_developer | M | Must | S0.2.1 |
| 4 | A | S1.2.1 ted_client (expert query, no OR in IN) | M | Must | — |
| 4 | A | S1.2.2 search_ted tool, GET /tenders/search | S | Must | S1.2.1 |
| 4 | A | S1.3.1 Frankfurter client, currency_convert | S | Must | — |
| 4 | A | S5.1 vendor slug switching inside OpenRouter | M | Must | S1.4.1 |
| 4 | A | S5.2 LangSmith metadata, GET /dev/costs | M | Must | S0.3.2 |
| 4 | A | S5.3 luna injection classifier on flagged chunks | S | Must | S2.3.1 |
| 4 | B | S2.3.1 injection heuristics | M | Must | S6.5 |
| 4 | B | S2.3.3 slowapi limits | S | Must | — |
| 4 | B | S3.2.2 fold TED notice fields into requirements | S | Must | S1.2.1 |
| 4 | B | S3.5.1 chat_graph, POST chat | M | Must | S2.4.2, S3.4.3 |
| 4 | C | S4.1.1 Supabase client, login, API client | M | Must | S0.4.2 |
| 4 | C | S4.2.1 company profile form | M | Must | S4.1.1 |
| 4 | C | S4.3.1 TED search → pick → upload → start | M | Must | S4.1.1 |
| 4 | C | S4.4.1 dashboard | M | Must | S4.1.1, S4.0.1 |
| 4 | C | S4.6.1 chat page | M | Must | S3.5.1 |
| 4 | C | S4.6.2 /dev panel | M | Must | S5.2 |
| 4 | C | S4.6.3 feedback thumbs | S | Must | — |
| 5 | E | S7.1 DeepEval suite + REPORT.md | M | Must | E3, S6.4 |
| 5 | E | S7.7 Playwright smoke test | M | Must | E4 Must stories |
| 5 | E | S7.4 user guide, three worked examples | M | Must | E4 Must stories |
| 5 | E | S7.5 critique.md | S | Must | — |
| 5 | E | S7.6 README, trim project.md, CLAUDE.md commands | S | Must | — |
| 6 | A | S5.4 BYOK backend: crypto, provider_keys, verify-on-save | M | Could | S0.2.3, S0.3.1 |
| 6 | A | S5.5 BYOK factory: resolve(company, role) with fallback | M | Could | S5.4 |
| 6 | A | S5.6 cost accounting for direct providers, llm_usage | S | Could | S5.5 |
| 6 | B | S2.1.2 Docling parser (switchable) | M | Could | S2.1.1 |
| 6 | C | S4.6.4 Settings → AI provider (BYOK) page | M | Could | S5.4 |
| 7 | E | S8.1 deploy (optional) | M | Optional | all |
| all | E | S7.2 ADRs, one per decision as it lands | S each | Must | — |
