/**
 * Typed calls for the `/bids` routes (story S4.5.1; the start step of S4.3.1 lands here early).
 *
 * The types come straight from the generated schema — integration point I2 of the plan:
 * `GET /bids/{id}` is the shape the workspace polls, and a field the backend renames stops
 * compiling here.
 */
import type { components } from './api'
import { conditionalGet, type Conditional } from './conditional-get'
import { apiConditionalGet, apiRequest } from './api-client'

export type BidResponse = components['schemas']['BidResponse']
export type BidStatus = components['schemas']['BidStatus']
export type BidSummary = components['schemas']['BidSummary']
export type BidDocument = components['schemas']['BidDocumentResponse']
export type Requirement = components['schemas']['Requirement']
export type RequirementCategory = components['schemas']['RequirementCategory']
export type ExtractionProblem = components['schemas']['ExtractionProblem']
export type MatrixRow = components['schemas']['MatrixRow']
export type RowStatus = components['schemas']['RowStatus']
export type Evidence = components['schemas']['Evidence']
export type EcertisEvidence = components['schemas']['EcertisEvidence']
export type StartBidRequest = components['schemas']['StartBidRequest']
export type Verdict = components['schemas']['Verdict']
export type Decision = components['schemas']['Decision']
export type Gap = components['schemas']['Gap']
export type GapSeverity = components['schemas']['GapSeverity']
export type ReviewSubmission = components['schemas']['ReviewSubmission']
export type RowEdit = components['schemas']['RowEdit']
export type ReviewerStatus = components['schemas']['ReviewerStatus']

/**
 * Statuses after which another poll would show nothing new: the interrupt (a person must
 * act), the end, or a failure. `checking`, `scoring` and `applying_review` are not reached in
 * Increment 1 but are in-flight stages when they are.
 */
const SETTLED_STATUSES: ReadonlySet<BidStatus> = new Set([
  'awaiting_review',
  'complete',
  'failed',
])

export function isBidSettled(bid: BidResponse): boolean {
  return SETTLED_STATUSES.has(bid.status)
}

/** One bid with its requirements so far — the call the poll repeats. */
export function getBid(bidId: string, signal?: AbortSignal): Promise<BidResponse> {
  return apiRequest('get', '/bids/{bid_id}', { path: { bid_id: bidId }, signal })
}

/**
 * The same call, conditional on what the caller already holds (M13).
 *
 * The poll repeats this every two seconds for the length of a run, and the answer carries
 * every requirement and every matrix row. Passing back the `ETag` that came with the last one
 * turns an unchanged tick into a 304 with no body, and returns the identical object, so the
 * workspace does not re-render either.
 */
export function getBidConditional(
  bidId: string,
  held: Conditional<BidResponse> | undefined,
  signal?: AbortSignal
): Promise<Conditional<BidResponse>> {
  return conditionalGet(
    (ifNoneMatch) =>
      apiConditionalGet('/bids/{bid_id}', { path: { bid_id: bidId }, ifNoneMatch, signal }),
    held
  )
}

/** One page of the company's bids, newest first, with where to continue (M13). */
export async function listBids(
  options: { limit?: number; cursor?: string; signal?: AbortSignal } = {}
): Promise<BidPage> {
  const { limit, cursor, signal } = options
  const response = await apiRequest('get', '/bids', {
    query: {
      ...(limit === undefined ? {} : { limit }),
      ...(cursor === undefined ? {} : { cursor }),
    },
    signal,
  })
  return { bids: response.bids, nextCursor: response.next_cursor ?? undefined }
}

/** One page of bids and the cursor that follows it, or `undefined` when this is the last. */
export interface BidPage {
  readonly bids: readonly BidSummary[]
  readonly nextCursor: string | undefined
}

/** Starts a bid and resolves with the 202 body (`status: "queued"`). */
export function startBid(body: StartBidRequest): Promise<BidResponse> {
  return apiRequest('post', '/bids', { body })
}

/**
 * Submits the review that finishes a bid (story S3.4.2) and resolves with the bid as the
 * review left it — `status: "complete"`, the re-scored verdict, and every row carrying the
 * reviewer's disposition. There is no polling afterwards: the backend runs the resume
 * inside this request because nothing past the interrupt calls a model.
 *
 * Answers **409** when the bid is not parked at `awaiting_review`, which is the same answer
 * for "somebody already reviewed it" and "it is still running" — the claim is one
 * conditional update and cannot tell them apart. **422** names a row the matrix does not
 * have, a status the row cannot legally take, or a decision differing from the agent's with
 * no reason given.
 */
export function submitReview(
  bidId: string,
  body: ReviewSubmission,
  signal?: AbortSignal
): Promise<BidResponse> {
  return apiRequest('post', '/bids/{bid_id}/review', {
    path: { bid_id: bidId },
    body,
    signal,
  })
}

/** A bid parked at its interrupt is the only one a review may be submitted for. */
export function isAwaitingReview(bid: BidResponse): boolean {
  return bid.status === 'awaiting_review'
}
