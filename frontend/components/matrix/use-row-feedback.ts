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
 * The bidder's ratings of one bid's answers — matrix rows and chat answers alike — loaded
 * once and sent as they are given (story S4.6.3).
 *
 * One controller for the whole workspace rather than one fetch per row: thirty expanded
 * rows would otherwise be thirty requests for a thumb each. `GET /bids/{id}/feedback`
 * answers the latest rating of every target in one call, and every `POST` answers with the
 * row it wrote, so the map is kept current without re-reading the list.
 *
 * **A target is a matrix row id, or an answer key from `answerTarget`.** The API has two
 * targets — a row (`matrix_row_id`) or the bid's own answer (`matrix_row_id: null`,
 * `routers/feedback.py`) — and the second is what a chat answer rates (ADR-0051). The API
 * cannot tell two answers in one bid apart, so the choice here was between rating only the
 * newest answer and rating each answer under its own client-side key. This file does the
 * second: every answer on screen can be rated, and the map shows exactly what the bidder
 * did in this tab. What it cannot do is pretend the server keeps the distinction — each
 * thumb is one more append-only bid-level row, the `GET` answers with the latest of them,
 * and the panel says so beside the thumbs. The alternative would have hidden the thumbs
 * from every answer but the last and, because all answers share one server key, would have
 * shown the previous answer's thumb as chosen on the next answer the moment it arrived.
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
  /** The thumb this target carries, or `undefined` when it has not been rated. */
  ratingOf(target: string): Rating | undefined
  /** The comment stored with that thumb, if the bidder gave one. */
  commentOf(target: string): string | undefined
  /** True while this target's rating is in flight, so its controls can say so. */
  isSending(target: string): boolean
  /** Why this target's last rating did not land, or `undefined` when it did. */
  errorOf(target: string): string | undefined
  /**
   * Files a rating for one target. Passing the thumb the target already carries with no
   * new comment is a no-op; everything else is sent.
   */
  rate(target: string, rating: Rating, comment?: string): Promise<void>
}

/**
 * Marks a target as a chat answer rather than a row. A row id is a UUID and can never start
 * with this, so the two key spaces cannot collide.
 */
const ANSWER_TARGET_PREFIX = 'answer:'

/** The key under which one chat answer's rating is held; sent as `matrix_row_id: null`. */
export function answerTarget(exchangeId: string): string {
  return `${ANSWER_TARGET_PREFIX}${exchangeId}`
}

function isAnswerTarget(target: string): boolean {
  return target.startsWith(ANSWER_TARGET_PREFIX)
}

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
    async (target: string, rating: Rating, comment?: string): Promise<void> => {
      const trimmed = (comment ?? '').trim()
      const current = stored.get(target)
      if (current?.rating === rating && trimmed === '') {
        return
      }
      setSending((inFlight) => new Set(inFlight).add(target))
      setFailed((errors) => withoutKey(errors, target))
      try {
        const record = await rateRow(bidId, submission(target, rating, trimmed))
        if (isMountedRef.current) {
          setStored((records) => new Map(records).set(target, record))
        }
      } catch (cause) {
        if (isMountedRef.current) {
          setFailed((errors) => new Map(errors).set(target, describeApiError(cause)))
        }
      } finally {
        if (isMountedRef.current) {
          setSending((inFlight) => withoutMember(inFlight, target))
        }
      }
    },
    [bidId, stored]
  )

  return {
    ratingOf: (target) => stored.get(target)?.rating,
    commentOf: (target) => stored.get(target)?.comment ?? undefined,
    isSending: (target) => sending.has(target),
    errorOf: (target) => failed.get(target),
    rate,
  }
}

function submission(target: string, rating: Rating, comment: string): FeedbackSubmission {
  return {
    rating,
    matrix_row_id: isAnswerTarget(target) ? null : target,
    comment: comment === '' ? null : comment,
  }
}

/**
 * The stored records keyed the way the screen asks for them.
 *
 * A bid-level record (`matrix_row_id: null`) is left out on purpose. It was a rating of a
 * chat answer, and the answer it was about is not on this screen: the chat log starts empty
 * on every load because no route reads the thread back (`use-bid-chat.ts`), and the record
 * carries no answer id to match even if it did. Keying it on any exchange that is here
 * would put a thumb on an answer the bidder never rated, so the latest bid-level rating the
 * `GET` returns is read and deliberately not shown.
 */
function indexByTarget(
  records: readonly FeedbackRecord[]
): ReadonlyMap<string, FeedbackRecord> {
  return new Map(
    records.flatMap((record) =>
      record.matrix_row_id === null || record.matrix_row_id === undefined
        ? []
        : [[record.matrix_row_id, record] as const]
    )
  )
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
