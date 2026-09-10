import type { Metadata } from 'next'

import { EmptyState } from '@/components/common/empty-state'
import { PageHeader } from '@/components/layout/page-header'

export const metadata: Metadata = {
  title: 'New bid · Crossbid',
}

/**
 * Placeholder. TED search, notice selection, the tender-document upload and the
 * Start button are S4.3.1; the upload table it shares with the company page is
 * S4.2.2. Nothing here calls the API.
 */
export default function NewBidPage() {
  return (
    <>
      <PageHeader
        title="New bid"
        description="Find the tender, hand Crossbid its documents, and start the check."
      />
      <EmptyState
        title="Starting a bid is not wired up yet"
        description="This screen is still being built. It will search TED for the notice, then ask you for the procurement documents. Crossbid cannot fetch those itself: most EU buyers publish them on their own national platform behind a page a machine may not scrape, so you download the pack and upload it here."
        steps={[
          'Nothing to do here today.',
          'When it opens: search TED by keyword, country and CPV code, then pick the notice.',
          'Download the buyer’s procurement documents from the platform the notice links to, and upload them.',
          'Start the check once at least one document is ready.',
        ]}
        secondaryAction={{ href: '/dashboard', label: 'Back to dashboard' }}
      />
    </>
  )
}
