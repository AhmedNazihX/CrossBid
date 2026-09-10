# Crossbid — structure and roadmap

Visual companion to `project-plan.md`. Diagrams are Mermaid fences, so they render in GitHub, VS Code (Markdown Preview Mermaid Support), and any MDX site with a Mermaid plugin. Sizes: S about 1 h, M about 2 h, L about 4 to 5 h. One roadmap "day" is a 4-hour block.

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

Feature-level (stories roll up). Thick red edges are the critical path. Dashed edges are content or contract inputs that carry no code dependency.

```mermaid
flowchart LR
  classDef crit fill:#fde8e8,stroke:#c0392b,stroke-width:2px,color:#1B2430;
  classDef laneA fill:#eaf4ff,stroke:#2c6fbb,color:#1B2430;
  classDef laneB fill:#eafbea,stroke:#2e8b57,color:#1B2430;
  classDef laneC fill:#fff4e5,stroke:#d98b00,color:#1B2430;
  classDef laneD fill:#f5eaff,stroke:#7b4bb5,color:#1B2430;
  classDef laneE fill:#f0f0f0,stroke:#666,color:#1B2430;

  subgraph E0["E0 Foundations (gate)"]
    F01["F0.1 repo & tooling"]:::crit
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
    F32["F3.2 extraction"]:::crit
    F33["F3.3 check_reqs (Send)"]:::crit
    F34["F3.4 verdict · interrupt · review"]:::crit
    F35["F3.5 ask the tender"]:::laneB
  end

  subgraph LaneC["Lane C"]
    F41["F4.1 shell & auth"]:::laneC
    F42["F4.2 onboarding"]:::laneC
    F43["F4.3 new bid"]:::laneC
    F44["F4.4 dashboard"]:::laneC
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

  F01 ==> F02 ==> F21 ==> F22 ==> F31 ==> F32 ==> F33 ==> F34 ==> F45 ==> S71
  F02 --> F03 --> F04
  F02 --> F11 & F12 & F13
  F11 & F12 & F13 --> F14
  F14 --> F33
  F22 --> F23 --> F32
  F22 --> F24 --> F33
  F03 --> F24
  F03 --> E5
  F14 --> E5
  F04 -.-> F41 --> F42 & F43 & F44
  F31 -.-> F45
  F34 --> F46
  F35 --> F46
  E5 --> F46
  F33 --> F35
  S61 -.-> F21
  S63 -.-> F24
  S64 -.-> S71
  F45 --> S74
  S74 --> E8
  F01 -.-> S72
```

## 5. Roadmap by lane

Feature-level Gantt. Dates are placeholders from a nominal start on 2026-09-14; only the ordering and overlaps matter. Lane D starts before E0 is finished because it has no code dependency.

