-- 0001_init — read-model tables, vector storage, and the settings row.
--
-- Story S0.2.1 / S0.2.3. Applied by `uv run python scripts/migrate.py` (or `make migrate`).
--
-- LangGraph's own tables (checkpoints, writes, the Store) are NOT created here. They are
-- created by `PostgresSaver.setup()` and `PostgresStore.setup()` at API startup (S0.2.2), and
-- this schema never reads them: `readmodel/` is a projection written after `score_verdict` and
-- again after the review resumes. If the two ever disagree, the checkpoint is right and the
-- projection has a bug.
--
-- Conventions, following the Supabase Postgres guidance:
--   * `text`, never `varchar(n)` — no artificial limits, same performance.
--   * `timestamptz`, never `timestamp` — a bid deadline without a zone is a bug waiting.
--   * `numeric`, never float, for money.
--   * Every foreign key is indexed; Postgres does not do it for you, and an unindexed FK
--     turns a cascade into a full scan.
--   * Enum columns are `text` with a check constraint rather than a Postgres enum type:
--     altering an enum is awkward in migrations, and the values must stay identical to the
--     Pydantic StrEnums in `crossbid/models/`. `tests/unit/test_migrations.py` asserts that
--     equality, so drift fails CI rather than surfacing as a runtime insert error.
--
-- Tenant isolation is application-level `company_id` filtering, not RLS. This is a settled
-- decision, and it is the right one *here* for a concrete reason: the `postgres` role this
-- API connects as has `BYPASSRLS = true`, so policies would be silently inert. Making RLS
-- real would need a dedicated non-BYPASSRLS role and a different DSN. Every tenant-scoped
-- table therefore carries `company_id NOT NULL` and leads its composite index with it, so
-- adding policies later is additive rather than a rewrite. See docs/decisions.md ADR-0009.

begin;

-- pgvector 0.8.2 on this project. `vector` lives in the `extensions` schema on Supabase but
-- is on the search_path; creating it here keeps a fresh local Postgres working too.
create extension if not exists vector;

-- gen_random_uuid() is in pgcrypto on older servers and core on newer ones; harmless either way.
create extension if not exists pgcrypto;


-- ---------------------------------------------------------------- companies and providers

-- Ids that appear in a URL are UUIDs, not sequential integers. `pg_uuidv7` is not available
-- on this project and the server is PG 17 (no built-in `uuidv7()`), so these are v4. The
-- index fragmentation the guidance warns about is a non-issue at this corpus size, whereas an
-- enumerable `/bids/1` would let one company probe for another's bids — and with
-- application-level isolation there is no second line of defence. Tables never addressed by
-- id in a URL use `bigint identity` instead.
create table if not exists companies (
    id              uuid primary key default gen_random_uuid(),
    owner_user_id   uuid not null,
    name            text not null,
    country         text not null check (country ~ '^[a-z]{2}$'),
    legal_form      text not null,
    language        text not null default 'de',
    tone            text not null default 'plain',
    active_provider text not null default 'openrouter',
    profile         jsonb not null default '{}'::jsonb,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),
    constraint companies_legal_form_check check (legal_form in (
        'gmbh', 'ug', 'ag', 'sarl', 'sas', 'sa', 'bv', 'sp_zoo', 'sole_trader', 'other'
    )),
    constraint companies_tone_check check (tone in ('plain', 'formal', 'brief')),
    constraint companies_active_provider_check check (active_provider in (
        'openrouter', 'openai', 'anthropic'
    ))
);

-- One company per user (settled decision), so this is the lookup every request makes.
create unique index if not exists companies_owner_user_id_key on companies (owner_user_id);


-- Bring-your-own-key storage (S5.4-S5.6, stretch). The key is encrypted with Fernet before it
-- reaches Postgres; `bytea` holds the token. `key_hint` is the last 4 characters only — the
-- one thing that may ever leave the server.
create table if not exists provider_keys (
    company_id    uuid not null references companies (id) on delete cascade,
    provider      text not null,
    encrypted_key bytea not null,
    key_hint      text not null check (char_length(key_hint) = 4),
    verified_at   timestamptz,
    created_at    timestamptz not null default now(),
    primary key (company_id, provider),
    constraint provider_keys_provider_check check (provider in (
        'openrouter', 'openai', 'anthropic'
    ))
);


