-- 0009 — the agent's own verdict on a row, kept when a reviewer overrules it (H24).
--
-- `apply_review` writes the reviewer's status into `matrix_rows.status`, because that is what
-- the scorer re-runs on and what the dashboard counts. The agent's original therefore existed
-- nowhere a request could reach: only inside the LangGraph checkpoint. So the workspace could
-- say a row was overridden and never say what it was overridden *from*, and story S4.5.2's
-- criterion that "the agent's original stays visible" was unmeetable for a stored review — it
-- held only for an edit the reviewer had not submitted yet.
--
-- Nullable, and left null for rows written before this migration. A backfill would have to
-- invent the answer for every already-reviewed row: for a confirmed row `status` is still the
-- agent's and copying it would be right, but for an overridden one it is the reviewer's and
-- copying it would assert the agent agreed when the record says the opposite. Null reads as
-- "not recorded", which is true, and the UI says nothing rather than something false.

begin;

alter table matrix_rows add column if not exists agent_status text;

alter table matrix_rows drop constraint if exists matrix_rows_agent_status_check;
alter table matrix_rows add constraint matrix_rows_agent_status_check check (
    agent_status is null or agent_status in (
        'supported', 'partially_supported', 'unsupported', 'not_applicable'
    )
);

-- A confirmed row is one the agent and the reviewer agree on, so its `status` is still the
-- agent's own and copying it asserts nothing new. Overridden rows are deliberately left null.
update matrix_rows
set agent_status = status
where agent_status is null and reviewer_status in ('pending', 'confirmed');

commit;