```mermaid
gantt
  title Crossbid roadmap (1 day = one 4-hour block)
  dateFormat YYYY-MM-DD
  axisFormat %d %b
  excludes weekends

  section E0 Foundations
  F0.1 repo & tooling            :crit, f01, 2026-09-14, 1d
  F0.2 db & persistence          :crit, f02, after f01, 2d
  F0.3 auth & settings           :f03, after f02, 1d
  F0.4 contracts → TS types      :f04, after f03, 1d

  section Lane A · reference & providers
  F1.1 eCertis cache + tool      :f11, after f02, 1d
  F1.2 TED client + tool         :f12, after f11, 1d
  F1.3 currency tool             :f13, after f12, 1d
  F1.4 tool registry             :f14, after f13, 1d
  E5 multi-model · BYOK · costs  :e5, after f14, 3d

  section Lane B · ingestion & agent
  F2.1 parsing & chunking        :crit, f21, after f02, 1d
  F2.2 embeddings & storage      :crit, f22, after f21, 2d
  F2.3 guards                    :f23, after f22, 1d
  F2.4 profile · memory · RAG    :f24, after f22, 2d
  F3.1 state & skeleton          :crit, f31, after f24, 1d
  F3.2 extraction                :crit, f32, after f31, 2d
  F3.3 check_reqs (Send)         :crit, f33, after f32, 2d
  F3.4 verdict · interrupt       :crit, f34, after f33, 2d
  F3.5 ask the tender            :f35, after f34, 1d

  section Lane C · web app
  F4.1 shell & auth              :f41, after f04, 1d
  F4.2 onboarding                :f42, after f41, 1d
  F4.3 new bid                   :f43, after f42, 1d
  F4.4 dashboard                 :f44, after f43, 1d
  F4.5 bid workspace             :crit, f45, after f34, 3d
  F4.6 chat · dev · settings     :f46, after f45, 2d

  section Lane D · content
  S6.1/6.2 fixture tenders       :s61, 2026-09-14, 1d
  S6.3 demo GmbH documents       :s63, after s61, 2d
  S6.4 golden set labels         :s64, after s63, 2d
  S6.5 adversarial fixtures      :s65, after s64, 1d

  section Lane E · eval & docs
  S7.2 ADRs (continuous)         :s72, 2026-09-14, 20d
  S7.3 architecture.md           :s73, after f34, 1d
  S7.1 DeepEval report           :crit, s71, after f45, 1d
  S7.4 user guide · S7.7 e2e     :s74, after f46, 2d
  S7.5/7.6 critique · README     :s75, after s74, 1d
  E8 deploy (optional)           :milestone, e8, after s75, 0d
```

## 6. Story board

Order inside each lane is the intended execution order. `needs` lists hard prerequisites outside the lane.

