'use client'

/**
 * Where the magic link lands (story S4.1.1).
 *
 * Supabase redirects here with a one-time `code` in the query string; the client's
 * `detectSessionInUrl` exchanges it for a session as soon as it is constructed, and the
 * `SessionProvider` subscription then reports `signedIn`. So this page waits rather than
 * doing the exchange itself — two exchanges of a single-use code would race, and the loser
 * would report a failure for a sign-in that in fact worked.
 *
 * A link that has expired or been used already arrives as `?error=...` instead, and that
 * message is shown with a way back rather than a spinner that never resolves.
 */
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { Suspense, useEffect } from 'react'

import { useSession } from '@/components/auth/session-provider'
import { Button } from '@/components/ui/button'
import { Notice } from '@/components/ui/notice'
import { safeNextPath } from '@/lib/safe-next-path'

export default function AuthCallbackPage() {
  return (
    <Suspense fallback={<Waiting />}>
      <Callback />
    </Suspense>
  )
}

function Callback() {
  const router = useRouter()
  const params = useSearchParams()
  const { status } = useSession()
  const failure = params.get('error_description') ?? params.get('error')

  const next = safeNextPath(params.get('next'))

  useEffect(() => {
    if (status === 'signedIn') router.replace(next)
  }, [status, router, next])

  if (failure !== null) {
    return (
      <Shell>
        <Notice tone="danger" title="That sign-in link did not work">
          {failure}
        </Notice>
        <Button asChild variant="secondary">
          <Link href="/login">Ask for a new link</Link>
        </Button>
      </Shell>
    )
  }

  if (status === 'signedOut') {
    return (
      <Shell>
        <Notice tone="danger" title="That sign-in link did not work">
          It may have expired or already been used. Each link works once, for one hour.
        </Notice>
        <Button asChild variant="secondary">
          <Link href="/login">Ask for a new link</Link>
        </Button>
      </Shell>
    )
  }

  return <Waiting />
}

function Waiting() {
  return (
    <Shell>
      <p className="m-0 [font:var(--type-body)] text-text-secondary" role="status">
        Signing you in…
      </p>
    </Shell>
  )
}

function Shell({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-4 bg-surface-canvas px-4">
      <div className="flex w-full max-w-[400px] flex-col gap-4">{children}</div>
    </main>
  )
}
