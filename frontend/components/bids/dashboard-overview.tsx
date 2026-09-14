'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'

import { EmptyState } from '@/components/common/empty-state'
import { Icon } from '@/components/ui/icons'
import { Notice } from '@/components/ui/notice'
import { describeApiError } from '@/lib/api-client'
import { listBids, type BidSummary } from '@/lib/bids'
import { DashboardMetrics } from './dashboard-metrics'
import { DashboardTendersTable } from './dashboard-tenders-table'

type ListState =
  | { readonly phase: 'loading' }
  | { readonly phase: 'failed'; readonly message: string }
  | {
      readonly phase: 'loaded'
      readonly bids: readonly BidSummary[]
      /** When the list was read, so every countdown on the screen is measured from one instant. */
      readonly loadedAt: Date
    }

/**
 * The dashboard's body (story S4.4.1) — the "Key metrics" row and the tenders table of
 * `Dashboard.dc.html` over the one call `GET /bids` already makes.
 *
 * The three outcomes of that call are all rendered: the wait, the failure with the API's own
 * sentence, and the first-run empty state, which stays exactly as it was because a bidder
 * with nothing on the screen needs the three steps far more than an empty table.
 *
 * "Now" is captured once, with the list, rather than read per row: a countdown that each row
 * measures for itself can print two different answers for two tenders closing in the same
 * minute, and the instant belongs to the data anyway.
 */
export function DashboardOverview() {
  const [state, setState] = useState<ListState>({ phase: 'loading' })

  useEffect(() => {
    const controller = new AbortController()
    listBids(controller.signal)
      .then((bids) => setState({ phase: 'loaded', bids, loadedAt: new Date() }))
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) {
          setState({ phase: 'failed', message: describeApiError(cause) })
        }
      })
    return () => controller.abort()
  }, [])

  if (state.phase === 'loading') {
    return (
      <p role="status" className="m-0 text-text-muted">
        Loading your bids…
      </p>
    )
  }
  if (state.phase === 'failed') {
    return (
      <Notice tone="danger" title="Your bids could not be loaded">
        {state.message}
      </Notice>
    )
  }
  if (state.bids.length === 0) {
    return (
      <EmptyState
        title="No bids yet"
        description="A bid is one tender you are deciding whether to enter. CrossBid reads the tender's documents, lists what the buyer requires, and matches each requirement to your own evidence — then you confirm or overrule its verdict."
        steps={[
          'Fill in your company details, so checks run against your own facts.',
          'Start a new bid: find the tender on TED and upload the procurement documents the buyer published.',
          'Review the requirement matrix and confirm the go/no-go verdict.',
        ]}
        action={{ href: '/bids/new', label: 'Start a new bid' }}
        secondaryAction={{ href: '/company', label: 'Fill in company details' }}
      />
    )
  }

  return (
    <div className="flex flex-col">
      <SectionHeading title="Key metrics" />
      <DashboardMetrics bids={state.bids} />
      <SectionHeading
        title="Tenders by deadline"
        link={{ href: '/bids', label: 'View all tenders' }}
      />
      <DashboardTendersTable bids={state.bids} now={state.loadedAt} />
    </div>
  )
}

interface SectionHeadingProps {
  readonly title: string
  readonly link?: { readonly href: string; readonly label: string }
}

/**
 * The artboard's section rule: an 18 px semibold heading with an optional quiet link to the
 * fuller screen on the right. A real `h2`, so the two halves of the dashboard are reachable
 * by heading navigation rather than by eye alone.
 */
function SectionHeading({ title, link }: SectionHeadingProps) {
  return (
    <div className="mt-7 mb-3.5 flex items-center justify-between gap-3 first:mt-0">
      <h2 className="m-0 text-lg font-semibold leading-[1.2] tracking-[-0.02em]">{title}</h2>
      {link !== undefined && (
        <Link
          href={link.href}
          className="inline-flex items-center gap-1.5 font-medium text-text-secondary"
        >
          {link.label}
          <Icon name="arrow" size={14} />
        </Link>
      )}
    </div>
  )
}
