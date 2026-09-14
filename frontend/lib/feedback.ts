/**
 * Typed calls for the `/bids/{id}/feedback` routes (story S4.6.3).
 *
 * The types come straight from the generated schema, like every other module here: a field
 * the backend renames stops compiling in this file rather than failing at run time.
 */
import type { components } from './api'
import { apiRequest } from './api-client'

/** A thumb, in the values `feedback.rating` stores: `check (rating in (-1, 1))`. */
export type Rating = components['schemas']['Rating']

export const THUMB_UP: Rating = 1
export const THUMB_DOWN: Rating = -1

/** What the bidder sends. `matrix_row_id` null rates the bid's answer rather than a row. */
export type FeedbackSubmission = components['schemas']['FeedbackSubmission']

/** One stored rating, as the API answers it back. */
export type FeedbackRecord = components['schemas']['FeedbackRecord']

/** The API's own bound on a comment — `crossbid.models.review.MAX_COMMENT_CHARS`. */
export const MAX_COMMENT_CHARS = 4000

const FEEDBACK_PATH = '/bids/{bid_id}/feedback'

/**
 * Stores one rating and resolves with the row as it was written.
 *
 * Rating the same target again appends rather than replacing — the bidder's earlier answer
 * is part of the record the story keeps — so the screen shows what this call returned, and
 * `listFeedback` answers with the latest per target on the next load.
 *
 * Answers **404** when the bid is not this company's, or the row is not that bid's.
 */
export function rateRow(
  bidId: string,
  body: FeedbackSubmission,
  signal?: AbortSignal
): Promise<FeedbackRecord> {
  return apiRequest('post', FEEDBACK_PATH, {
    path: { bid_id: bidId },
    body,
    signal,
  })
}

/** What this company has already rated on the bid: the latest rating of each target. */
export async function listFeedback(
  bidId: string,
  signal?: AbortSignal
): Promise<readonly FeedbackRecord[]> {
  const response = await apiRequest('get', FEEDBACK_PATH, {
    path: { bid_id: bidId },
    signal,
  })
  return response.feedback
}
