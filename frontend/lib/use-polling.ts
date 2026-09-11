'use client'

import { useEffect, useRef, useState } from 'react'

import { ApiError } from './api-client'

/** The plan's poll cadence for anything the backend processes in the background. */
export const DEFAULT_POLL_INTERVAL_MS = 2_000

/**
 * Statuses that mean polling again would never help: the caller is not allowed to see the
 * resource, or it no longer exists. Everything else — a transport failure, a 5xx, a 429 —
 * is treated as transient and the next tick tries again.
 */
const STOP_ON_STATUSES: ReadonlySet<number> = new Set([401, 403, 404])

export interface UsePollingOptions<T> {
  /** What the caller already holds, e.g. the 202 body of the upload that created it. */
  readonly initialValue: T
  /** Fetches the current state. The signal aborts on unmount and once polling stops. */
  readonly fetchLatest: (signal: AbortSignal) => Promise<T>
  /** `true` once the value will not change any more; polling stops on the first such value. */
  readonly isSettled: (value: T) => boolean
  readonly intervalMs?: number
}

export interface PollingState<T> {
  /** The latest value seen — `initialValue` until the first successful poll. */
  readonly value: T
  /** The most recent poll failure, cleared by the next success. `undefined` when none. */
  readonly error: unknown
  /** `false` once the value settled or a poll was refused for good. */
  readonly isPolling: boolean
}

/**
 * Polls one resource on a fixed interval until it settles (story S4.2.2; S4.5.1 reuses it for
 * `GET /bids/{id}`).
 *
 * Why a timer chain rather than `setInterval`: a slow answer must never overlap the next
 * request, so the wait starts only after each response. Why `fetchLatest` goes through a
 * ref: callers pass a fresh closure every render, and restarting the loop on each one would
 * reset the interval. The loop itself restarts only when `isPolling` or the interval changes.
 */
export function usePolling<T>({
  initialValue,
  fetchLatest,
  isSettled,
  intervalMs = DEFAULT_POLL_INTERVAL_MS,
}: UsePollingOptions<T>): PollingState<T> {
  const [value, setValue] = useState<T>(initialValue)
  const [error, setError] = useState<unknown>(undefined)
  const [isRefused, setIsRefused] = useState(false)
  const fetchRef = useRef(fetchLatest)

  const isPolling = !isRefused && !isSettled(value)

  useEffect(() => {
    fetchRef.current = fetchLatest
  }, [fetchLatest])

  useEffect(() => {
    if (!isPolling) {
      return
    }
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout> | undefined

    const tick = async () => {
      try {
        const next = await fetchRef.current(controller.signal)
        if (controller.signal.aborted) {
          return
        }
        setValue(next)
        setError(undefined)
      } catch (cause) {
        if (controller.signal.aborted) {
          return
        }
        setError(cause)
        if (cause instanceof ApiError && STOP_ON_STATUSES.has(cause.status)) {
          setIsRefused(true)
          return
        }
      }
      timer = setTimeout(tick, intervalMs)
    }

    timer = setTimeout(tick, intervalMs)
    return () => {
      controller.abort()
      if (timer !== undefined) {
        clearTimeout(timer)
      }
    }
  }, [isPolling, intervalMs])

  return { value, error, isPolling }
}
