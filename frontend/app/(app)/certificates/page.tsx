import type { Metadata } from 'next'

import { EmptyState } from '@/components/common/empty-state'
import { PageHeader } from '@/components/layout/page-header'

export const metadata: Metadata = {
  title: 'Certificates · CrossBid',
}

/**
 * Placeholder behind the sidebar's Certificates entry. The certificate table — what the
 * buyer asks for, the German equivalent eCertis names, the issuer — lands with the matrix
 * rows in Increment 2 (F1.1, F3.3).
 */
export default function CertificatesPage() {
  return (
    <>
      <PageHeader
        title="Certificates"
        description="What each buyer asks for, and the equivalent your home country issues."
      />
      <EmptyState
        title="Certificate mapping arrives with the evidence check"
        description="This screen will list every certificate and registration a tender requests beside its equivalent in your country, from the EU's eCertis service, with the issuer named. It lands with the matrix rows in Increment 2."
        steps={['Nothing to do here today.']}
        secondaryAction={{ href: '/dashboard', label: 'Back to dashboard' }}
      />
    </>
  )
}
