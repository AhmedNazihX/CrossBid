import type { Metadata } from 'next'

import { ProfileForm } from '@/components/company/profile-form'
import { ProviderKeyCard } from '@/components/company/provider-key-card'
import { DocumentsPanel } from '@/components/documents/documents-panel'
import { PageHeader } from '@/components/layout/page-header'

export const metadata: Metadata = {
  title: 'Company · CrossBid',
}

/**
 * The company screen: the profile form (S4.2.1) above the document table (S4.2.2).
 *
 * The order is the order they are needed in. The profile is what every requirement is
 * checked *against*, and until it exists this account has no company at all — every other
 * route answers 404 (S0.3.1), which is why `RequireCompany` sends a new bidder straight
 * here. The documents are the evidence those checks cite, and uploading them before there
 * is a company to hang them on is not possible.
 *
 * The provider key sits between them because it gates both: without it, a document cannot
 * be embedded and a bid cannot be run, and the API answers 402 rather than billing the work
 * to a shared key (S5.4).
 *
 * A server component on purpose: the panels below are the client boundaries, so the header
 * and metadata render without JavaScript.
 */
export default function CompanyPage() {
  return (
    <>
      <PageHeader
        title="Company"
        description="The facts every requirement is checked against, and the documents that prove them."
      />
      <div className="flex flex-col gap-10">
        <ProfileForm />
        <ProviderKeyCard />
        <DocumentsPanel />
      </div>
    </>
  )
}
