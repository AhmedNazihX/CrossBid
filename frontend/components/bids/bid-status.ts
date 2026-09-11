import type { BadgeTone } from '@/components/ui/badge'
import type { BidStatus } from '@/lib/bids'

export interface BidStatusLabel {
  /** The design system's words for the stage, sentence case. */
  readonly label: string
  readonly tone: BadgeTone
  /** One line under the badge while the agent works, saying what to expect. */
  readonly hint?: string
}

/**
 * What each `BidStatus` means to the bidder. The machine's names are the API's; these are
 * the words of the confirmed canvas (ADR-0014): amber for "waits on you", green for done,
 * red for failed, the one blue for every stage in flight.
 */
export const BID_STATUS_LABELS: Readonly<Record<BidStatus, BidStatusLabel>> = {
  queued: {
    label: 'Queued',
    tone: 'neutral',
    hint: 'The run is about to start.',
  },
  parsing: {
    label: 'Reading the pack',
    tone: 'info',
    hint: 'Every page of every document is read first; pages without a text layer are counted, never guessed.',
  },
  extracting: {
    label: 'Extracting requirements',
    tone: 'info',
    hint: 'Requirements appear below as each section is read, each with its page in the tender.',
  },
  checking: {
    label: 'Checking evidence',
    tone: 'info',
    hint: 'Each requirement is being checked against your company documents.',
  },
  scoring: {
    label: 'Scoring',
    tone: 'info',
    hint: 'The verdict is being assembled from the matrix.',
  },
  awaiting_review: {
    label: 'Awaiting your confirmation',
    tone: 'warning',
  },
  applying_review: {
    label: 'Applying your review',
    tone: 'info',
    hint: 'Your edits are being folded into the verdict.',
  },
  complete: {
    label: 'Complete',
    tone: 'success',
  },
  failed: {
    label: 'Failed',
    tone: 'danger',
  },
}
