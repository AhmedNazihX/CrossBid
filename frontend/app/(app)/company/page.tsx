import type { Metadata } from 'next'

import { DocumentsPanel } from '@/components/documents/documents-panel'
import { PageHeader } from '@/components/layout/page-header'

export const metadata: Metadata = {
  title: 'Company · Crossbid',
}

/**
 * The company screen: the document upload table (S4.2.2). The profile form — country,
 * legal form, turnover, certificates, explanation language — is S4.2.1 and mounts above
 * the documents when it lands.
 *
 * A server component on purpose: the panel below is the client boundary, so the header and
 * metadata render without JavaScript.
 */
export default function CompanyPage() {
  return (
    <>
      <PageHeader
        title="Company"
        description="Your company's documents. Every check is answered from these, and every claim cites a page in them."
      />
      <DocumentsPanel />
    </>
  )
}
