import type { Metadata } from 'next'
import Link from 'next/link'

import { BidsTable } from '@/components/bids/bids-table'
import { PageHeader } from '@/components/layout/page-header'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/ui/icons'

export const metadata: Metadata = {
  title: 'Tenders · CrossBid',
}

/**
 * Tenders: every bid of the company, newest first, in the dashboard artboard's table shape
 * (story S4.5.1 brings the list forward; S4.4.1 adds verdict, deadline and open items).
 */
export default function BidsPage() {
  return (
    <>
      <PageHeader
        title="Tenders"
        description="Every tender you have started a bid on, and how far its run has got."
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
      <BidsTable />
    </>
  )
}
