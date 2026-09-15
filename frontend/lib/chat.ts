/**
 * Typed call for `POST /bids/{id}/chat` — "ask the tender" (story S4.6.1 over S3.5.1).
 *
 * The types come straight from the generated schema, like every other module here: a field
 * the backend renames stops compiling in this file rather than failing at run time.
 */
import type { components } from './api'
import { apiRequest } from './api-client'
import { MAX_COMMENT_CHARS } from './feedback'

/** What the bidder sends: one question, in any language. */
export type ChatQuestion = components['schemas']['ChatQuestion']

/** The delivered turn: the answer in the bidder's language, and where it got its facts. */
export type ChatTurn = components['schemas']['ChatTurn']

/**
 * Where a chat answer got one of its facts. Resolved server-side from what was actually
 * retrieved (ADR-0055) — the model never writes one — so `page` is always a real page.
 */
export type ChatCitation = components['schemas']['Citation']

/**
 * The API bounds a question with the same constant it bounds a comment
 * (`crossbid.models.review.MAX_COMMENT_CHARS`), so the two are one number here too.
 */
export const MAX_QUESTION_CHARS = MAX_COMMENT_CHARS

const CHAT_PATH = '/bids/{bid_id}/chat'

/**
 * Asks one question and resolves with the assistant's turn. Several seconds, one model
 * call's worth of money; the caller is expected to allow one in flight at a time.
 *
 * Answers **404** when the bid is not this company's (the same sentence as "not there"),
 * **422** for a blank or over-long question, **429** with a `Retry-After` when the company
 * has used its hour's questions, and **500** with a fixed sentence when the answer could not
 * be produced — nothing about the bid changes in that case, so asking again is safe.
 */
export function askAboutBid(
  bidId: string,
  question: string,
  signal?: AbortSignal
): Promise<ChatTurn> {
  return apiRequest('post', CHAT_PATH, {
    path: { bid_id: bidId },
    body: { question },
    signal,
  })
}
