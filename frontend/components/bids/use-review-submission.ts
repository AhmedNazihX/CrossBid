'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiError, describeApiError } from '@/lib/api-client'
import { getBid, submitReview, type BidResponse, type ReviewSubmission } from '@/lib/bids'

/**
 * The one-shot submit behind `Verdict.dc.html`'s Confirm verdict button (story S4.5.3).
 *
 * A review is the safety boundary of the whole product, so it must happen exactly once. Two
 * things could send it twice: a second click while the first call is in flight, and a retry
 * after an answer the screen mistook for a failure. The first is stopped by a ref rather
 * than by state alone, because a click handler reads the state of the render it was created
 * in; the second is why 409 is a phase of its own and not an error string — the API answers
 * it when the bid is no longer parked, and pressing Confirm again can only produce another
 * 409.
 *
 * Nothing aborts the call. An `AbortSignal` here would cancel a write the server may already
 * be applying, which is the one outcome worse than waiting; if the component goes away the
 * answer is dropped instead.
 */
export type ReviewState =
  /** Nothing sent yet, or a failure the reviewer can act on and send again. */
  | { readonly phase: 'editing'; readonly error: string | undefined }
  | { readonly phase: 'submitting' }
  /** The review landed. `bid` is the bid as the review left it. */
  | { readonly phase: 'reviewed'; readonly bid: BidResponse }
  /**
   * 409: something got there first. `bid` is the bid re-read afterwards, so the screen can
   * show what is actually true; `undefined` when that read failed too.
   */
  | { readonly phase: 'conflict'; readonly bid: BidResponse | undefined }

export interface ReviewSubmissionHandle {
  readonly state: ReviewState
  /** True while the call is in flight or after it has settled — the button's `disabled`. */
  readonly isLocked: boolean
  readonly submit: (body: ReviewSubmission) => Promise<void>
}

const CONFLICT_STATUS = 409

export function useReviewSubmission(
  bidId: string,
  onReviewed: (bid: BidResponse) => void
): ReviewSubmissionHandle {
  const [state, setState] = useState<ReviewState>({ phase: 'editing', error: undefined })
  const isSendingRef = useRef(false)
  const isMountedRef = useRef(true)

  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
    }
  }, [])

  const submit = useCallback(
    async (body: ReviewSubmission): Promise<void> => {
      if (isSendingRef.current) {
        return
      }
      isSendingRef.current = true
      setState({ phase: 'submitting' })
      try {
        const reviewed = await submitReview(bidId, body)
        if (!isMountedRef.current) {
          return
        }
        setState({ phase: 'reviewed', bid: reviewed })
        onReviewed(reviewed)
      } catch (cause) {
        if (cause instanceof ApiError && cause.status === CONFLICT_STATUS) {
          const current = await readCurrentBid(bidId)
          if (!isMountedRef.current) {
            return
          }
          setState({ phase: 'conflict', bid: current })
          if (current !== undefined) {
            onReviewed(current)
          }
          return
        }
        if (isMountedRef.current) {
          setState({ phase: 'editing', error: describeApiError(cause) })
        }
      } finally {
        isSendingRef.current = false
      }
    },
    [bidId, onReviewed]
  )

  return { state, isLocked: state.phase !== 'editing', submit }
}

/**
 * The bid as it stands now, or `undefined` when even that could not be read. Deliberately
 * swallows its error: this runs while a 409 is already being reported, and a second failure
 * must not replace the sentence that explains the first.
 */
async function readCurrentBid(bidId: string): Promise<BidResponse | undefined> {
  try {
    return await getBid(bidId)
  } catch {
    return undefined
  }
}
