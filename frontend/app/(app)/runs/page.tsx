import type { Metadata } from 'next'

import { EmptyState } from '@/components/common/empty-state'
import { PageHeader } from '@/components/layout/page-header'

export const metadata: Metadata = {
  title: 'Agent runs · CrossBid',
}

/**
 * Placeholder behind the sidebar's Agent runs entry. Per-run stages, cost and duration
 * belong to the developer console (S4.6.2); until then a bid's stage is on its workspace.
 */
export default function RunsPage() {
  return (
    <>
      <PageHeader
        title="Agent runs"
        description="Each run of the agent: its stages, what it cost, and how long it took."
      />
      <EmptyState
        title="Runs are not listed here yet"
        description="The run log — stage timings, model calls and their cost — is the developer console's job and arrives with S4.6.2. Today each bid's workspace shows its own stage while the agent works."
        steps={['Open a bid from Tenders to follow its run.']}
        secondaryAction={{ href: '/bids', label: 'Open tenders' }}
      />
    </>
  )
}
