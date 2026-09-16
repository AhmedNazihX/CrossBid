/**
 * `deadline.ts` — the buyer's clock and the countdown beside it (story S4.4.1).
 *
 * Why this module can be quietly wrong: every function in it returns a plausible string for
 * every input. An offset applied in the wrong direction prints "14:00" where the buyer wrote
 * "18:00"; a countdown that rounds instead of floors says "3 days" with 2 days 23 hours
 * left; a date formatted in the viewer's zone moves the deadline to yesterday west of
 * Greenwich. Nothing throws, nothing looks broken, and the bidder plans around the wrong
 * number. So these tests pin the arithmetic to hand-computed instants and never let the
 * machine's own time zone or clock into the answer: `now` is injected, and every expected
 * wall-clock reading is worked out from a UTC instant plus a stated offset.
 *
 * October is used throughout because `en-GB` abbreviates September as "Sept", which is
 * correct but a distraction from what is being asserted.
 */
import { describe, expect, test } from 'vitest'

import {
  NO_DEADLINE,
  countdownTo,
  deadlineSortKey,
  formatBuyerClockDate,
  formatBuyerClockDateTime,
  formatBuyerClockTime,
  formatUtcOffset,
} from './deadline'

const MINUTE = 60_000
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR

/** 16:00 UTC on 7 October 2026, which is 18:00 in Paris and Berlin that day. */
const AFTERNOON_UTC = '2026-10-07T16:00:00Z'
const PARIS_OFFSET_MINUTES = 120

const at = (iso: string): Date => new Date(iso)

describe('formatUtcOffset', () => {
  test.each([
    [0, 'UTC'],
    [null, 'UTC'],
    [undefined, 'UTC'],
    [60, 'UTC+01:00'],
    [120, 'UTC+02:00'],
    [-180, 'UTC-03:00'],
    [-210, 'UTC-03:30'],
    [345, 'UTC+05:45'],
  ])('%s minutes prints as %s', (offsetMinutes, expected) => {
    expect(formatUtcOffset(offsetMinutes)).toBe(expected)
  })
})

describe('formatBuyerClockTime', () => {
  test('prints the hour the buyer wrote, not the UTC hour the API stores', () => {
    expect(formatBuyerClockTime(AFTERNOON_UTC, PARIS_OFFSET_MINUTES)).toBe('18:00 (UTC+02:00)')
  })

  test('a positive offset late in the day rolls the clock past midnight', () => {
    // 22:30 UTC is 00:30 the next day in Paris — the minutes survive, the hour wraps.
    expect(formatBuyerClockTime('2026-10-07T22:30:00Z', PARIS_OFFSET_MINUTES)).toBe(
      '00:30 (UTC+02:00)'
    )
  })

  test('a negative offset early in the day rolls the clock back before midnight', () => {
    expect(formatBuyerClockTime('2026-10-08T02:00:00Z', -180)).toBe('23:00 (UTC-03:00)')
  })

  test('a half-hour offset shifts the minutes as well as the hour', () => {
    expect(formatBuyerClockTime(AFTERNOON_UTC, -210)).toBe('12:30 (UTC-03:30)')
  })

  test('prints UTC and says so when the API sent no offset', () => {
    expect(formatBuyerClockTime(AFTERNOON_UTC, null)).toBe('16:00 (UTC)')
    expect(formatBuyerClockTime(AFTERNOON_UTC, undefined)).toBe('16:00 (UTC)')
  })

  test('is an em dash when there is no deadline', () => {
    expect(formatBuyerClockTime(null, PARIS_OFFSET_MINUTES)).toBe(NO_DEADLINE)
    expect(formatBuyerClockTime(undefined, PARIS_OFFSET_MINUTES)).toBe(NO_DEADLINE)
    expect(formatBuyerClockTime('', PARIS_OFFSET_MINUTES)).toBe(NO_DEADLINE)
  })

  test('is an em dash rather than "Invalid Date" for a timestamp it cannot read', () => {
    expect(formatBuyerClockTime('not a timestamp', PARIS_OFFSET_MINUTES)).toBe(NO_DEADLINE)
  })
})

describe('formatBuyerClockDate', () => {
  test('is the calendar day on the buyer clock, so a late-evening UTC instant is tomorrow', () => {
    expect(formatBuyerClockDate('2026-10-07T22:30:00Z', PARIS_OFFSET_MINUTES)).toBe('8 Oct')
  })

  test('a negative offset can move the same instant to the day before', () => {
    expect(formatBuyerClockDate('2026-10-08T02:00:00Z', -180)).toBe('7 Oct')
  })

  test('reads the date in UTC when no offset was sent', () => {
    expect(formatBuyerClockDate('2026-10-07T23:59:00Z', null)).toBe('7 Oct')
  })

  test('is an em dash when there is no deadline', () => {
    expect(formatBuyerClockDate(null, PARIS_OFFSET_MINUTES)).toBe(NO_DEADLINE)
  })
})

