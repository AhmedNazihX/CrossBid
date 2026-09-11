import type { Metadata } from 'next'

import { BidWorkspace } from '@/components/bids/bid-workspace'

export const metadata: Metadata = {
  title: 'Compliance · CrossBid',
}

/**
 * The bid workspace route (story S4.5.1): `Main.dc.html` on the desktop,
 * `WorkspacePhone.dc.html` on a phone. A server component on purpose — the workspace below
 * is the client boundary that polls `GET /bids/{id}`.
 */
export default async function BidPage({
  params,
}: Readonly<{ params: Promise<{ id: string }> }>) {
  const { id } = await params
  return <BidWorkspace bidId={id} />
}
