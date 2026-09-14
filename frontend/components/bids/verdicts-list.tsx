'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'

import { EmptyState } from '@/components/common/empty-state'
import { Badge } from '@/components/ui/badge'
import { DataTable, Td, Th, Tr } from '@/components/ui/data-table'
import { Notice } from '@/components/ui/notice'
import { VerdictChip } from '@/components/ui/verdict-chip'
import { describeApiError } from '@/lib/api-client'
import { listBids, type BidSummary } from '@/lib/bids'
import { formatDateTime, formatLanguage, plural } from '@/lib/format'
import { BID_STATUS_LABELS } from './bid-status'

type ListState =
  | { readonly phase: 'loading' }
  | { readonly phase: 'failed'; readonly message: string }
  | { readonly phase: 'loaded'; readonly bids: readonly BidSummary[] }

/**
 * The sidebar's Verdicts entry (story S4.5.3), on the table shape of `Dashboard.dc.html`.
 *
 * A verdict is a thing a person owes an answer to, so the list is ordered by whether it is
 * owed: everything parked at the review interrupt first, then what has been decided and what
 * the decision was. Bids still running are counted in the footer rather than listed — they
 * are not verdicts yet, and a row that cannot be acted on next to rows that can is how a
 * waiting review gets missed.
 */
export function VerdictsList() {
  const [state, setState] = useState<ListState>({ phase: 'loading' })

  useEffect(() => {
    const controller = new AbortController()
    listBids(controller.signal)
      .then((bids) => setState({ phase: 'loaded', bids }))
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
        Loading your verdicts…
      </p>
    )
  }
  if (state.phase === 'failed') {
    return (
      <Notice tone="danger" title="Your verdicts could not be loaded">
        {state.message}
      </Notice>
    )
  }

  const awaiting = state.bids.filter((bid) => bid.status === 'awaiting_review')
  const decided = state.bids.filter(
    (bid) => bid.decision !== null && bid.decision !== undefined
  )
  const listed = [...awaiting, ...decided.filter((bid) => bid.status !== 'awaiting_review')]
  const running = state.bids.length - listed.length

  if (listed.length === 0) {
    return (
      <EmptyState
        title="No verdicts to review yet"
        description="A verdict is Go, Conditional, No-go, or Insufficient evidence, with the compliance matrix behind it. It appears once the evidence check has run over a bid, and nothing proceeds until a person confirms or overrides it."
        steps={
          running > 0
            ? [`${plural(running, 'bid')} still running; each appears here at its review step.`]
            : ['Start a bid; its verdict appears here when the evidence check has run.']
        }
        action={{ href: '/bids/new', label: 'Analyse tender' }}
        secondaryAction={{ href: '/bids', label: 'Back to tenders' }}
      />
    )
  }

  return (
    <DataTable
      caption="Verdicts waiting for your confirmation, then the ones you have decided."
      footer={
        running > 0
          ? `${plural(listed.length, 'verdict')} · ${plural(running, 'bid')} still running`
          : `${plural(listed.length, 'verdict')} · every row opens its workspace`
      }
    >
      <thead>
        <tr>
          <Th>Tender</Th>
          <Th>Verdict</Th>
          <Th>Phase</Th>
          <Th>Updated</Th>
        </tr>
      </thead>
      <tbody>
        {listed.map((bid) => {
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
                    {bid.ted_publication_number ?? '—'} · {formatLanguage(bid.source_language)}
                  </span>
                </div>
              </Td>
              <Td>
                {bid.decision === null || bid.decision === undefined ? (
                  <span className="text-text-muted">Not decided</span>
                ) : (
                  <VerdictChip
                    verdict={bid.decision}
                    size="sm"
                    confirmed={bid.status === 'complete'}
                  />
                )}
              </Td>
              <Td>
                <Badge tone={status.tone} pill={false}>
                  {status.label}
                </Badge>
              </Td>
              <Td className="whitespace-nowrap text-text-secondary">
                {formatDateTime(bid.updated_at)}
              </Td>
            </Tr>
          )
        })}
      </tbody>
    </DataTable>
  )
}
