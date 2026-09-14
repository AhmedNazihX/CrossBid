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
 * `/company` itself is exempt, for the obvious reason.
 */
import { usePathname, useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'

import { useSession } from '@/components/auth/session-provider'
import { loadProfile } from '@/lib/companies'

const ONBOARDING_PATH = '/company'

type Check = 'checking' | 'hasCompany' | 'needsCompany' | 'skipped'

export function RequireCompany({ children }: Readonly<{ children: React.ReactNode }>) {
  const { status } = useSession()
  const router = useRouter()
  const pathname = usePathname()
  const [check, setCheck] = useState<Check>('checking')

  useEffect(() => {
    // Only a real session can have a company. On the dev bridge the header names one
    // already, and while the session is still loading there is nobody to ask about.
    if (status !== 'signedIn') {
      setCheck('skipped')
      return
    }
    const controller = new AbortController()
    void (async () => {
      try {
        const { profile } = await loadProfile(controller.signal)
        if (!controller.signal.aborted) {
          setCheck(profile === undefined ? 'needsCompany' : 'hasCompany')
        }
      } catch {
        // A failure here is the API being unreachable, not a missing company. Render the
        // screen and let it show its own error rather than redirecting on a network blip.
        if (!controller.signal.aborted) setCheck('skipped')
      }
    })()
    return () => controller.abort()
  }, [status])

  useEffect(() => {
    if (check === 'needsCompany' && pathname !== ONBOARDING_PATH) {
      router.replace(`${ONBOARDING_PATH}?next=${encodeURIComponent(pathname)}`)
    }
  }, [check, pathname, router])

  if (check === 'checking' && status === 'signedIn' && pathname !== ONBOARDING_PATH) {
    return (
      <div className="flex min-h-dvh items-center justify-center px-4">
        <p className="m-0 [font:var(--type-body)] text-text-muted" role="status">
          Loading…
        </p>
      </div>
    )
  }

  return <>{children}</>
}
