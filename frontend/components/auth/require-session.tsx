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
 */
import { usePathname, useRouter } from 'next/navigation'
import { useEffect } from 'react'

import { useSession } from '@/components/auth/session-provider'
import { LoadingState } from '@/components/common/loading-state'

export function RequireSession({ children }: Readonly<{ children: React.ReactNode }>) {
  const { status } = useSession()
  const router = useRouter()
  const pathname = usePathname()

  useEffect(() => {
    if (status !== 'signedOut') return
    const next = encodeURIComponent(pathname)
    router.replace(`/login?next=${next}`)
  }, [status, pathname, router])

  if (status === 'signedIn' || status === 'disabled') return <>{children}</>

  return <LoadingState message={status === 'loading' ? 'Loading…' : 'Taking you to sign in…'} />
}
