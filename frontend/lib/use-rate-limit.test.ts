/**
 * `useRateLimit` — the wait a 429 imposes, and the second it lifts (ADR-0058, audit M12).
 *
 * Why this hook can be quietly wrong: a block that never lifts looks exactly like a working
 * one for the first two minutes. The button is disabled, the sentence names a time, and only
 * a bidder who waits past it finds the form still dead — a reload fixes it, so nobody files
 * the bug. The other silent failure is the reverse: a 429 with no readable header recorded as
 * a block of `NaN` milliseconds, which `setTimeout` treats as zero and clears at once, so the
 * form flickers and the API's sentence is never shown. So each test here runs a fake clock
 * to the exact second and asserts the state on both sides of it.
 */
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { ApiError } from './api-client'
import { formatTime } from './format'
import { retryAt, useRateLimit } from './use-rate-limit'

const NOW = new Date('2026-10-07T14:30:00Z')
const SECOND = 1000

function refusal(status: number, retryAfter?: string): ApiError {
  return new ApiError({
    status,
    statusText: 'answer from the API',
    method: 'POST',
    url: 'http://localhost:8000/documents',
    body: { detail: `HTTP ${status}` },
    headers:
      retryAfter === undefined ? new Headers() : new Headers({ 'Retry-After': retryAfter }),
  })
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(NOW)
})

afterEach(() => {
  vi.useRealTimers()
})

describe('useRateLimit', () => {
  test('starts unblocked', () => {
    const { result } = renderHook(() => useRateLimit())

    expect(result.current.isBlocked).toBe(false)
    expect(result.current.blockedUntil).toBeUndefined()
  })

  test('a 429 with Retry-After blocks until exactly that second, then lifts on its own', () => {
    const { result } = renderHook(() => useRateLimit())

    let owned = false
    act(() => {
      owned = result.current.noteRefusal(refusal(429, '120'))
    })

    expect(owned).toBe(true)
    expect(result.current.isBlocked).toBe(true)
    expect(result.current.blockedUntil).toBe(NOW.getTime() + 120 * SECOND)

    act(() => {
      vi.advanceTimersByTime(119 * SECOND)
    })
    expect(result.current.isBlocked).toBe(true)

    act(() => {
      vi.advanceTimersByTime(1 * SECOND)
    })
    expect(result.current.isBlocked).toBe(false)
    expect(result.current.blockedUntil).toBeUndefined()
  })

  test('a 429 with no readable header is not owned, so the caller shows the API’s sentence', () => {
    const { result } = renderHook(() => useRateLimit())

    let owned = true
    act(() => {
      owned = result.current.noteRefusal(refusal(429))
    })

    expect(owned).toBe(false)
    expect(result.current.isBlocked).toBe(false)
  })

  test('any other status, or a non-API error, is not a wait', () => {
    const { result } = renderHook(() => useRateLimit())

    let owned = true
    act(() => {
      owned = result.current.noteRefusal(refusal(500, '30'))
    })
    expect(owned).toBe(false)

    act(() => {
      owned = result.current.noteRefusal(new Error('offline'))
    })
    expect(owned).toBe(false)
    expect(result.current.isBlocked).toBe(false)
  })
})

describe('retryAt', () => {
  test('names the clock time the wait ends', () => {
    const until = NOW.getTime() + 120 * SECOND

    expect(retryAt(until)).toBe(`Try again at ${formatTime(new Date(until))}.`)
  })
})
