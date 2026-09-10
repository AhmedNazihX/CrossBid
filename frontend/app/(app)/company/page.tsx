import type { Metadata } from 'next'

import { EmptyState } from '@/components/common/empty-state'
import { PageHeader } from '@/components/layout/page-header'

export const metadata: Metadata = {
  title: 'Company · Crossbid',
}

/**
 * Placeholder. The profile form is S4.2.1 and the document upload table is
 * S4.2.2; this story only guarantees that navigation reaches the route and that
 * what the reader finds there tells them what happens next.
 */
export default function CompanyPage() {
  return (
    <>
      <PageHeader
        title="Company"
        description="Your company's facts and documents. Every check is answered from these."
      />
      <EmptyState
        title="Company details are not editable yet"
        description="This screen is still being built. It will hold your country, legal form, turnover and certificates, plus the documents that prove them — certificates, insurance, references, accounts. Crossbid answers each tender requirement from these facts, so nothing is claimed that you cannot evidence."
        steps={[
          'Nothing to do here today.',
          'Gather the certificates and accounts you normally attach to a bid, so they are ready to upload.',
        ]}
        secondaryAction={{ href: '/dashboard', label: 'Back to dashboard' }}
      />
    </>
  )
}
