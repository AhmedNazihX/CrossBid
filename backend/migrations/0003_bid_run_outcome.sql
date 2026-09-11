-- 0003_bid_run_outcome — what a bidder sees when a run stops short of a matrix.
--
-- Story S3.1.1. `GET /bids/{id}` is read from this row and never from a checkpoint, so two
-- things the poller must show had nowhere to live in 0001:
--
--   * `failure_reason` — a `failed` bid with no reason is a dead end on the dashboard. The
--     text names the stage and the exception *type* only; the traceback is in the API log
--     and the exception's message is deliberately not stored, because a message built from
--     model output carries document-derived text (ADR-0008).
--   * `problems` — what parsing and extraction could not do (`ExtractionProblem` rows:
--     unread pages, unparseable files, rows without a verbatim quote). Written after every
--     node, so a reviewer sees them the moment the bid parks at `awaiting_review`. Kept as
--     one jsonb list rather than a table: it is a projection of the graph state, read
--     whole and never queried by field.
--
-- Additive only; 0001 is immutable once applied (ADR-0009).

begin;

alter table bids add column if not exists failure_reason text;
alter table bids add column if not exists problems jsonb not null default '[]'::jsonb;

commit;
