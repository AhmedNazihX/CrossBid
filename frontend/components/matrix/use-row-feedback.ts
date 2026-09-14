'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

import { describeApiError } from '@/lib/api-client'
import {
  listFeedback,
  rateRow,
  type FeedbackRecord,
  type Rating,
  type FeedbackSubmission,
} from '@/lib/feedback'

/**
 * The bidder's ratings of one bid's answers, loaded once and sent as they are given
 * (story S4.6.3).
 *
 * One controller for the whole workspace rather than one fetch per row: thirty expanded
 * rows would otherwise be thirty requests for a thumb each. `GET /bids/{id}/feedback`
 * answers the latest rating of every target in one call, and every `POST` answers with the
 * row it wrote, so the map is kept current without re-reading the list.
 *
 * **A rating is sent the moment it is given, and a comment is a second sending of the same
 * thumb.** The story's criterion is that a thumbs rating is *stored*, so it must not wait
 * behind a Save the bidder may never press — which is the opposite of `useRowEdits`, where
 * holding the change until Confirm is the whole point because a review changes a verdict.
 * A rating changes nothing; it is only kept.
 *
 * **There is no unrating.** The table is an append-only log and has no delete route: a
 * bidder who changes their mind presses the other thumb, which appends the new answer, and
 * pressing the thumb already stored does nothing rather than filing the same answer twice.
 */
export interface RowFeedbackController {
  /** The thumb this row carries, or `undefined` when it has not been rated. */
  ratingOf(matrixRowId: string): Rating | undefined
  /** The comment stored with that thumb, if the bidder gave one. */
  commentOf(matrixRowId: string): string | undefined
  /** True while this row's rating is in flight, so its controls can say so. */
  isSending(matrixRowId: string): boolean
  /** Why this row's last rating did not land, or `undefined` when it did. */
  errorOf(matrixRowId: string): string | undefined
  /**
   * Files a rating for one row. Passing the thumb the row already carries with no new
   * comment is a no-op; everything else is sent.
   */
  rate(matrixRowId: string, rating: Rating, comment?: string): Promise<void>
}

/** The key a bid-level rating is held under; the API sends `matrix_row_id: null` for it. */
const BID_TARGET = ''

export function useRowFeedback(bidId: string): RowFeedbackController {
  const [stored, setStored] = useState<ReadonlyMap<string, FeedbackRecord>>(new Map())
  const [sending, setSending] = useState<ReadonlySet<string>>(new Set())
  const [failed, setFailed] = useState<ReadonlyMap<string, string>>(new Map())
  const isMountedRef = useRef(true)

  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    setStored(new Map())
    listFeedback(bidId, controller.signal)
      .then((records) => setStored(indexByTarget(records)))
      .catch(() => {
        // Deliberately not surfaced, and the one error in this file that is not. A failed
        // *read* costs the bidder nothing they can act on: the thumbs simply start empty,
        // rating still works, and a banner about ratings they may never have given would
        // be the loudest thing on a screen about a tender. A failed *write* is reported —
        // that one loses something they did.
      })
    return () => controller.abort()
  }, [bidId])

  const rate = useCallback(
    async (matrixRowId: string, rating: Rating, comment?: string): Promise<void> => {
      const trimmed = (comment ?? '').trim()
      const current = stored.get(matrixRowId)
      if (current?.rating === rating && trimmed === '') {
        return
      }
      setSending((inFlight) => new Set(inFlight).add(matrixRowId))
      setFailed((errors) => withoutKey(errors, matrixRowId))
      try {
        const record = await rateRow(bidId, submission(matrixRowId, rating, trimmed))
        if (isMountedRef.current) {
          setStored((records) => new Map(records).set(matrixRowId, record))
        }
      } catch (cause) {
        if (isMountedRef.current) {
          setFailed((errors) => new Map(errors).set(matrixRowId, describeApiError(cause)))
        }
      } finally {
        if (isMountedRef.current) {
          setSending((inFlight) => withoutMember(inFlight, matrixRowId))
        }
      }
    },
    [bidId, stored]
  )

  return {
    ratingOf: (matrixRowId) => stored.get(matrixRowId)?.rating,
    commentOf: (matrixRowId) => stored.get(matrixRowId)?.comment ?? undefined,
    isSending: (matrixRowId) => sending.has(matrixRowId),
    errorOf: (matrixRowId) => failed.get(matrixRowId),
    rate,
  }
}

function submission(matrixRowId: string, rating: Rating, comment: string): FeedbackSubmission {
  return {
    rating,
    matrix_row_id: matrixRowId === BID_TARGET ? null : matrixRowId,
    comment: comment === '' ? null : comment,
  }
}

/** The records keyed the way the screen asks for them; a bid-level rating keys on `''`. */
function indexByTarget(
  records: readonly FeedbackRecord[]
): ReadonlyMap<string, FeedbackRecord> {
  return new Map(records.map((record) => [record.matrix_row_id ?? BID_TARGET, record]))
}

/** A copy without that member; the state is replaced rather than mutated. */
function withoutMember(values: ReadonlySet<string>, member: string): ReadonlySet<string> {
  const next = new Set(values)
  next.delete(member)
  return next
}

/** A copy without that key, for the same reason. */
function withoutKey<T>(entries: ReadonlyMap<string, T>, key: string): ReadonlyMap<string, T> {
  const next = new Map(entries)
  next.delete(key)
  return next
}
