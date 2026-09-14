'use client'

/**
 * Where the magic link and the confirmation link land (S4.1.1; rewritten by ADR-0040).
 *
 * **This page owns the code exchange, and that is a correction.** ADR-0034 had it wait for
 * `detectSessionInUrl` to do the exchange, on the reasoning that two exchanges of a
 * single-use code would race. The reasoning was right and the design was wrong: supabase-js
 * treats a URL as a PKCE callback only when the `code` *and* a stored `code_verifier` are
 * both present, and the verifier is written in the browser that started the sign-up. Open
 * the link in a different browser — or after clearing site data — and supabase-js quietly
 * concludes there is nothing to exchange. Nothing happened, nothing failed, and the page
 * waited forever on a session that was never coming.
 *
 * So the client no longer detects (`detectSessionInUrl: false`), this page exchanges, and
 * there is still exactly one exchanger. The difference is that its failure is now a
 * sentence on the screen — including the one that actually explains the common case, which
 * is Supabase's own complaint that the code verifier is empty.
 *
 * **Every arrival resolves.** A code that works, a code that does not, an `?error=` from
 * Supabase, a build with sign-in switched off, and a bare `/auth/callback` with nothing on
 * it at all each end on something the visitor can act on. The state this replaced had one
 * fall-through that rendered a spinner for three of those five.
 *
 * The exchange is attempted once per code, guarded at module scope rather than by a ref,
 * because React's development double-mount would otherwise spend the code on the first
 * attempt and report the second one's failure.
 */
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { Suspense, useEffect, useState } from 'react'

import { useSession } from '@/components/auth/session-provider'
import { Button } from '@/components/ui/button'
import { Notice } from '@/components/ui/notice'
import { safeNextPath } from '@/lib/safe-next-path'
import { getSupabaseClient } from '@/lib/supabase'

/** Codes already spent, so a development double-mount cannot report its own second try. */
const attempted = new Set<string>()

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
  const next = safeNextPath(params.get('next'))
  const code = params.get('code')
  const [failure, setFailure] = useState<string | undefined>(
    params.get('error_description') ?? params.get('error') ?? undefined
  )

  useEffect(() => {
    if (status === 'signedIn') router.replace(next)
  }, [status, router, next])

  useEffect(() => {
    if (code === null || attempted.has(code)) return
    attempted.add(code)
    void (async () => {
      const supabase = await getSupabaseClient()
      if (supabase === null) return
      const { error } = await supabase.auth.exchangeCodeForSession(code)
      // Success needs no handling here: the provider's subscription reports `signedIn`
      // and the effect above moves on.
      if (error !== null) setFailure(error.message)
    })()
  }, [code])

  if (failure !== undefined) {
    return (
      <Problem
        title="That link did not work"
        hint="If you opened it in a different browser from the one you signed up in, ask for a new link there — the halves of the exchange do not cross browsers."
      >
        {failure}
      </Problem>
    )
  }

  if (status === 'disabled') {
    return (
      <Problem title="This build does not sign people in">
        It runs on the development bridge, so a sign-in link has nothing to hand a session to.
      </Problem>
    )
  }

  if (code === null && status === 'signedOut') {
    return (
      <Problem title="There is nothing to sign in with">
        This page is where a sign-in link lands, and this visit carried no link.
      </Problem>
    )
  }

  return <Waiting />
}

function Problem({
  title,
  hint,
  children,
}: Readonly<{ title: string; hint?: string; children: React.ReactNode }>) {
  return (
    <Shell>
      <Notice tone="danger" title={title}>
        {children}
      </Notice>
      {hint !== undefined && (
        <p className="m-0 [font:var(--type-body-sm)] text-text-secondary">{hint}</p>
      )}
      <Button asChild variant="secondary">
        <Link href="/login">Back to sign in</Link>
      </Button>
    </Shell>
  )
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
