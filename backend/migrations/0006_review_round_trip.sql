-- 0006_review_round_trip — what the human decided, and who (or whether) we may say decided it.
--
-- Story S3.4.2. Two columns 0001 could not have got right, because both turn on a
-- distinction the review step only makes once it exists.
--
--   * `bids.decision` — the *reviewer's* final call. It is deliberately not the same fact as
--     `bids.verdict`, which 0001 already declared and S3.4.1 writes: the verdict is what the
--     rules say about the matrix, and after a review it is what the rules say about the
--     matrix *as the reviewer left it*. The reviewer may then decide otherwise, and the whole
--     point of the human interrupt is that the two can differ. `BidSummary.decision` reads
--     this column and falls back to the verdict's while a bid is still in flight, so the
--     dashboard shows the agent's advisory answer until a person has given a real one.
--
--   * `reviews.reviewer_id` becomes nullable. `auth.py` says it plainly: under `AUTH_MODE=dev`
--     a header is not a credential. There is therefore no verified identity to record, and the
--     obvious substitute — the company's `owner_user_id` — would assert that a particular
--     person reviewed a bid when the system cannot know it. An audit trail that records an
--     unverified identity is worse than one that records none, so the column stays empty until
--     magic-link sign-in (S0.3.1) can fill it truthfully.
--
-- Additive only; 0001 is immutable once applied (ADR-0009).

begin;

alter table bids add column if not exists decision text;

-- Mirrors `models.verdict.Decision`, and `tests/unit/test_migrations.py` asserts the parity
-- against the last definition of the constraint, as it does for every other enum column.
alter table bids drop constraint if exists bids_decision_check;
alter table bids add constraint bids_decision_check check (decision is null or decision in (
    'go', 'conditional', 'no_go', 'insufficient_evidence'
));

-- "Which bids has a human finished with?" joins the dashboard's existing status filter.
create index if not exists bids_company_id_decision_idx on bids (company_id, decision);

alter table reviews alter column reviewer_id drop not null;

commit;
