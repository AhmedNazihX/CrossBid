import type { Metadata } from 'next'

import { NewBidFlow } from '@/components/bids/new-bid-flow'
import { Breadcrumb } from '@/components/layout/breadcrumb'
import { PageHeader } from '@/components/layout/page-header'

export const metadata: Metadata = {
  title: 'Analyse tender · CrossBid',
}

/**
 * Analyse tender — all three cards of `NewBid.dc.html` (S4.3.1): find the notice on TED,
 * upload the pack the buyer's own platform holds, then start.
 *
 * A server component; `NewBidFlow` is the client boundary, so the header and the metadata
 * render without JavaScript.
 */
export default function NewBidPage() {
  return (
    <>
      <Breadcrumb items={[{ label: 'Tenders', href: '/bids' }, { label: 'Analyse tender' }]} />
      <PageHeader
        title="Analyse tender"
        description="Find the tender, add the documents the buyer published, and start the check."
      />
      <NewBidFlow />
    </>
  )
}
