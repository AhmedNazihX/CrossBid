-- 0005_espd_requests — the published DUME becomes an uploadable kind, and its requirements
-- become rows that cite a criterion instead of a page (S2.5.1).
--
-- Two schema facts change, both because an ESPD request is not a PDF.
--
-- 1. `documents.kind` gains `tender_espd_request`. The upload boundary is an accept-list
--    keyed on kind — every other kind is still PDF-only — so the kind is what carries the
--    permission, and the constraint has to know the value before a row can exist.
--
-- 2. `requirements.page` becomes nullable, and a new `requirements.source` says why. A DUME
--    is XML: it has no pages, and a row claiming `p. 1` would render in the workspace as a
--    citation the reviewer can click and land nowhere. The pair is constrained together —
--    `source = 'espd_request'` if and only if `page is null` — so neither an extracted quote
--    without its page nor an ESPD criterion pretending to have one can be written, by this
--    application or by hand. `Requirement` enforces the same invariant in Pydantic; this is
--    the half a direct SQL write cannot bypass.
--
-- `source` defaults to `tender_document` so the rows written before this migration (every
-- one of them an extracted quote with a page) stay valid, and so a writer that does not
-- know about ESPD requests keeps working. 0001 and 0004 are immutable once applied
-- (ADR-0009), hence the drop-and-re-add of `documents_kind_check`.

begin;

alter table documents drop constraint if exists documents_kind_check;
alter table documents add constraint documents_kind_check check (kind in (
    'company_evidence', 'tender_document', 'tender_notice', 'tender_espd_request'
));

alter table requirements
    add column if not exists source text not null default 'tender_document';

alter table requirements drop constraint if exists requirements_source_check;
alter table requirements add constraint requirements_source_check check (source in (
    'tender_document', 'espd_request'
));

-- The column check `page >= 1` from 0001 stays: a NULL passes a CHECK, so it keeps meaning
-- "if there is a page, it is 1-indexed".
alter table requirements alter column page drop not null;

alter table requirements drop constraint if exists requirements_page_matches_source_check;
alter table requirements add constraint requirements_page_matches_source_check check (
    (source = 'espd_request') = (page is null)
);

commit;
