'use client'

import { cn } from 'cn'

import { VerdictChip } from '@/components/ui/verdict-chip'
import type { BidResponse, Verdict } from '@/lib/bids'
import { plural } from '@/lib/format'

/**
 * The decision, where the eye lands first — on both layouts. The full panel (gaps,
 * rationale, the reviewer's own decision) is one click or one tap away in the Verdict tab;
 * this line exists because the measured desktop page put that panel at y=13 876, and the
 * phone had nothing at all, above the fold that said what CrossBid had concluded (ADR-0060).
 *
 * The chip is qualified until a person has spoken: "· advisory" while `bid.decision` is
 * null, "· confirmed" after the review. Without the first word an unreviewed "No-go" read
 * as final at a glance, and the caveat that it was not lived in the Verdict tab — the very
 * tab a bidder who trusted the chip would not open.
 */
export function DecisionLine({
  bid,
  verdict,
  className,
}: {
  readonly bid: BidResponse
  readonly verdict: Verdict
  readonly className?: string
}) {
  const isReviewed = bid.decision !== null
  return (
    <div
      className={cn(
        'flex flex-wrap items-center gap-3 rounded-[14px] border border-border-default bg-surface-card px-4 py-3 shadow-xs',
        className
      )}
    >
      <VerdictChip
        verdict={verdict.decision}
        size="lg"
        confirmed={isReviewed}
        advisory={!isReviewed}
      />
      <p className="m-0 [font:var(--type-body-sm)] text-text-secondary">
        <b className="font-semibold text-text-primary">
          {verdict.mandatory_supported} of {verdict.mandatory_total}
        </b>{' '}
        mandatory requirements supported · {plural(verdict.gaps.length, 'gap')}
        {isReviewed && ' · reviewed'}
      </p>
    </div>
  )
}