-- ---------------------------------------------------------------- bids

create table if not exists bids (
    id                      uuid primary key default gen_random_uuid(),
    company_id              uuid not null references companies (id) on delete cascade,
    ted_publication_number  text,
    title                   text not null,
    buyer                   text,
    source_language         text,
    deadline                timestamptz,
    -- The LangGraph thread this bid runs on: `bid:{id}`. Chat runs on `bid:{id}:chat`.
    thread_id               text not null unique,
    status                  text not null default 'queued',
    verdict                 jsonb,
    provider_used           text,
    created_at              timestamptz not null default now(),
    updated_at              timestamptz not null default now(),
    constraint bids_status_check check (status in (
        'queued', 'parsing', 'extracting', 'checking', 'scoring',
        'awaiting_review', 'applying_review', 'complete', 'failed'
    ))
);

-- The dashboard lists a company's bids newest first, so the index leads with the tenant key
-- and carries the sort column — equality first, range last.
create index if not exists bids_company_id_created_at_idx
    on bids (company_id, created_at desc);

-- "Which bids still need a human?" is the dashboard's other query.
create index if not exists bids_company_id_status_idx on bids (company_id, status);


-- ---------------------------------------------------------------- documents

create table if not exists documents (
    id             uuid primary key default gen_random_uuid(),
    company_id     uuid not null references companies (id) on delete cascade,
    -- Null for a company's own evidence pack; set for a tender's procurement documents.
    bid_id         uuid references bids (id) on delete cascade,
    kind           text not null,
    name           text not null,
    storage_path   text not null,
    pages          integer not null default 0 check (pages >= 0),
    -- Pages with no extractable text. Surfaced to the reviewer as "not read" rather than
    -- silently dropped, because OCR is out of scope (S2.1.1).
    unread_pages   integer[] not null default '{}',
    flagged_chunks integer[] not null default '{}',
    expiry         date,
    created_at     timestamptz not null default now(),
    constraint documents_kind_check check (kind in (
        'company_evidence', 'tender_document', 'tender_notice'
    ))
);

create index if not exists documents_company_id_kind_idx on documents (company_id, kind);
create index if not exists documents_bid_id_idx on documents (bid_id);


-- ---------------------------------------------------------------- chunks and embeddings

-- 1536 dimensions: `openai/text-embedding-3-small` (ADR-0004). The dimension is baked into
-- the column type, so changing the embedding model means a migration AND re-embedding the
-- whole corpus. 1536 was chosen partly because it sits under pgvector's 2000-dimension index
-- limit, which is what makes the HNSW indexes below possible at all.
--
-- Two tables rather than one with a discriminator: a company's evidence corpus and a tender's
-- text are searched separately by two different tools, are deleted on different lifecycles,
-- and only ever join through `documents`. Keeping them apart keeps each ANN index small.

create table if not exists company_chunks (
    id          bigint generated always as identity primary key,
    document_id uuid not null references documents (id) on delete cascade,
    company_id  uuid not null references companies (id) on delete cascade,
    page        integer not null check (page >= 1),
    -- Every page the chunk's text came from; `page` above is where it starts, which is where
    -- the reviewer is sent (S2.1.3).
    pages       integer[] not null default '{}',
    text        text not null,
    token_count integer check (token_count is null or token_count >= 0),
    embedding   vector(1536),
    created_at  timestamptz not null default now()
);

create index if not exists company_chunks_company_id_idx on company_chunks (company_id);
create index if not exists company_chunks_document_id_idx on company_chunks (document_id);

