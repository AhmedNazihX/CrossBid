-- S3.2.2 — requirements read out of the buyer's own structured TED fields.
--
-- A third `requirements.source`. `tender_document` is a verbatim quote a model found on a
-- numbered page and that was checked against that page; `espd_request` is a criterion the
-- buyer declared in a published DUME; `notice` is a fact the buyer published in TED's
-- structured fields — the deadline, the languages a tender may be written in, a stated
-- selection criterion. None of the three is read the way the others are, and a reviewer has
-- to be able to tell them apart, which is what the column is for.
--
-- The page constraint changes shape rather than gaining an exception. 0005 wrote it as
-- `(source = 'espd_request') = (page is null)`, which read "a DUME row has no page". The
-- rule it was always expressing is broader: **only a tender document has a page**, because
-- only a tender document is a parsed PDF. A DUME is XML and a notice is JSON. Stating it
-- that way means the next structured source is a change to the `in (...)` list and not
-- another exception to a rule that has stopped describing itself.
--
-- Idempotent, like every migration here: `make migrate` re-runs the whole directory.

begin;

alter table requirements drop constraint if exists requirements_source_check;
alter table requirements add constraint requirements_source_check check (source in (
    'tender_document', 'espd_request', 'notice'
));

alter table requirements drop constraint if exists requirements_page_matches_source_check;
alter table requirements add constraint requirements_page_matches_source_check check (
    (page is null) = (source in ('espd_request', 'notice'))
);

commit;
