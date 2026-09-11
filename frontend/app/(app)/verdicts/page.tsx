import type { Metadata } from 'next'

import { EmptyState } from '@/components/common/empty-state'
import { PageHeader } from '@/components/layout/page-header'

export const metadata: Metadata = {
  title: 'Verdicts · CrossBid',
}

/**
 * Placeholder behind the sidebar's Verdicts entry. The review screen — the agent's
 * recommendation, what would change it, and your decision with a reason — is S4.5.3
 * (`Verdict.dc.html`) and needs the evidence check of Increment 2 first.
 */
export default function VerdictsPage() {
  return (
    <>
      <PageHeader
        title="Verdicts"
        description="Every recommendation waiting for your confirmation, and the ones you have decided."
      />
      <EmptyState
        title="No verdicts to review yet"
        description="A verdict is Go, Conditional, No-go, or Insufficient evidence, with the compliance matrix behind it. It appears once the evidence check has run over a bid, and nothing proceeds until a person confirms or overrides it."
        steps={[
          'Start a bid; the requirement list appears first, the verdict follows in Increment 2.',
        ]}
        action={{ href: '/bids/new', label: 'Analyse tender' }}
        secondaryAction={{ href: '/dashboard', label: 'Back to dashboard' }}
      />
    </>
  )
}
