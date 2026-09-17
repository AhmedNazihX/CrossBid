'use client'

import { useCallback } from 'react'
import Link from 'next/link'

import { EmptyState } from '@/components/common/empty-state'
import { LoadMore } from '@/components/common/load-more'
import { Badge } from '@/components/ui/badge'
import { DataTable, Td, Th, Tr } from '@/components/ui/data-table'
import { Notice } from '@/components/ui/notice'
import { listBids } from '@/lib/bids'
import { formatDateTime, formatLanguage, plural } from '@/lib/format'
import { usePagedList } from '@/lib/use-paged-list'
import { BID_STATUS_LABELS } from './bid-status'

/**
 * The tenders table — the "Next 30 days" table shape of `Dashboard.dc.html` over
 * `GET /bids`: title with the notice number and language underneath in the citation face,
 * the phase badge, and when the status last changed; each title opens the workspace.
 *
 * Deliberately the shorter table. S4.4.1 gives the dashboard the deadline, buyer, verdict
 * and open-item columns ordered by what closes first; this page answers the other question —
 * what did I start last — and a second copy of the same five columns would only make the
 * two screens harder to tell apart.
 */
export function BidsTable() {
  const fetchPage = useCallback(async (cursor: string | undefined, signal: AbortSignal) => {
    const page = await listBids({ cursor, signal })
    return { items: page.bids, nextCursor: page.nextCursor }
  }, [])
  const state = usePagedList(fetchPage)

  if (state.phase === 'loading') {
    return (
      <p role="status" className="m-0 text-text-muted">
        Loading your tenders…
      </p>
    )
  }
  if (state.phase === 'failed') {
    return (
      <Notice tone="danger" title="Your tenders could not be loaded">
        {state.message}
      </Notice>
    )
  }
  if (state.items.length === 0) {
    return (
      <EmptyState
        title="No tenders yet"
        description="A bid is one tender you are deciding whether to enter. CrossBid reads its documents, lists what the buyer requires with a page for every line, and — once the evidence check lands — matches each requirement to your own evidence."
        steps={[
          'Upload the tender’s procurement documents on the Company profile page as Tender document.',
          'Start the analysis with the notice number and the tender’s language.',
          'Follow the run in the workspace; requirements appear as they are extracted.',
        ]}
        action={{ href: '/bids/new', label: 'Analyse tender' }}
        secondaryAction={{ href: '/company', label: 'Upload documents' }}
      />
    )
  }
  return (
    <>
      <DataTable
        caption="Your tenders, newest first."
        footer={`${plural(state.items.length, 'tender')} · every bid opens its workspace`}
      >
        <thead>
          <tr>
            <Th>Tender</Th>
            <Th>Phase</Th>
            <Th>Updated</Th>
          </tr>
        </thead>
        <tbody>
          {state.items.map((bid) => {
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
                      {bid.ted_publication_number ?? '—'} ·{' '}
                      {formatLanguage(bid.source_language)}
                    </span>
                  </div>
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
      <LoadMore
        hasMore={state.hasMore}
        isLoadingMore={state.isLoadingMore}
        message={state.message}
        onLoadMore={state.loadMore}
        noun="tenders"
      />
    </>
  )
}
