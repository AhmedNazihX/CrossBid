'use client'

/**
 * The guard on every route in the `(app)` group (story S4.1.1).
 *
 * **`loading` is not `signedOut`.** On the first paint the session is still being read out
 * of `localStorage`; redirecting then would bounce every returning visitor to the login
 * page and back, losing the route they asked for. So the guard renders a quiet waiting
 * state until the provider has decided, and only then redirects.
 *
 * **`disabled` renders straight through.** On the S0.3.1 dev bridge there is no session to
 * check and `X-Dev-Company` is doing the work, so the demo and every screen built before
 * this story behave exactly as they did.
 *
 * **It guards the content frame, not the shell.** Until the 2026-09-15 audit (M7) this
 * wrapped the whole shell in `app/(app)/layout.tsx`, so the waiting state was the *only*
 * thing on a freshly loaded page — no sidebar, no header, one centred word — on every full
 * load of every protected route. The layout now composes the chrome first and mounts this
 * guard inside the white content frame, so the sidebar paints at once and only the frame
 * waits (`LoadingState`). What a signed-out visitor sees for the moment before the redirect
 * is that chrome with "Taking you to sign in…" where the page would be: the nav labels and
 * the advisory line, nothing that belongs to an account. `AccountBlock` renders nothing
 * until `signedIn`, and `NavGroups` holds its developer probe until then for the same
 * reason.
 *
 * The redirect carries the path that was asked for, so following a deep link to a bid and
 * signing in lands on that bid rather than on the dashboard.
 *
 * **`failed` is drawn, not waited through.** Until 2026-09-16 the provider could stay
 * `loading` for ever — its bootstrap had no `catch`, so a stale tab whose auth chunk the
 * dev server no longer served sat at "Loading…" with the only clue in the console — and
 * this guard, which only knew `loading`, drew exactly that. It now renders the provider's
 * `problem` in the same danger `Notice` the bid workspace uses for a bid that could not be
 * loaded, with the two ways forward that case has: reload, or sign in again. The sign-in
 * link is a plain anchor rather than a `Link` on purpose — a full navigation fetches the
 * current build, which a client-side transition inside a stale one cannot.
 */
import { usePathname, useRouter } from 'next/navigation'
import { useEffect } from 'react'

import { useSession } from '@/components/auth/session-provider'
import { LoadingState } from '@/components/common/loading-state'
import { Button } from '@/components/ui/button'
import { Notice } from '@/components/ui/notice'

export function RequireSession({ children }: Readonly<{ children: React.ReactNode }>) {
  const { status, problem } = useSession()
  const router = useRouter()
  const pathname = usePathname()

  useEffect(() => {
    if (status !== 'signedOut') return
    const next = encodeURIComponent(pathname)
    router.replace(`/login?next=${next}`)
  }, [status, pathname, router])

  if (status === 'signedIn' || status === 'disabled') return <>{children}</>
  if (status === 'failed') return <SessionProblem problem={problem} pathname={pathname} />

  return <LoadingState message={status === 'loading' ? 'Loading…' : 'Taking you to sign in…'} />
}

function SessionProblem({
  problem,
  pathname,
}: Readonly<{ problem: string | undefined; pathname: string }>) {
  return (
    <>
      <Notice tone="danger" title="Your session could not be checked">
        {problem ?? 'Something went wrong while reading your session.'}
      </Notice>
      <div className="mt-4 flex gap-2">
        <Button variant="secondary" onClick={() => window.location.reload()}>
          Reload the page
        </Button>
        <Button asChild variant="ghost">
          <a href={`/login?next=${encodeURIComponent(pathname)}`}>Sign in</a>
        </Button>
      </div>
    </>
  )
}
