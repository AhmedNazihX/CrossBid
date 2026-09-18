import { describe, expect, test } from 'vitest'

import { formatElapsed } from './run-elapsed'

const START = '2026-09-18T01:00:00Z'

function at(seconds: number): Date {
  return new Date(Date.parse(START) + seconds * 1_000)
}

describe('formatElapsed', () => {
  test('returns null when the bid carries no start instant', () => {
    expect(formatElapsed(null, at(10))).toBeNull()
  })

  test('returns null when the start instant cannot be parsed', () => {
    expect(formatElapsed('not a date', at(10))).toBeNull()
  })

  test('counts whole seconds under a minute', () => {
    expect(formatElapsed(START, at(48))).toBe('48 s')
  })

  test('shows minutes and seconds between one minute and one hour', () => {
    expect(formatElapsed(START, at(3 * 60 + 12))).toBe('3 min 12 s')
  })

  test('pads the seconds so the text does not jump width', () => {
    expect(formatElapsed(START, at(3 * 60 + 5))).toBe('3 min 05 s')
  })

  test('drops to hours and minutes past an hour', () => {
    expect(formatElapsed(START, at(3600 + 4 * 60 + 30))).toBe('1 hr 04 min')
  })

  test('never counts backwards when the clock is behind the start instant', () => {
    expect(formatElapsed(START, at(-5))).toBe('0 s')
  })
})
