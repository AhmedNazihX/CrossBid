-- 0002_documents_status — the upload state machine on `documents`.
--
-- Story S2.2.3. Applied by `uv run python scripts/migrate.py` (or `make migrate`).
--
-- 0001 gave `documents` its identity, its Storage key and its page bookkeeping, but nothing
-- that says *how far* an upload has got. The story is exactly that: a bidder polls a document
-- and watches `uploaded → parsed → embedded → ready`, or reads why it `failed`. Three columns:
--
--   * `status` — text plus a check constraint, like every enum column in 0001. The values must
--     stay identical to `DocumentStatus` in `crossbid/readmodel/documents.py`;
--     `tests/unit/test_documents_readmodel.py` asserts that parity (0001's guard only scans its
--     own file).
--   * `failure_reason` — a sentence the bidder can act on, never a stack trace. The invariant
--     "failed if and only if there is a reason" is enforced here as well as in the Pydantic
--     record, because a direct SQL write bypasses Pydantic (same reasoning as
--     `matrix_rows_met_needs_evidence_check`).
--   * `updated_at` — so a poller can tell a stuck document from a slow one.
--
-- `add constraint` has no `if not exists`, so each constraint is dropped and re-added, which
-- keeps the file replayable against a database that already has the objects.

begin;

alter table documents add column if not exists status text not null default 'uploaded';
alter table documents add column if not exists failure_reason text;
alter table documents add column if not exists updated_at timestamptz not null default now();

alter table documents drop constraint if exists documents_status_check;
alter table documents add constraint documents_status_check check (status in (
    'uploaded', 'parsed', 'embedded', 'ready', 'failed'
));

alter table documents drop constraint if exists documents_failed_needs_reason_check;
alter table documents add constraint documents_failed_needs_reason_check check (
    (status = 'failed') = (failure_reason is not null)
);

commit;
