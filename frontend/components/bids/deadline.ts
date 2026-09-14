/**
 * The buyer's clock (story S4.4.1, the `Due` column of `Dashboard.dc.html`).
 *
 * Two questions are answered here and they are deliberately answered from different inputs.
 * *How long is left* is the distance between two instants, so it has no time zone at all and
 * is read from `deadline` alone. *When is it due* is a wall clock reading, and the only one
 * that means anything is the buyer's: a German bidder looking at a French tender must see
 * the hour the French buyer wrote, not the hour it happens to be in Berlin. An instant has
 * already lost that hour, which is why `BidSummary` carries
 * `deadline_utc_offset_minutes` beside it — and why nothing here ever formats in the
 * viewer's local zone.
 *
 * An offset is all the API has: neither a notice nor TED publishes an IANA zone, so a zone
 * name would be an inference that changes its answer twice a year. When even the offset is
 * missing the time is printed in UTC and labelled `UTC`, because a stated wrong hour is
 * worse than a plainly foreign one.
 *
 * No React here, so the rule lives in one place and stays testable on its own.
 */
import { plural } from '@/lib/format'

const MS_PER_MINUTE = 60_000
const MS_PER_HOUR = 3_600_000
const MS_PER_DAY = 86_400_000
const MINUTES_PER_HOUR = 60

/** Fewer days left than this and the row is calling for an answer now. */
const URGENT_DAYS = 3
/** Fewer days left than this and it is close enough to plan the week around. */
const SOON_DAYS = 14

/** What the screens print where there is no deadline and none may be invented. */
export const NO_DEADLINE = '—'

/**
 * Every formatter reads `timeZone: 'UTC'`, because the instant handed to it has already
 * been shifted by the buyer's offset — see `shiftToBuyerClock`.
 */
const BUYER_DAY_MONTH = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  timeZone: 'UTC',
})

const BUYER_DAY_MONTH_YEAR = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  timeZone: 'UTC',
})

const BUYER_HOUR_MINUTE = new Intl.DateTimeFormat('en-GB', {
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
  timeZone: 'UTC',
})

/** How close the deadline is, for a caller that wants to say so without saying it in colour. */
export type DeadlineUrgency = 'overdue' | 'urgent' | 'soon' | 'distant'

export interface DeadlineCountdown {
  /** Column-width form: "28 days", "5 hours", "Overdue". */
  readonly short: string
  /** Sentence form for a label or a tooltip: "28 days left", "Closed 3 days ago". */
  readonly long: string
  readonly urgency: DeadlineUrgency
}

/** An ISO instant, or `null` when the API sent none or sent something unreadable. */
function parseInstant(iso: string | null | undefined): Date | null {
  if (iso === null || iso === undefined || iso.length === 0) {
    return null
  }
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? null : date
}

/**
 * The instant moved forward by the buyer's offset, so that formatting it *as UTC* prints
 * the buyer's wall clock. Shifting and then reading in UTC is the whole trick: it is exact
 * for a fixed offset and, unlike a guessed zone name, it cannot drift with a DST rule.
 */
function shiftToBuyerClock(instant: Date, offsetMinutes: number): Date {
  return new Date(instant.getTime() + offsetMinutes * MS_PER_MINUTE)
}

/** "UTC+02:00", "UTC-03:30", or plain "UTC" for zero and for an offset the API never sent. */
export function formatUtcOffset(offsetMinutes: number | null | undefined): string {
  if (offsetMinutes === null || offsetMinutes === undefined || offsetMinutes === 0) {
    return 'UTC'
  }
  const sign = offsetMinutes < 0 ? '-' : '+'
  const total = Math.abs(offsetMinutes)
  const hours = String(Math.floor(total / MINUTES_PER_HOUR)).padStart(2, '0')
  const minutes = String(total % MINUTES_PER_HOUR).padStart(2, '0')
  return `UTC${sign}${hours}:${minutes}`
}

/** "9 Oct" on the buyer's clock; an em dash when there is no deadline. */
export function formatBuyerClockDate(
  iso: string | null | undefined,
  offsetMinutes: number | null | undefined
): string {
  const instant = parseInstant(iso)
  if (instant === null) {
    return NO_DEADLINE
  }
  return BUYER_DAY_MONTH.format(shiftToBuyerClock(instant, offsetMinutes ?? 0))
}

/** "16:00 (UTC+02:00)" — the hour the buyer wrote, with the clock it was written on. */
export function formatBuyerClockTime(
  iso: string | null | undefined,
  offsetMinutes: number | null | undefined
): string {
  const instant = parseInstant(iso)
  if (instant === null) {
    return NO_DEADLINE
  }
  const time = BUYER_HOUR_MINUTE.format(shiftToBuyerClock(instant, offsetMinutes ?? 0))
  return `${time} (${formatUtcOffset(offsetMinutes)})`
}

/** "9 Oct 2026, 16:00 (UTC+02:00)" — the whole reading, for a label or a summary line. */
export function formatBuyerClockDateTime(
  iso: string | null | undefined,
  offsetMinutes: number | null | undefined
): string {
  const instant = parseInstant(iso)
  if (instant === null) {
    return NO_DEADLINE
  }
  const shifted = shiftToBuyerClock(instant, offsetMinutes ?? 0)
  const time = BUYER_HOUR_MINUTE.format(shifted)
  return `${BUYER_DAY_MONTH_YEAR.format(shifted)}, ${time} (${formatUtcOffset(offsetMinutes)})`
}

/**
 * How long is left, from one instant to another — never a negative countdown: a deadline
 * that has passed says so in words, because "-3 days" reads as a number to act on and a
 * closed tender is not one.
 *
 * `null` when there is no deadline. A bid started before TED search lands (S1.2.1) has
 * none, and inventing one would be inventing the only fact the column exists to carry.
 */
export function countdownTo(
  iso: string | null | undefined,
  now: Date = new Date()
): DeadlineCountdown | null {
  const instant = parseInstant(iso)
  if (instant === null) {
    return null
  }

  const remainingMs = instant.getTime() - now.getTime()
  if (remainingMs <= 0) {
    const daysPast = Math.floor(-remainingMs / MS_PER_DAY)
    return {
      short: 'Overdue',
      long: daysPast === 0 ? 'Closed earlier today' : `Closed ${plural(daysPast, 'day')} ago`,
      urgency: 'overdue',
    }
  }
  if (remainingMs < MS_PER_HOUR) {
    return { short: 'Under an hour', long: 'Under an hour left', urgency: 'urgent' }
  }
  if (remainingMs < MS_PER_DAY) {
    const hours = plural(Math.floor(remainingMs / MS_PER_HOUR), 'hour')
    return { short: hours, long: `${hours} left`, urgency: 'urgent' }
  }

  const wholeDays = Math.floor(remainingMs / MS_PER_DAY)
  const days = plural(wholeDays, 'day')
  return {
    short: days,
    long: `${days} left`,
    urgency: wholeDays < URGENT_DAYS ? 'urgent' : wholeDays < SOON_DAYS ? 'soon' : 'distant',
  }
}

/**
 * Sort key for "soonest first": the deadline in milliseconds, and `Infinity` for a bid that
 * has none, so the bids nobody can act on a date for sit at the end rather than the top.
 */
export function deadlineSortKey(iso: string | null | undefined): number {
  return parseInstant(iso)?.getTime() ?? Number.POSITIVE_INFINITY
}