describe('formatBuyerClockDateTime', () => {
  test('joins the buyer-clock date, time and offset into one reading', () => {
    expect(formatBuyerClockDateTime(AFTERNOON_UTC, PARIS_OFFSET_MINUTES)).toBe(
      '7 Oct 2026, 18:00 (UTC+02:00)'
    )
  })

  test('shifts the date and the time together across midnight', () => {
    expect(formatBuyerClockDateTime('2026-12-31T23:30:00Z', 60)).toBe(
      '1 Jan 2027, 00:30 (UTC+01:00)'
    )
  })

  test('is an em dash when there is no deadline', () => {
    expect(formatBuyerClockDateTime(undefined, 0)).toBe(NO_DEADLINE)
  })
})

describe('countdownTo', () => {
  const now = at(AFTERNOON_UTC)
  const inMs = (ms: number): string => new Date(now.getTime() + ms).toISOString()

  test('is null when there is no deadline, so the column can stay honestly empty', () => {
    expect(countdownTo(null, now)).toBeNull()
    expect(countdownTo(undefined, now)).toBeNull()
    expect(countdownTo('', now)).toBeNull()
    expect(countdownTo('garbage', now)).toBeNull()
  })

  test('a deadline at this very instant is overdue, not "0 hours"', () => {
    expect(countdownTo(inMs(0), now)).toEqual({
      short: 'Overdue',
      long: 'Closed earlier today',
      urgency: 'overdue',
    })
  })

  test('a deadline earlier today is overdue and says so without a day count', () => {
    expect(countdownTo(inMs(-5 * HOUR), now)?.long).toBe('Closed earlier today')
  })

  test('days past are floored, and one day is singular', () => {
    expect(countdownTo(inMs(-(3 * DAY + 5 * HOUR)), now)?.long).toBe('Closed 3 days ago')
    expect(countdownTo(inMs(-(1 * DAY + 1 * MINUTE)), now)?.long).toBe('Closed 1 day ago')
  })

  test('under an hour left is said in words rather than as "0 hours"', () => {
    expect(countdownTo(inMs(59 * MINUTE), now)).toEqual({
      short: 'Under an hour',
      long: 'Under an hour left',
      urgency: 'urgent',
    })
  })

  test('exactly one hour left is "1 hour", singular and urgent', () => {
    expect(countdownTo(inMs(HOUR), now)).toEqual({
      short: '1 hour',
      long: '1 hour left',
      urgency: 'urgent',
    })
  })

  test('hours are floored: 23 hours 59 minutes is "23 hours", never "1 day"', () => {
    expect(countdownTo(inMs(DAY - MINUTE), now)?.short).toBe('23 hours')
  })

  test('exactly one day left is "1 day" and still urgent', () => {
    expect(countdownTo(inMs(DAY), now)).toEqual({
      short: '1 day',
      long: '1 day left',
      urgency: 'urgent',
    })
  })

  test('days are floored: 2 days 23 hours is "2 days", not "3 days"', () => {
    expect(countdownTo(inMs(2 * DAY + 23 * HOUR), now)?.short).toBe('2 days')
  })

  test.each([
    [2 * DAY + 23 * HOUR, 'urgent'],
    [3 * DAY, 'soon'],
    [13 * DAY + 23 * HOUR, 'soon'],
    [14 * DAY, 'distant'],
    [28 * DAY, 'distant'],
  ])('%d ms ahead has urgency %s', (ahead, urgency) => {
    expect(countdownTo(inMs(ahead), now)?.urgency).toBe(urgency)
  })

  test('a distant deadline reads as whole days in both forms', () => {
    expect(countdownTo(inMs(28 * DAY + 6 * HOUR), now)).toEqual({
      short: '28 days',
      long: '28 days left',
      urgency: 'distant',
    })
  })

  test('the countdown is a distance between instants and ignores the buyer offset entirely', () => {
    // Same instant written two ways; whoever's clock it is written on, it is 2 days away.
    expect(countdownTo('2026-10-09T16:00:00Z', now)).toEqual(
      countdownTo('2026-10-09T18:00:00+02:00', now)
    )
  })
})

describe('deadlineSortKey', () => {
  test('is the instant in milliseconds for a readable deadline', () => {
    expect(deadlineSortKey(AFTERNOON_UTC)).toBe(at(AFTERNOON_UTC).getTime())
  })

  test('sorts a bid with no deadline after every bid that has one', () => {
    const bids = [null, '2026-10-09T16:00:00Z', undefined, AFTERNOON_UTC, 'garbage']
    const sorted = [...bids].sort((a, b) => deadlineSortKey(a) - deadlineSortKey(b))
    expect(sorted.slice(0, 2)).toEqual([AFTERNOON_UTC, '2026-10-09T16:00:00Z'])
    expect(sorted.slice(2).every((iso) => deadlineSortKey(iso) === Infinity)).toBe(true)
  })
})
