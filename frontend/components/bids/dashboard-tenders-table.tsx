/**
 * The tenders table of `Dashboard.dc.html` (story S4.4.1): `Tender · Due · Phase · Buyer ·
 * Verdict` over a semantic table, so every column is announced and the rows are navigable.
 *
 * The artboard's `Value` column is not here — `BidSummary` carries no contract value, and a
 * blank money column is worse than none. Everything else the artboard shows, the API now
 * sends.
 *
 * Ordering is the point of the screen rather than a preference: the dashboard answers "what
 * needs me today", so the soonest deadline is first and the bids with no deadline recorded
 * sink to the end, where they cannot push a closing tender off the top of the page. The
 * tenders page (S4.5.1) keeps the newest-first order for the other question, "what did I
 * start last".
 *
 * Urgency is said in words before it is said in colour — "Overdue", "2 days" — because a
 * bidder who cannot tell amber from stone still has to know which tender closes on Friday.
 */
import Link from 'next/link'
import { cn } from 'cn'

import { Badge } from '@/components/ui/badge'
import { DataTable, Td, Th, Tr } from '@/components/ui/data-table'
import { Icon } from '@/components/ui/icons'
import { VerdictChip } from '@/components/ui/verdict-chip'
import type { BidSummary } from '@/lib/bids'
import { formatLanguage, plural } from '@/lib/format'
import { BID_STATUS_LABELS } from './bid-status'
import {
  countdownTo,
  deadlineSortKey,
  formatBuyerClockDate,
  formatBuyerClockTime,
  NO_DEADLINE,
  type DeadlineUrgency,
} from './deadline'

/** What a cell prints where the API sent nothing: never a blank, never a guess. */
const EM_DASH = '—'

/** Colour only reinforces the wording; it is never the only carrier of the urgency. */
const URGENCY_CLASSES: Readonly<Record<DeadlineUrgency, string>> = {
  overdue: 'font-medium text-status-danger-text',
  urgent: 'font-medium text-status-warning-text',
  soon: 'text-text-secondary',
  distant: 'text-text-secondary',
}

export interface DashboardTendersTableProps {
  readonly bids: readonly BidSummary[]
  /** The instant every countdown is measured from, so all rows agree on "now". */
  readonly now: Date
}

export function DashboardTendersTable({ bids, now }: DashboardTendersTableProps) {
  const ordered = sortByDeadline(bids)
  const awaiting = bids.filter((bid) => bid.status === 'awaiting_review').length

  return (
    <DataTable
      caption="Your tenders, soonest deadline first; the ones with no deadline recorded last. Deadlines are shown on the buyer's clock."
      footer={
        awaiting > 0
          ? `${plural(ordered.length, 'tender')} · ${plural(awaiting, 'verdict')} awaiting your confirmation`
          : `${plural(ordered.length, 'tender')} · every row opens its workspace`
      }
    >
      <thead>
        <tr>
          <Th>Tender</Th>
          <Th>Due</Th>
          <Th>Phase</Th>
          <Th>Buyer</Th>
          <Th>Verdict</Th>
        </tr>
      </thead>
      <tbody>
        {ordered.map((bid) => {
          const status = BID_STATUS_LABELS[bid.status]
          return (
            <Tr key={bid.id} className="hover:bg-surface-sunken">
              <Td className="min-w-[240px]">
                <div className="flex flex-col gap-[3px]">
                  <Link
                    href={`/bids/${encodeURIComponent(bid.id)}`}
                    className="font-medium [overflow-wrap:anywhere]"
                  >
                    {bid.title}
                  </Link>
                  <span className="[font:var(--type-mono)] text-text-muted">
                    {bid.ted_publication_number ?? EM_DASH} ·{' '}
                    {formatLanguage(bid.source_language)}
                  </span>
                </div>
              </Td>
              <Td>
                <DeadlineCell bid={bid} now={now} />
              </Td>
              <Td>
                <Badge tone={status.tone} pill={false}>
                  {status.label}
                </Badge>
              </Td>
              <Td className="min-w-[160px] text-text-secondary">{bid.buyer ?? EM_DASH}</Td>
              <Td>
                <div className="flex flex-col items-start gap-1">
                  {bid.decision === null || bid.decision === undefined ? (
                    <span className="text-text-muted">Not decided</span>
                  ) : (
                    <VerdictChip
                      verdict={bid.decision}
                      size="sm"
                      confirmed={bid.status === 'complete'}
                    />
                  )}
                  <span className="[font:var(--type-body-sm)] text-text-muted">
                    {describeOpenItems(bid)}
                  </span>
                </div>
              </Td>
            </Tr>
          )
        })}
      </tbody>
    </DataTable>
  )
}

interface DeadlineCellProps {
  readonly bid: BidSummary
  readonly now: Date
}

/**
 * The date on the buyer's clock, the countdown beside it, and the buyer's hour underneath
 * with the offset it was written on. No deadline gives an em dash and says why — a bid
 * started before TED search lands (S1.2.1) simply has none.
 */
function DeadlineCell({ bid, now }: DeadlineCellProps) {
  const countdown = countdownTo(bid.deadline, now)
  if (countdown === null) {
    return (
      <div className="flex flex-col gap-[3px]">
        <span className="text-text-muted">{NO_DEADLINE}</span>
        <span className="[font:var(--type-body-sm)] text-text-muted">No deadline recorded</span>
      </div>
    )
  }
  return (
    <div className="flex flex-col gap-[3px]">
      <span
        className={cn(
          'inline-flex items-center gap-1.5 whitespace-nowrap',
          URGENCY_CLASSES[countdown.urgency]
        )}
      >
        <Icon name="clock" size={15} />
        {formatBuyerClockDate(bid.deadline, bid.deadline_utc_offset_minutes)} ·{' '}
        {countdown.short}
      </span>
      <span className="[font:var(--type-body-sm)] whitespace-nowrap text-text-muted">
        {formatBuyerClockTime(bid.deadline, bid.deadline_utc_offset_minutes)}
      </span>
    </div>
  )
}

/**
 * How much of the matrix still needs somebody. A bid whose evidence check has not run has
 * no open items *and* no settled ones, and saying "no open items" there would read as
 * reassurance the agent has not earned.
 */
function describeOpenItems(bid: BidSummary): string {
  if (bid.open_items > 0) {
    return plural(bid.open_items, 'open item')
  }
  return bid.decision === null || bid.decision === undefined
    ? 'Nothing checked yet'
    : 'No open items'
}

/** Soonest deadline first, no deadline last, and the most recently touched first within a tie. */
function sortByDeadline(bids: readonly BidSummary[]): readonly BidSummary[] {
  return [...bids].sort((left, right) => {
    const leftKey = deadlineSortKey(left.deadline)
    const rightKey = deadlineSortKey(right.deadline)
    if (leftKey !== rightKey) {
      return leftKey < rightKey ? -1 : 1
    }
    return (right.updated_at ?? '').localeCompare(left.updated_at ?? '')
  })
}
