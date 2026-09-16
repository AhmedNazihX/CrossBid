/**
 * `usePolling` — the 2 s loop every background job on the screen depends on (S4.2.2, S4.5.1).
 *
 * Why this hook can be quietly wrong: a poll that never stops looks exactly like one that
 * works. The page shows the right value either way; the difference is a request every two
 * seconds for as long as the tab is open, or a 404 hammered for ever after somebody deleted
 * the bid, or a timer that outlives its component and sets state on nothing. None of that
 * is visible in a screenshot. So each test here counts calls against a fake clock: how many
 * fetches happened by when, and — the harder assertion — how many did *not*.
 *
 * `fetchLatest` is a scripted function rather than a network stub, because the hook's
 * contract is about *when it calls*, not what HTTP looks like. The only production type it
 * needs is `ApiError`, whose `status` decides whether a failure is worth retrying.
 */
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { ApiError } from './api-client'
import { DEFAULT_POLL_INTERVAL_MS, usePolling } from './use-polling'

interface Job {
  readonly status: 'running' | 'done'
}

const RUNNING: Job = { status: 'running' }
const DONE: Job = { status: 'done' }
const isDone = (job: Job): boolean => job.status === 'done'

function apiError(status: number): ApiError {
  return new ApiError({
    status,
    statusText: 'answer from the API',
    method: 'GET',
    url: 'http://localhost:8000/bids/one',
    body: { detail: `HTTP ${status}` },
  })
}

