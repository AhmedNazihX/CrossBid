/**
 * The "Key metrics" row of `Dashboard.dc.html` (story S4.4.1), on the design system's
 * `MetricCard`.
 *
 * Three tiles, not the artboard's four, and none of them carries a delta. Every figure here
 * is counted from the bid list the page already holds — there is no metrics endpoint, and a
 * number a bidder cannot trace back to a row is the opposite of what this product sells. So
 * the artboard's "Requirements checked · last 7 days" is absent (`BidSummary` carries no
 * requirement count and no history to compare a week against) and so is "Go rate": a
 * percentage over three decided bids reads like a trend and is arithmetic on a sample too
 * small to mean one.
 *
 * What is left is the honest reading of "what needs me today": how much is still open, how
 * much of it is waiting on a person, and how many matrix rows are still unproven.
 */
import { MetricCard } from '@/components/ui/metric-card'
import type { BidStatus, BidSummary } from '@/lib/bids'

/** A bid in one of these has nothing more to run; everything else is still open work. */
const CLOSED_STATUSES: ReadonlySet<BidStatus> = new Set(['complete', 'failed'])

export interface DashboardMetricsProps {
  readonly bids: readonly BidSummary[]
}

export function DashboardMetrics({ bids }: DashboardMetricsProps) {
  const openTenders = bids.filter((bid) => !CLOSED_STATUSES.has(bid.status)).length
  const awaitingReview = bids.filter((bid) => bid.status === 'awaiting_review').length
  const openItems = bids.reduce((total, bid) => total + bid.open_items, 0)

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <MetricCard label="Open tenders" value={openTenders} period="Not yet decided" />
      <MetricCard label="Awaiting your confirmation" value={awaitingReview} period="Current" />
      <MetricCard
        label="Open items"
        value={openItems}
        period="Partially supported or unsupported rows"
      />
    </div>
  )
}
