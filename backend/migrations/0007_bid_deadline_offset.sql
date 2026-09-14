-- 0007_bid_deadline_offset — the buyer's own clock, which a `timestamptz` does not keep.
--
-- Story S4.4.1, pulled into Increment 3. Its criterion is "a deadline countdown **in the
-- buyer's time zone**", and 0001's `bids.deadline timestamptz` cannot satisfy it alone:
-- Postgres stores the *instant* and hands it back in whatever zone the session asks for, so
-- the wall-clock time the buyer actually wrote is lost on the way in.
--
-- What is recoverable is the **offset**, and only the offset. A published notice states
-- `09.10.2026 16:00 (UTC+02:00)`; TED's `deadline-receipt-tender-date-lot` likewise carries an
-- ISO timestamp with an offset (S1.2.1). Neither names an IANA zone, so storing `Europe/Paris`
-- would be an inference, and one that changes the answer twice a year. The offset is what the
-- buyer published, so the offset is what is kept.
--
-- The countdown itself needs none of this — a difference between two instants has no zone.
-- This column exists so the deadline can be *printed* the way the buyer wrote it.
--
-- Nullable because it is only ever as available as the deadline it belongs to, and a bid
-- started before S1.2.1 may have neither.
--
-- Additive only; 0001 is immutable once applied (ADR-0009).

begin;

alter table bids add column if not exists deadline_utc_offset_minutes smallint;

-- The real range is about -12:00 to +14:00; the constraint is deliberately a little wider
-- than any zone in use, because its job is to refuse a value that is plainly not an offset
-- (a year, a millisecond count) rather than to adjudicate geography.
alter table bids drop constraint if exists bids_deadline_offset_range_check;
alter table bids add constraint bids_deadline_offset_range_check check (
    deadline_utc_offset_minutes is null
    or deadline_utc_offset_minutes between -900 and 900
);

-- An offset without a deadline describes nothing, and would print as a zone on a bid that
-- has no date. The pair travels together or not at all.
alter table bids drop constraint if exists bids_deadline_offset_needs_a_deadline_check;
alter table bids add constraint bids_deadline_offset_needs_a_deadline_check check (
    deadline_utc_offset_minutes is null or deadline is not null
);

commit;
