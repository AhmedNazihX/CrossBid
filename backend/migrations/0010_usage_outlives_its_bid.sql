-- 0010 — a bid's cost record outlives the bid.
--
-- Deleting a tender analysis is a bidder's decision about a tender, not about their accounts.
-- `llm_usage.bid_id` cascaded, so a delete took the spend with it: the operator console's
-- cost-per-bid totals would fall by whatever that bid had cost, and money genuinely spent on
-- OpenRouter would have no record on this side of it. An accounting row should outlive the
-- thing it describes.
--
-- `set null` rather than a second copy of the bid's name: the row keeps its company, its node,
-- its model and its cost, and loses only the bid it can no longer point at. That is the same
-- shape `usage.py` already handles — `bid_id` has always been nullable, because the injection
-- review and the startup slug probe spend money outside any bid — so nothing downstream learns
-- a new state. What changes is that "unattributed" now also means "the bid it paid for is
-- gone", which `fetch_usage_by_bid` groups away and `fetch_usage_by_node` still counts.
--
-- The company predicate is untouched and still `on delete cascade`: a company leaving takes
-- its accounts with it, which is a different question with a different answer.

begin;

alter table llm_usage drop constraint if exists llm_usage_bid_id_fkey;
alter table llm_usage add constraint llm_usage_bid_id_fkey
    foreign key (bid_id) references bids (id) on delete set null;

commit;
