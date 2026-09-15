'use client'

/**
 * Send a signed-in bidder who has no company yet to the form that creates one (S4.2.1).
 *
 * `owner_user_id` is `NOT NULL`, so a company arrives with its owner or not at all
 * (S0.3.1) — which means a brand-new account is authenticated and has nothing to be scoped
 * to, and every tenant route answers **404 with a message naming `POST /companies`**. That
 * message is correct and is exactly the wrong thing to show a person: the first screen
 * after their first sign-in should not name an HTTP verb.
 *
 * So the check happens once, in the shell, and a bidder with no company lands on
 * `/company` instead of on a dashboard that can only fail. It runs the same `GET
 * /companies/me` the form is about to run, one request either way.
 *
 * **The redirect carries where they were going, and that is not a detail.** A bounce with
 * nothing to show for it reads as a broken link, not as a step: you click Dashboard, the URL
 * changes to something you did not ask for, and nothing on the page acknowledges that you
 * asked for anything. `?next=` is what lets the form say why it interrupted and then finish
 * the journey it interrupted (ADR-0041).
 *
 * **The check re-runs on every navigation until it finds a company, and never after.**
 * Depending on the session alone was a bug with a long fuse (ADR-0042): the `(app)` layout
 * stays mounted as you move between routes inside it, so the gate ran exactly once — and a
 * bidder who then *created* their company was still carrying `needsCompany`. Every click on
 * Dashboard bounced off stale state, forever, until a full page reload. `found` is what
 * stops the extra request once there is an answer that cannot change back.
 *
 * **The wait is drawn inside the content frame.** This guard sits under `RequireSession`,
 * inside the shell's white frame (2026-09-15 audit, M7), so while the profile is in flight
 * the sidebar and header stay put and only the frame shows `LoadingState` — the same line
 * `RequireSession` shows, from the same component, so the two waits cannot drift apart.
 *
 * `/company` itself is exempt, for the obvious reason.
 */
import { usePathname, useRouter } from 'next/navigation'
import { useEffect, useRef, useState } from 'react'

import { useSession } from '@/components/auth/session-provider'
import { LoadingState } from '@/components/common/loading-state'
import { loadProfile } from '@/lib/companies'

const ONBOARDING_PATH = '/company'

type Check = 'checking' | 'hasCompany' | 'needsCompany' | 'skipped'

export function RequireCompany({ children }: Readonly<{ children: React.ReactNode }>) {
  const { status } = useSession()
  const router = useRouter()
  const pathname = usePathname()
  const [check, setCheck] = useState<Check>('checking')
  /** Once a company has been seen, it cannot un-exist; stop asking. */
  const found = useRef(false)

  useEffect(() => {
    // Only a real session can have a company. On the dev bridge the header names one
    // already, and while the session is still loading there is nobody to ask about.
    if (status !== 'signedIn') {
      setCheck('skipped')
      return
    }
    if (found.current) {
      setCheck('hasCompany')
      return
    }
    const controller = new AbortController()
    // Back to `checking` first, so the redirect below cannot fire on the previous answer
    // while this one is still in flight — which is the whole defect this re-run fixes.
    setCheck('checking')
    void (async () => {
      try {
        const { profile } = await loadProfile(controller.signal)
        if (controller.signal.aborted) return
        found.current = profile !== undefined
        setCheck(profile === undefined ? 'needsCompany' : 'hasCompany')
      } catch {
        // A failure here is the API being unreachable, not a missing company. Render the
        // screen and let it show its own error rather than redirecting on a network blip.
        if (!controller.signal.aborted) setCheck('skipped')
      }
    })()
    return () => controller.abort()
  }, [status, pathname])

  useEffect(() => {
    if (check === 'needsCompany' && pathname !== ONBOARDING_PATH) {
      router.replace(`${ONBOARDING_PATH}?next=${encodeURIComponent(pathname)}`)
    }
  }, [check, pathname, router])

  if (check === 'checking' && status === 'signedIn' && pathname !== ONBOARDING_PATH) {
    return <LoadingState message="Loading…" />
  }

  return <>{children}</>
}
