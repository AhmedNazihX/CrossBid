'use client'

import { useCallback, useEffect, useState } from 'react'

import { ApiError } from './api-client'
import { formatTime } from './format'

/**
 * The one treatment a 429 gets on every screen that can be refused for its hour's
 * allowance — a question asked, a file uploaded, a bid started (ADR-0058; audit finding
 * M12).
 *
 * **A 429 is a wait, not an error.** The API's `Retry-After` names the second the next call
 * will be accepted; when the browser can read it (`ApiError.retryAfterSeconds`) this hook
 * holds that instant so the form can disable its control until then and say the clock time.
 * When it cannot — a proxy stripped the header — `noteRefusal` returns `false` and the
 * caller shows the API's own `detail`, which carries the same number of seconds in prose.
 * Never "something went wrong".
 *
 * **The limit lifts itself.** A timer clears `blockedUntil` at the second the API named, so
 * the control re-enables without a reload and without a probe that would itself be refused.
 * This used to live inside `useBidChat` alone, which is how the upload form and the start
 * form came to show a sentence with a stale number in it under a button that still worked.
 */
export interface RateLimitController {
  /** Epoch milliseconds at which the API will take the call again; `undefined` when it will now. */
  readonly blockedUntil: number | undefined
  /** `blockedUntil` is set and has not passed — the form's "do not send another". */
  readonly isBlocked: boolean
  /**
   * Records a refusal. `true` when it was a 429 whose wait the browser could read — the hook
   * now owns the message, and the caller should not also show the stale `detail`. `false`
   * for anything else, the header-less 429 included: the caller shows the error as usual.
   */
  noteRefusal(cause: unknown): boolean
}

const RATE_LIMITED_STATUS = 429
const MILLISECONDS_PER_SECOND = 1000

export function useRateLimit(): RateLimitController {
  const [blockedUntil, setBlockedUntil] = useState<number | undefined>(undefined)

  useEffect(() => {
    if (blockedUntil === undefined) {
      return
    }
    const wait = blockedUntil - Date.now()
    if (wait <= 0) {
      setBlockedUntil(undefined)
      return
    }
    const timer = setTimeout(() => setBlockedUntil(undefined), wait)
    return () => clearTimeout(timer)
  }, [blockedUntil])

  const noteRefusal = useCallback((cause: unknown): boolean => {
    if (!(cause instanceof ApiError) || cause.status !== RATE_LIMITED_STATUS) {
      return false
    }
    const seconds = cause.retryAfterSeconds
    if (seconds === undefined) {
      return false
    }
    setBlockedUntil(Date.now() + seconds * MILLISECONDS_PER_SECOND)
    return true
  }, [])

  return { blockedUntil, isBlocked: blockedUntil !== undefined, noteRefusal }
}

/**
 * "Try again at 14:32." — the clock time the wait ends, on the bidder's own clock. A
 * clock time rather than the API's "in 120 seconds" because the sentence stays on the screen
 * while the seconds run down, and a number that was true when it appeared is not true a
 * minute later.
 */
export function retryAt(blockedUntil: number): string {
  return `Try again at ${formatTime(new Date(blockedUntil))}.`
}
