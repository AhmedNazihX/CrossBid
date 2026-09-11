-- 0004_design_system_vocabulary — the matrix and verdict words of the CrossBid design system.
--
-- ADR-0013 (2026-09-11). The design system fixes the product's vocabulary: rows are
-- `supported` / `partially_supported` / `unsupported` / `not_applicable`, and verdicts are
-- `go` / `conditional` / `no_go` / `insufficient_evidence`. 0001 used `met` / `unmet` /
-- `unclear` and `go_with_open_items`, and 0001 is immutable once applied (ADR-0009), so the
-- check constraints are dropped and re-added here with the new lists. The Pydantic enums
-- `RowStatus` and `Decision` carry the same lists and `tests/unit/test_migrations.py`
-- asserts the parity against the *last* definition of each constraint.
--
-- Data first, then constraints: the `update`s are no-ops on the empty tables of 2026-09-11
-- but make the file honest against any database that already holds rows.

begin;

update matrix_rows set status = 'supported'           where status = 'met';
update matrix_rows set status = 'unsupported'         where status = 'unmet';
update matrix_rows set status = 'partially_supported' where status = 'unclear';
update reviews     set decision = 'conditional'       where decision = 'go_with_open_items';

alter table matrix_rows drop constraint if exists matrix_rows_status_check;
alter table matrix_rows add constraint matrix_rows_status_check check (status in (
    'supported', 'partially_supported', 'unsupported', 'not_applicable'
));

-- "Every cell carries a citation or is marked partially supported": the invariant keeps its
-- force under the new word. Renamed so the name says what it guards.
alter table matrix_rows drop constraint if exists matrix_rows_met_needs_evidence_check;
alter table matrix_rows drop constraint if exists matrix_rows_supported_needs_evidence_check;
alter table matrix_rows add constraint matrix_rows_supported_needs_evidence_check check (
    status <> 'supported'
    or jsonb_array_length(evidence) > 0
    or cardinality(attached_doc_ids) > 0
);

alter table reviews drop constraint if exists reviews_decision_check;
alter table reviews add constraint reviews_decision_check check (decision in (
    'go', 'conditional', 'no_go', 'insufficient_evidence'
));

commit;
