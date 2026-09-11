import type { Metadata } from 'next'

import { EmptyState } from '@/components/common/empty-state'
import { PageHeader } from '@/components/layout/page-header'

export const metadata: Metadata = {
  title: 'Dashboard · CrossBid',
}

/**
 * The landing screen of the shell.
 *
 * It shows the first-run empty state only. The bid list itself — status, verdict
 * badge, deadline countdown, open-item count — is S4.4.1, which is blocked on the
 * S4.0.1 design confirmation, so nothing here reads `GET /bids`.
 */
export default function DashboardPage() {
  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Every bid you have checked, and what needs you today."
      />
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
    </>
  )
}
