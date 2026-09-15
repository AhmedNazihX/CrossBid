'use client'

/**
 * The error boundary under the root layout (M8 of the 2026-09-15 audit: an unhandled throw in
 * any client component — and every screen is one — replaced the page with Next's default
 * error screen, losing the shell and any way back).
 *
 * Next mounts this in place of whatever segment threw. For the `(app)` group that is the
 * whole shell, sidebar included, because this boundary sits above the group's layout; an
 * `app/(app)/error.tsx` would keep the chrome and is the natural next step. This file is the
 * floor under every route — the marketing page and sign-in included — which is why it wears
 * `AuthCard`'s frame rather than the shell's: no artboard draws an error state, and the
 * lockup–card–footnote frame is the one screen chrome that needs no session (ADR-0034).
 *
 * **`reset` before a link.** `reset` re-renders the segment that threw. Most client errors
 * here are transient — a fetch that resolved after unmount, a stale chunk after a deploy —
 * and trying again in place is the cheaper recovery. The dashboard is the second exit, not
 * the only one.
 *
 * **The raw error is never shown.** The rest of the app words a failure as a `Notice` in
 * `tone="danger"`, a title saying what could not happen and a body saying what to do
 * (`bid-workspace.tsx`; `describeApiError`'s last resort is "Something went wrong. Try
 * again."). A stack or a bundler message is neither: it is not the bidder's to act on, and it
 * can carry a URL or an id they should not see. Next logs the error itself in development;
 * this build has no error sink, so nothing is re-logged here.
 */
import Link from 'next/link'

import { AuthCard } from '@/components/auth/auth-card'
import { Button } from '@/components/ui/button'
import { Notice } from '@/components/ui/notice'

interface ErrorPageProps {
  readonly error: Error & { readonly digest?: string }
  readonly reset: () => void
}

export default function ErrorPage({ reset }: ErrorPageProps) {
  return (
    <AuthCard>
      <h1 className="m-0 text-[length:var(--text-lg)] font-semibold text-text-primary">
        This page could not be shown
      </h1>
      <Notice tone="danger" title="Something went wrong">
        Trying again redraws this screen in place. If it fails a second time, the dashboard is
        the way back, and every bid you have checked is still there.
      </Notice>
      <div className="flex flex-col gap-3">
        <Button fullWidth onClick={reset}>
          Try again
        </Button>
        <Button asChild variant="secondary" fullWidth>
          <Link href="/dashboard">Back to the dashboard</Link>
        </Button>
      </div>
    </AuthCard>
  )
}