| Lane | Order | Story | Size | needs |
|---|---|---|---|---|
| gate | 1 | S0.1.1 layout, uv, create-next-app, shadcn | S | — |
| gate | 2 | S0.1.2 docker-compose, env, task runner | M | — |
| gate | 3 | S0.1.3 ruff, pyright, pytest, eslint, pre-commit, `make deps` / `deps-check` guard | M | — |
| gate | 4 | S0.2.1 Supabase EU project, bucket, migrations runner | M | — |
| gate | 5 | S0.2.2 db.py pool, checkpointer + store factories | M | S0.2.1 |
| gate | 6 | S0.2.3 read-model tables incl. provider_keys, llm_usage | M | S0.2.1 |
| gate | 7 | S0.3.1 Supabase Auth, JWT deps, is_developer | M | S0.2.1 |
| gate | 8 | S0.3.2 settings.default.yaml, llm.py factory (OpenRouter) | S | — |
| gate | 9 | S0.3.3 LangSmith wiring | S | — |
| gate | 10 | S0.4.1 Pydantic contracts and enums | M | — |
| gate | 11 | S0.4.2 router stubs, openapi-typescript → api.ts | S | S0.4.1 |
| A | 1 | S1.1.1 build_ecertis_cache.py | M | S0.1 |
| A | 2 | S1.1.2 ecertis_evidence_lookup tool | M | S1.1.1 |
| A | 3 | S1.1.3 criterion enum from cache | S | S1.1.1 |
| A | 4 | S1.2.1 ted_client (expert query, no OR in IN) | M | — |
| A | 5 | S1.2.2 search_ted tool, GET /tenders/search | S | S1.2.1 |
| A | 6 | S1.3.1 Frankfurter client, currency_convert | S | — |
| A | 7 | S1.4.1 tool registry with manifests | M | tools above |
| A | 8 | S5.1 vendor slug switching inside OpenRouter | M | S1.4.1 |
| A | 9 | S5.4 BYOK backend: crypto, provider_keys, verify-on-save | M | S0.2.3, S0.3.1 |
| A | 10 | S5.5 BYOK factory: resolve(company, role) with fallback | M | S5.4 |
| A | 11 | S5.6 cost accounting for direct providers, llm_usage | S | S5.5 |
| A | 12 | S5.2 LangSmith metadata, GET /dev/costs | M | S5.6 |
| A | 13 | S5.3 luna injection classifier on flagged chunks | S | S2.3.1 |
| B | 1 | S2.1.1 Parser protocol, pymupdf parser | M | S0.1 |
| B | 2 | S2.1.3 chunker 800/100 | S | S2.1.1 |
| B | 3 | S2.2.1 embeddings via OpenRouter, pgvector helpers | M | S0.2.2 |
| B | 4 | S2.2.2 Storage upload, signed URLs | M | S0.2.1 |
| B | 5 | S2.2.3 POST /documents pipeline | M | S2.2.1, S2.2.2 |
| B | 6 | S2.3.1 injection heuristics | M | S6.5 |
| B | 7 | S2.3.2 data-block wrapper | S | — |
| B | 8 | S2.3.3 slowapi limits | S | — |
| B | 9 | S2.4.1 company profile endpoints, Store namespace | M | S0.3.1 |
| B | 10 | S2.4.2 company_rag_search, tender_rag_search tools | M | S2.2.1 |
| B | 11 | S2.4.3 seed_demo_company.py | M | S6.3 |
| B | 12 | S2.1.2 Docling parser (switchable) | M | S2.1.1 |
| B | 13 | S3.1.1 BidState, graph skeleton, POST/GET bids | M | S0.2.2 |
| B | 14 | S3.2.2 fold TED notice fields into requirements | S | S1.2.1 |
| B | 15 | S3.2.1 extract_reqs sections + dedupe | L | S1.1.3 |
| B | 16 | S3.3.1 check_reqs Send fan-out | L | S1.4.1, S2.4.2 |
| B | 17 | S3.3.2 fake-model tests per status branch | M | S3.3.1 |
| B | 18 | S3.4.1 score_verdict rules + explanation | M | S3.3.1 |
| B | 19 | S3.4.2 interrupt, apply_review, POST review | M | S3.4.1 |
| B | 20 | S3.4.3 read-model writers | M | S3.4.2 |
| B | 21 | S3.4.4 failure handling | M | S3.4.2 |
| B | 22 | S3.5.1 chat_graph, POST chat | M | S2.4.2, S3.4.3 |
| C | 1 | S4.1.1 Supabase client, login, API client | M | S0.4.2 |
| C | 2 | S4.1.2 layout, nav, theme | S | S4.1.1 |
| C | 3 | S4.2.1 company profile form | M | S4.1.1 |
| C | 4 | S4.2.2 document upload with status | M | S4.1.1 |
| C | 5 | S4.3.1 TED search → pick → upload → start | M | S4.1.1 |
| C | 6 | S4.4.1 dashboard | M | S4.1.1 |
| C | 7 | S4.5.1 workspace two-pane, react-pdf, polling | L | S3.1.1 |
| C | 8 | S4.5.2 matrix rows editor, evidence, eCertis card | L | S3.4.3 |
| C | 9 | S4.5.3 verdict panel, confirm/override | M | S3.4.2 |
| C | 10 | S4.6.4 Settings → AI provider (BYOK) page | M | S5.4 |
| C | 11 | S4.6.1 chat page | M | S3.5.1 |
| C | 12 | S4.6.2 /dev panel | M | S5.2 |
| C | 13 | S4.6.3 feedback thumbs | S | — |
| D | 1 | S6.1 DE + FR fixture tenders, SOURCES.md | M | — |
| D | 2 | S6.2 EN golden tender | M | — |
| D | 3 | S6.3 demo GmbH document pack | L | — |
| D | 4 | S6.5 adversarial injection PDFs | S | — |
| D | 5 | S6.4 golden set labels (LLM-assisted, verified) | L | S6.1, S6.2 |
| E | ∞ | S7.2 ADRs, one per decision as it lands | S each | — |
| E | 1 | S7.3 architecture.md | M | S3.4 |
| E | 2 | S7.1 DeepEval suite + REPORT.md | M | E3, S6.4 |
| E | 3 | S7.7 Playwright smoke test | M | E4 |
| E | 4 | S7.4 user guide, three worked examples | M | E4 |
| E | 5 | S7.5 critique.md | S | — |
| E | 6 | S7.6 README, trim project.md, CLAUDE.md commands | S | — |
| E | 7 | S8.1 deploy (optional) | M | all |
