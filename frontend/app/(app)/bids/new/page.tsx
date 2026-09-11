import type { Metadata } from 'next'

import { StartBidForm } from '@/components/bids/start-bid-form'
import { Breadcrumb } from '@/components/layout/breadcrumb'
import { PageHeader } from '@/components/layout/page-header'
import { Badge } from '@/components/ui/badge'

export const metadata: Metadata = {
  title: 'Analyse tender · CrossBid',
}

/**
 * Analyse tender — the start step, the third card of `NewBid.dc.html`. The first two cards
 * (the notice found on TED, the in-flow upload) are S4.3.1, Increment 4; until then the pack
 * is uploaded on the Company profile page and chosen here.
 */
export default function NewBidPage() {
  return (
    <>
      <Breadcrumb items={[{ label: 'Tenders', href: '/bids' }, { label: 'Analyse tender' }]} />
      <PageHeader
        title="Analyse tender"
        actions={
          <Badge tone="info" pill={false}>
            Step 3 of 3 · Start
          </Badge>
        }
      />
      <StartBidForm />
    </>
  )
}
