import type { Metadata } from 'next'
import Link from 'next/link'

import { AuthCard } from '@/components/auth/auth-card'
import { Button } from '@/components/ui/button'

export const metadata: Metadata = {
  title: 'Page not found · CrossBid',
}

/**
 * The 404 (M8 of the 2026-09-15 audit: a mistyped URL showed Next's unbranded "404 / This
 * page could not be found" — the one screen nobody had written).
 *
 * No artboard draws it — the canvas of ADR-0014 has the six screens that existed when it was
 * confirmed — so, like sign-in (ADR-0034), it is built from what the artboards fixed:
 * `AuthCard`'s lockup–card–footnote frame on the canvas and the design system's `Button`,
 * with no spacing, colour or type of its own.
 *
 * It renders under the root layout only. A URL that matches no route is outside the `(app)`
 * group, so there is no shell to keep; the way back is the dashboard, and for a visitor with
 * no session `RequireSession` turns that into the sign-in page carrying the path.
 *
 * The wording says what happened and what is safe, and names no status code: "404" means
 * nothing to a bidder, and the address they typed is already in the bar above.
 */
export default function NotFound() {
  return (
    <AuthCard>
      <div className="flex flex-col gap-2">
        <h1 className="m-0 text-[length:var(--text-lg)] font-semibold text-text-primary">
          There is no page at this address
        </h1>
        <p className="m-0 [font:var(--type-body)] text-text-secondary">
          The link may be mistyped or out of date. Nothing is lost: every bid you have checked
          is still on your dashboard.
        </p>
      </div>
      <Button asChild fullWidth>
        <Link href="/dashboard">Go to the dashboard</Link>
      </Button>
    </AuthCard>
  )
}
