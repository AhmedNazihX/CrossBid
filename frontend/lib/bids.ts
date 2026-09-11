/**
 * Typed calls for the `/bids` routes (story S4.5.1; the start step of S4.3.1 lands here early).
 *
 * The types come straight from the generated schema — integration point I2 of the plan:
 * `GET /bids/{id}` is the shape the workspace polls, and a field the backend renames stops
 * compiling here.
 */
import type { components } from './api'
import { apiRequest } from './api-client'

export type BidResponse = components['schemas']['BidResponse']
export type BidStatus = components['schemas']['BidStatus']
export type BidSummary = components['schemas']['BidSummary']
export type BidDocument = components['schemas']['BidDocumentResponse']
export type Requirement = components['schemas']['Requirement']
export type RequirementCategory = components['schemas']['RequirementCategory']
export type ExtractionProblem = components['schemas']['ExtractionProblem']
export type StartBidRequest = components['schemas']['StartBidRequest']

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

/** Every bid of the company, newest first. */
export async function listBids(signal?: AbortSignal): Promise<readonly BidSummary[]> {
  const response = await apiRequest('get', '/bids', { signal })
  return response.bids
}

/** Starts a bid and resolves with the 202 body (`status: "queued"`). */
export function startBid(body: StartBidRequest): Promise<BidResponse> {
  return apiRequest('post', '/bids', { body })
}