-- Cosine distance: OpenAI embeddings are L2-normalised, so cosine and inner product rank
-- identically; cosine is the convention and reads unambiguously at the call site.
--
-- A caveat worth knowing before trusting this index: HNSW is an approximate index and pgvector
-- applies the `company_id` filter *after* the ANN scan, so a tenant with few chunks inside a
-- large corpus can lose recall. At this corpus size the planner will often prefer a sequential
-- scan anyway, which is exact. If the corpus grows, partial indexes per company or an
-- `iterative scan` setting are the levers.
create index if not exists company_chunks_embedding_idx
    on company_chunks using hnsw (embedding vector_cosine_ops);

create table if not exists tender_chunks (
    id          bigint generated always as identity primary key,
    document_id uuid not null references documents (id) on delete cascade,
    company_id  uuid not null references companies (id) on delete cascade,
    bid_id      uuid not null references bids (id) on delete cascade,
    page        integer not null check (page >= 1),
    pages       integer[] not null default '{}',
    text        text not null,
    token_count integer check (token_count is null or token_count >= 0),
    embedding   vector(1536),
    created_at  timestamptz not null default now()
);

create index if not exists tender_chunks_bid_id_idx on tender_chunks (bid_id);
create index if not exists tender_chunks_company_id_idx on tender_chunks (company_id);
create index if not exists tender_chunks_document_id_idx on tender_chunks (document_id);
create index if not exists tender_chunks_embedding_idx
    on tender_chunks using hnsw (embedding vector_cosine_ops);


-- ---------------------------------------------------------------- requirements

-- `stage` and `checkable` are not decoration. The SP.1 spike extracted 579 "mandatory"
-- requirements from one tender without `stage`, because standard contract terms are genuinely
-- phrased as obligations — they simply bind the winner after award rather than the bidder at
-- qualification time. Adding the discriminator cut the set to 238 with no loss of recall, and
-- `checkable` records which rows evidence can settle at all: the first checking round returned
-- "unclear" for every document-submission row, because no corpus of company facts can
-- establish "we submitted form X". See docs/decisions.md ADR-0003.
create table if not exists requirements (
    id                   uuid primary key default gen_random_uuid(),
    bid_id               uuid not null references bids (id) on delete cascade,
    company_id           uuid not null references companies (id) on delete cascade,
    category             text not null,
    kind                 text not null,
    stage                text not null,
    checkable            text not null,
    source_text          text not null,
    source_lang          text not null,
    document_name        text not null,
    page                 integer not null check (page >= 1),
    translation          text,
    ecertis_criterion_id uuid,
    threshold            jsonb,
    deadline             date,
    created_at           timestamptz not null default now(),
    constraint requirements_category_check check (category in (
        'formal', 'economic_financial', 'technical_professional', 'exclusion_ground', 'other'
    )),
    constraint requirements_kind_check check (kind in (
        'mandatory', 'optional', 'informational'
    )),
    constraint requirements_stage_check check (stage in (
        'bid_eligibility', 'contract_performance'
    )),
    constraint requirements_checkable_check check (checkable in (
        'company_property', 'document_submission', 'neither'
    ))
);

-- The workspace loads one bid's eligibility requirements; contract-performance rows are
-- stored but never shown in the matrix, so `stage` belongs in the index.
create index if not exists requirements_bid_id_stage_idx on requirements (bid_id, stage);
create index if not exists requirements_company_id_idx on requirements (company_id);


-- ---------------------------------------------------------------- matrix rows

