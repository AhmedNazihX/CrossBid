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
 * The redirect carries the path that was asked for, so following a deep link to a bid and
 * signing in lands on that bid rather than on the dashboard.
 */
import { usePathname, useRouter } from 'next/navigation'
import { useEffect } from 'react'

import { useSession } from '@/components/auth/session-provider'

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

  return (
    <div className="flex min-h-dvh items-center justify-center px-4">
      <p className="m-0 [font:var(--type-body)] text-text-muted" role="status">
        {status === 'loading' ? 'Loading…' : 'Taking you to sign in…'}
      </p>
    </div>
  )
}