/** Advance the fake clock inside React's `act`, so every state update it causes is flushed. */
async function elapse(ms: number): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('usePolling', () => {
  test('does not fetch until the first interval has elapsed', async () => {
    const fetchLatest = vi
      .fn<(signal: AbortSignal) => Promise<Job>>()
      .mockResolvedValue(RUNNING)
    renderHook(() => usePolling({ initialValue: RUNNING, fetchLatest, isSettled: isDone }))

    await elapse(DEFAULT_POLL_INTERVAL_MS - 1)
    expect(fetchLatest).not.toHaveBeenCalled()

    await elapse(1)
    expect(fetchLatest).toHaveBeenCalledTimes(1)
  })

  test('never fetches when the value it was handed is already settled', async () => {
    const fetchLatest = vi.fn<(signal: AbortSignal) => Promise<Job>>().mockResolvedValue(DONE)
    const { result } = renderHook(() =>
      usePolling({ initialValue: DONE, fetchLatest, isSettled: isDone })
    )

    await elapse(5 * DEFAULT_POLL_INTERVAL_MS)

    expect(fetchLatest).not.toHaveBeenCalled()
    expect(result.current.isPolling).toBe(false)
  })

  test('keeps polling on the interval while the value is unsettled', async () => {
    const fetchLatest = vi
      .fn<(signal: AbortSignal) => Promise<Job>>()
      .mockResolvedValue(RUNNING)
    renderHook(() =>
      usePolling({ initialValue: RUNNING, fetchLatest, isSettled: isDone, intervalMs: 500 })
    )

    await elapse(500 * 3)

    expect(fetchLatest).toHaveBeenCalledTimes(3)
  })

  test('stops on the first settled value and makes no further request', async () => {
    const fetchLatest = vi
      .fn<(signal: AbortSignal) => Promise<Job>>()
      .mockResolvedValueOnce(RUNNING)
      .mockResolvedValue(DONE)
    const { result } = renderHook(() =>
      usePolling({ initialValue: RUNNING, fetchLatest, isSettled: isDone, intervalMs: 100 })
    )

    await elapse(200)
    expect(result.current.value).toEqual(DONE)
    expect(result.current.isPolling).toBe(false)

    await elapse(10 * 100)
    expect(fetchLatest).toHaveBeenCalledTimes(2)
  })

  test('waits for the answer before starting the next interval, so slow replies never overlap', async () => {
    // Each fetch takes 300 ms against a 100 ms interval. `setInterval` would fire at 100,
    // 200, 300 and pile up in-flight requests; the timer chain fires at 100, then 500.
    const fetchLatest = vi.fn<(signal: AbortSignal) => Promise<Job>>(
      () => new Promise<Job>((resolve) => setTimeout(() => resolve(RUNNING), 300))
    )
    renderHook(() =>
      usePolling({ initialValue: RUNNING, fetchLatest, isSettled: isDone, intervalMs: 100 })
    )

    await elapse(100)
    expect(fetchLatest).toHaveBeenCalledTimes(1)
    await elapse(399)
    expect(fetchLatest).toHaveBeenCalledTimes(1)
    await elapse(1)
    expect(fetchLatest).toHaveBeenCalledTimes(2)
  })

  test('treats a 5xx as transient: the error is exposed and the next tick still fires', async () => {
    const fetchLatest = vi
      .fn<(signal: AbortSignal) => Promise<Job>>()
      .mockRejectedValueOnce(apiError(503))
      .mockResolvedValue(RUNNING)
    const { result } = renderHook(() =>
      usePolling({ initialValue: RUNNING, fetchLatest, isSettled: isDone, intervalMs: 100 })
    )

    await elapse(100)
    expect(result.current.error).toBeInstanceOf(ApiError)
    expect(result.current.isPolling).toBe(true)

    await elapse(100)
    expect(fetchLatest).toHaveBeenCalledTimes(2)
    expect(result.current.error).toBeUndefined()
  })

  test('treats a thrown non-ApiError as transient too', async () => {
    const fetchLatest = vi
      .fn<(signal: AbortSignal) => Promise<Job>>()
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValue(RUNNING)
    const { result } = renderHook(() =>
      usePolling({ initialValue: RUNNING, fetchLatest, isSettled: isDone, intervalMs: 100 })
    )

    await elapse(200)

    expect(fetchLatest).toHaveBeenCalledTimes(2)
    expect(result.current.isPolling).toBe(true)
  })

  test.each([401, 403, 404])(
    'stops for good on a %d rather than hammering a resource it will never see',
    async (status) => {
      const fetchLatest = vi
        .fn<(signal: AbortSignal) => Promise<Job>>()
        .mockRejectedValue(apiError(status))
      const { result } = renderHook(() =>
        usePolling({ initialValue: RUNNING, fetchLatest, isSettled: isDone, intervalMs: 100 })
      )

      await elapse(100)
      expect(result.current.isPolling).toBe(false)
      expect(result.current.error).toBeInstanceOf(ApiError)

      await elapse(10 * 100)
      expect(fetchLatest).toHaveBeenCalledTimes(1)
      // The value the caller already held is kept; a refusal does not blank the screen.
      expect(result.current.value).toEqual(RUNNING)
    }
  )

  test('a 429 is not a stop: the rate limit lifts, so the next tick tries again', async () => {
    const fetchLatest = vi
      .fn<(signal: AbortSignal) => Promise<Job>>()
      .mockRejectedValueOnce(apiError(429))
      .mockResolvedValue(RUNNING)
    renderHook(() =>
      usePolling({ initialValue: RUNNING, fetchLatest, isSettled: isDone, intervalMs: 100 })
    )

    await elapse(200)

    expect(fetchLatest).toHaveBeenCalledTimes(2)
  })

  test('unmounting before the first tick leaves no timer behind', async () => {
    const fetchLatest = vi
      .fn<(signal: AbortSignal) => Promise<Job>>()
      .mockResolvedValue(RUNNING)
    const { unmount } = renderHook(() =>
      usePolling({ initialValue: RUNNING, fetchLatest, isSettled: isDone, intervalMs: 100 })
    )

    unmount()
    await elapse(10 * 100)

    expect(fetchLatest).not.toHaveBeenCalled()
    expect(vi.getTimerCount()).toBe(0)
  })

  test('unmounting mid-flight aborts the request and schedules nothing more', async () => {
    let seenSignal: AbortSignal | undefined
    const fetchLatest = vi.fn<(signal: AbortSignal) => Promise<Job>>(
      (signal) =>
        new Promise<Job>((resolve) => {
          seenSignal = signal
          setTimeout(() => resolve(RUNNING), 300)
        })
    )
    const { unmount } = renderHook(() =>
      usePolling({ initialValue: RUNNING, fetchLatest, isSettled: isDone, intervalMs: 100 })
    )

    await elapse(100)
    expect(seenSignal?.aborted).toBe(false)
    unmount()
    expect(seenSignal?.aborted).toBe(true)

    // The in-flight promise resolves, is ignored, and must not chain another tick.
    await elapse(300 + 10 * 100)
    expect(fetchLatest).toHaveBeenCalledTimes(1)
  })

  test('uses the newest fetchLatest closure without resetting the interval', async () => {
    const first = vi.fn<(signal: AbortSignal) => Promise<Job>>().mockResolvedValue(RUNNING)
    const second = vi.fn<(signal: AbortSignal) => Promise<Job>>().mockResolvedValue(RUNNING)
    const { rerender } = renderHook(
      ({ fetchLatest }: { fetchLatest: (signal: AbortSignal) => Promise<Job> }) =>
        usePolling({ initialValue: RUNNING, fetchLatest, isSettled: isDone, intervalMs: 100 }),
      { initialProps: { fetchLatest: first } }
    )

    await elapse(60)
    rerender({ fetchLatest: second })
    await elapse(40)

    // Still fires at t=100 — a fresh closure every render must not push the tick back.
    expect(first).not.toHaveBeenCalled()
    expect(second).toHaveBeenCalledTimes(1)
  })
})
