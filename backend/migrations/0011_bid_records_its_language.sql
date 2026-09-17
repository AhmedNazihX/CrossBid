-- 0011 — a bid records the language its analysis was written in.
--
-- It never did. `bids` had no such column: `create_bid` took a `bidder_language` argument and
-- dropped it, and every read joined `companies` and returned `c.language as bidder_language`.
-- So "the language this analysis explains requirements in" was really "the language this
-- company prefers right now", and the two are the same only until somebody changes the
-- setting.
--
-- Reported 2026-09-18. A company analysed a tender with German as its explanation language,
-- then switched to English. Every requirement still held its German translation, the matrix
-- still held German rationales — and the workspace relabelled the column "explained in EN" and
-- offered an EN toggle over German text. Worse than the label: `routers/chat.py` passes the
-- same field into the chat preamble, so asking a question about that bid instructed the model
-- to answer in English about a German matrix, and a resumed run would have written English
-- rationales into it.
--
-- Nullable, and left null here rather than backfilled from `companies.language`. That column
-- is precisely the value that may have changed, so copying it would stamp the new language on
-- exactly the bids this exists to protect and make the mistake permanent and unrecoverable.
-- `scripts/backfill_bid_languages.py` fills it from each run's own LangGraph checkpoint, where
-- `BidState.bidder_language` is what the graph actually used — a record rather than a guess.
--
-- Until a bid is backfilled the read falls back to the company's language, which is today's
-- behaviour: no bid gets worse, and every bid the script reaches gets right.

begin;

alter table bids add column if not exists bidder_language text;

commit;
