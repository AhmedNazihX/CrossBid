import type { Metadata } from 'next'

import { VerdictsList } from '@/components/bids/verdicts-list'
import { PageHeader } from '@/components/layout/page-header'

export const metadata: Metadata = {
  title: 'Verdicts · CrossBid',
}

/**
 * The Verdicts screen behind the sidebar's entry (story S4.5.3, `Verdict.dc.html`): the
 * queue of recommendations a person still owes an answer to.
 *
 * The review itself happens in the bid's own workspace, next to the matrix it is a verdict
 * on — a decision taken from a list, without the evidence in front of it, is exactly the
 * rubber stamp the interrupt exists to prevent. So this page routes rather than decides.
 */
export default function VerdictsPage() {
  return (
    <>
      <PageHeader
        title="Verdicts"
        description="Every recommendation waiting for your confirmation, and the ones you have decided. Open a tender to confirm or override its verdict against the matrix behind it."
      />
      <VerdictsList />
    </>
  )
}
