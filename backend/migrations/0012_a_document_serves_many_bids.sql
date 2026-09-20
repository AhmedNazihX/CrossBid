-- 0012 — a tender document serves many bids, and is embedded once.
--
-- `documents.bid_id` was a single nullable column, so a document belonged to one analysis.
-- Re-analysing the same tender meant uploading the pack a second time — a new row, a new
-- Storage object and a second embedding pass over every page. Found on 2026-09-18 comparing
-- two checking models on one FRONTEX notice: the six PDFs the first analysis held were not
-- offered for the second at all, and there was no way to use them other than uploading them
-- again.
--
-- `tender_chunks.bid_id` was `NOT NULL` for the same reason, and it is what made the second
-- embedding pass unavoidable: the vectors were the *bid's*, not the document's, so nothing a
-- second analysis did could reach them.
--
-- `company_chunks` (0001) has had the right shape all along — no `bid_id`, embedded once at
-- upload, shared by every bid. This migration gives the tender corpus that same shape and
-- moves the bid-to-document relation out of `documents` into a table where "many" can be
-- said. The comment above both chunk tables in 0001 already claimed they "only ever join
-- through `documents`"; after this, that is true of both of them.
--
-- **THIS MIGRATION IS NOT ONLINE-SAFE.** The two `drop column`s break the previously deployed
-- API the instant they commit, because every one of its document statements names `bid_id` by
-- column; and the new code cannot run against the old schema, because `bid_documents` does not
-- exist there. There is no version overlap. Stop the API, migrate, deploy. See ADR-0103.

begin;

-- ---------------------------------------------------------------- the link

create table if not exists bid_documents (
    bid_id      uuid not null references bids (id) on delete cascade,
    document_id uuid not null references documents (id) on delete cascade,
    -- Carried rather than joined for, the same way `tender_chunks.company_id` is: tenant
    -- isolation is application-level (ADR-0009), so every statement reading this table must be
    -- able to write its own `company_id = %(company_id)s` without a second join.
    company_id  uuid not null references companies (id) on delete cascade,
    created_at  timestamptz not null default now(),
    -- The whole row is the key. One bid citing one document twice is the same fact stated
    -- twice, and this is what makes the retrieval join incapable of returning a passage once
    -- per citing bid — a fan-out that raises no error and reads downstream as several
    -- independent pieces of evidence for one clause.
    primary key (bid_id, document_id)
);

-- "Which bids cite this document?" — the delete rule and the `bid_count` the picker reads.
-- The primary key already serves the other direction.
create index if not exists bid_documents_document_id_idx on bid_documents (document_id);
create index if not exists bid_documents_company_id_idx on bid_documents (company_id);

-- ---------------------------------------------------------------- backfill, before any drop

insert into bid_documents (bid_id, document_id, company_id, created_at)
select documents.bid_id, documents.id, documents.company_id, documents.created_at
from documents
where documents.bid_id is not null
on conflict do nothing;

-- ---------------------------------------------------------------- the link cannot cross a tenant
--
-- `company_id` is denormalised above, so on its own nothing stops a row naming company A's bid
-- and company B's document. A composite foreign key makes that unrepresentable rather than
-- merely wrong. Each target needs a unique index on `(company_id, id)`; Postgres accepts a
-- unique index as a foreign-key target, and both tables are small enough that building them
-- is instant.

create unique index if not exists documents_company_id_id_key on documents (company_id, id);
create unique index if not exists bids_company_id_id_key on bids (company_id, id);

alter table bid_documents drop constraint if exists bid_documents_document_scope_fkey;
alter table bid_documents add constraint bid_documents_document_scope_fkey
    foreign key (company_id, document_id) references documents (company_id, id)
    on delete cascade;

alter table bid_documents drop constraint if exists bid_documents_bid_scope_fkey;
alter table bid_documents add constraint bid_documents_bid_scope_fkey
    foreign key (company_id, bid_id) references bids (company_id, id)
    on delete cascade;

-- ---------------------------------------------------------------- collapse duplicate chunk sets
--
-- `tender_chunks` may hold several sets of rows for one document — one per bid that ever
-- indexed it, because `replace_tender_chunks`' idempotency delete was scoped
-- `(company_id, bid_id, document_id)`. Once `bid_id` is gone those sets become
-- indistinguishable duplicates of each other, and every retrieval would return each passage
-- once per old bid.
--
-- What is removed is redundant rather than unique: the same PDF through the same chunker and
-- the same embedding model (`text-embedding-3-small`, pinned by the column's dimensionality)
-- produces the same text and the same vectors, so the surviving set is equivalent to the ones
-- deleted. The newest set is kept because it is the one the most recent chunker wrote.
--
-- On the hosted project this is expected to delete **nothing**: the old `and bid_id is null`
-- in `ATTACH_DOCUMENTS` prevented a document from ever reaching a second bid. It is written
-- anyway because `scripts/index_pack.py`'s `_rename_bid` can re-point a seeded bid and leave
-- two sets behind, and because a migration must not depend on the invariant it is removing.
--
-- **THIS DELETE IS IRREVERSIBLE.** Take a backup or a restore point first.

delete from tender_chunks tc
using (
    select ranked.document_id, ranked.bid_id
    from (
        select document_id,
               bid_id,
               row_number() over (
                   partition by document_id
                   order by max(created_at) desc, count(*) desc, bid_id
               ) as rank
        from tender_chunks
        group by document_id, bid_id
    ) ranked
    where ranked.rank > 1
) doomed
where tc.document_id = doomed.document_id
  and tc.bid_id = doomed.bid_id;

-- ---------------------------------------------------------------- the drops

drop index if exists tender_chunks_bid_id_idx;
alter table tender_chunks drop column if exists bid_id;

drop index if exists documents_bid_id_idx;
alter table documents drop column if exists bid_id;

commit;
