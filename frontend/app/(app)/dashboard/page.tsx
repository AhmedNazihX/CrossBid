import type { Metadata } from 'next'
import Link from 'next/link'

import { DashboardOverview } from '@/components/bids/dashboard-overview'
import { PageHeader } from '@/components/layout/page-header'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/ui/icons'

export const metadata: Metadata = {
  title: 'Dashboard · CrossBid',
}

/**
 * The landing screen of the shell, on `Dashboard.dc.html` (story S4.4.1).
 *
 * It answers one question — what needs you today — so the page itself stays a header and a
 * heading, and everything that depends on `GET /bids` lives below the client boundary in
 * `DashboardOverview`: the metric tiles, and the tenders table with each bid's verdict, its
 * deadline on the buyer's clock, and how many matrix rows are still open.
 */
export default function DashboardPage() {
  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Every bid you have checked, and what needs you today."
        actions={
          <Button asChild>
            <Link href="/bids/new">
              <span className="inline-flex size-4">
                <Icon name="spark" size={16} />
              </span>
              Analyse tender
            </Link>
          </Button>
        }
      />
      <DashboardOverview />
    </>
  )
}