create table if not exists matrix_rows (
    id               uuid primary key default gen_random_uuid(),
    requirement_id   uuid not null references requirements (id) on delete cascade,
    bid_id           uuid not null references bids (id) on delete cascade,
    company_id       uuid not null references companies (id) on delete cascade,
    status           text not null,
    evidence         jsonb not null default '[]'::jsonb,
    ecertis_evidence jsonb,
    agent_rationale  text not null,
    reviewer_status  text not null default 'pending',
    override_reason  text,
    attached_doc_ids uuid[] not null default '{}',
    reviewed_at      timestamptz,
    created_at       timestamptz not null default now(),
    constraint matrix_rows_status_check check (status in (
        'met', 'unmet', 'unclear', 'not_applicable'
    )),
    constraint matrix_rows_reviewer_status_check check (reviewer_status in (
        'pending', 'confirmed', 'overridden'
    )),
    -- The product's central promise, enforced in the database as well as in the Pydantic
    -- model: no row claims `met` without something to cite. A row the agent believes is
    -- satisfied but cannot cite is `unclear`, which sends it to a human.
    constraint matrix_rows_met_needs_evidence_check check (
        status <> 'met'
        or jsonb_array_length(evidence) > 0
        or cardinality(attached_doc_ids) > 0
    ),
    -- An override with no reason is unauditable, and the review record is the audit trail.
    constraint matrix_rows_override_needs_reason_check check (
        reviewer_status <> 'overridden' or override_reason is not null
    )
);

create unique index if not exists matrix_rows_requirement_id_key on matrix_rows (requirement_id);
create index if not exists matrix_rows_bid_id_idx on matrix_rows (bid_id);
create index if not exists matrix_rows_company_id_idx on matrix_rows (company_id);


-- ---------------------------------------------------------------- reviews and feedback

create table if not exists reviews (
    id              uuid primary key default gen_random_uuid(),
    bid_id          uuid not null references bids (id) on delete cascade,
    company_id      uuid not null references companies (id) on delete cascade,
    decision        text not null,
    agent_verdict   jsonb not null,
    final_verdict   jsonb not null,
    override_reason text,
    reviewer_id     uuid not null,
    created_at      timestamptz not null default now(),
    constraint reviews_decision_check check (decision in (
        'go', 'go_with_open_items', 'no_go'
    ))
);

create index if not exists reviews_bid_id_idx on reviews (bid_id);
create index if not exists reviews_company_id_idx on reviews (company_id);

create table if not exists feedback (
    id            bigint generated always as identity primary key,
    matrix_row_id uuid references matrix_rows (id) on delete cascade,
    bid_id        uuid not null references bids (id) on delete cascade,
    company_id    uuid not null references companies (id) on delete cascade,
    rating        smallint not null check (rating in (-1, 1)),
    comment       text,
    created_at    timestamptz not null default now()
);

create index if not exists feedback_bid_id_idx on feedback (bid_id);
create index if not exists feedback_matrix_row_id_idx on feedback (matrix_row_id);
create index if not exists feedback_company_id_idx on feedback (company_id);


-- ---------------------------------------------------------------- cost accounting

-- Cost comes from OpenRouter's own per-generation usage accounting, not from a local price
-- table, so any vendor slug is priced correctly (graded Medium 1).
create table if not exists llm_usage (
    id            bigint generated always as identity primary key,
    bid_id        uuid references bids (id) on delete cascade,
    company_id    uuid not null references companies (id) on delete cascade,
    node          text not null,
    provider      text not null,
    model         text not null,
    input_tokens  integer not null default 0 check (input_tokens >= 0),
    output_tokens integer not null default 0 check (output_tokens >= 0),
    cost_usd      numeric(12, 6) not null default 0 check (cost_usd >= 0),
    created_at    timestamptz not null default now()
);

create index if not exists llm_usage_bid_id_idx on llm_usage (bid_id);
create index if not exists llm_usage_company_id_created_at_idx
    on llm_usage (company_id, created_at desc);


-- ---------------------------------------------------------------- operator settings

-- Exactly one row, so the developer panel can tune behaviour without a redeploy. Every column
-- is nullable: NULL means "fall back to settings.default.yaml", which is what
-- `apply_app_settings_row` in crossbid/settings.py implements.
create table if not exists app_settings (
    id            integer primary key default 1 check (id = 1),
    models        jsonb,
    temperature   double precision check (temperature is null or temperature between 0 and 2),
    max_tokens    integer check (max_tokens is null or max_tokens > 0),
    system_prompt text,
    enabled_tools text[],
    updated_at    timestamptz not null default now()
);

insert into app_settings (id) values (1) on conflict (id) do nothing;

commit;
