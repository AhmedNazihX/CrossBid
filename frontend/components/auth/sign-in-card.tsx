'use client'

/**
 * The sign-in screen (story S4.1.1).
 *
 * There is no artboard for this one — the canvas of ADR-0014 draws the six screens that
 * existed when it was confirmed, and sign-in was S4.1.1's to design. So it is built from
 * the primitives the artboards already fixed (`Input`, `Button`, `Notice`) on the
 * marketing page's canvas and brand lockup, and invents no spacing, colour or type of its
 * own. ADR-0034 records that.
 *
 * **The form has two states and they are not the same screen.** Before sending, an email
 * field; after sending, the link has gone to an address and the useful thing to show is
 * *which* address, plus a way back for a typo. A single screen that just greys out the
 * button would leave the bidder watching a mailbox they may have misspelled.
 *
 * **A failure to send is never silent, and never guessed at.** Supabase's own message is
 * shown as it comes: rate limiting ("For security purposes, you can only request this
 * once every 60 seconds") is the one users actually hit, and paraphrasing it into
 * "something went wrong" would hide the one instruction that helps.
 *
 * **The address is never confirmed or denied.** Supabase answers the same way for a known
 * and an unknown address, and so does this screen: telling a stranger which emails have
 * accounts is an enumeration oracle, and it is why the success state says "if that address
 * has an account".
 */
import Image from 'next/image'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useEffect, useState, type FormEvent } from 'react'

import { useSession } from '@/components/auth/session-provider'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Notice } from '@/components/ui/notice'
import { AUTH_MODE, configurationProblem } from '@/lib/auth-mode'
import { safeNextPath } from '@/lib/safe-next-path'

type Stage = 'form' | 'sending' | 'sent'

export function SignInCard() {
  const { sendMagicLink, status } = useSession()
  const router = useRouter()
  const next = safeNextPath(useSearchParams().get('next'))
  const [email, setEmail] = useState('')
  const [stage, setStage] = useState<Stage>('form')
  const [error, setError] = useState<string | undefined>(undefined)

  // Already signed in — reaching the login page then means a stale tab or a bookmark, and
  // showing a form that would email a second link is the wrong answer to either.
  useEffect(() => {
    if (status === 'signedIn') router.replace(next)
  }, [status, router, next])

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(undefined)
    setStage('sending')
    try {
      await sendMagicLink(email.trim(), next)
      setStage('sent')
    } catch (cause) {
      setStage('form')
      setError(cause instanceof Error ? cause.message : 'The link could not be sent.')
    }
  }

  if (status === 'disabled') {
    return (
      <Card>
        <Notice
          tone={configurationProblem === undefined ? 'neutral' : 'danger'}
          title={
            configurationProblem === undefined
              ? 'This build does not sign people in'
              : 'This build cannot sign people in'
          }
        >
          {configurationProblem ??
            `NEXT_PUBLIC_AUTH_MODE=${AUTH_MODE}: this copy names its company with a header ` +
              'instead of a session. Set NEXT_PUBLIC_AUTH_MODE=supabase in ' +
              'frontend/.env.local and restart the dev server to turn sign-in on.'}
        </Notice>
        <Button asChild variant="secondary" fullWidth>
          <Link href="/dashboard">Continue to the dashboard</Link>
        </Button>
      </Card>
    )
  }

  if (stage === 'sent') {
    return (
      <Card>
        <div className="flex flex-col gap-2">
          <h1 className="m-0 text-[length:var(--text-lg)] font-semibold text-text-primary">
            Check your inbox
          </h1>
          <p className="m-0 [font:var(--type-body)] text-text-secondary">
            If <span className="font-medium text-text-primary">{email.trim()}</span> has an
            account, a sign-in link is on its way. It expires in an hour and can be used once.
          </p>
        </div>
        <Button variant="ghost" fullWidth onClick={() => setStage('form')}>
          Use a different address
        </Button>
      </Card>
    )
  }

  return (
    <Card>
      <div className="flex flex-col gap-2">
        <h1 className="m-0 text-[length:var(--text-lg)] font-semibold text-text-primary">
          Sign in
        </h1>
        <p className="m-0 [font:var(--type-body)] text-text-secondary">
          We email you a link. There is no password to remember or to lose.
        </p>
      </div>

      {error !== undefined && (
        <Notice tone="danger" title="The link could not be sent">
          {error}
        </Notice>
      )}

      <form className="flex flex-col gap-4" onSubmit={onSubmit} noValidate>
        <Input
          label="Work email"
          type="email"
          name="email"
          autoComplete="email"
          required
          autoFocus
          placeholder="sabine@example-it.de"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          disabled={stage === 'sending'}
        />
        <Button type="submit" fullWidth disabled={stage === 'sending' || email.trim() === ''}>
          {stage === 'sending' ? 'Sending…' : 'Email me a sign-in link'}
        </Button>
      </form>
    </Card>
  )
}

function Card({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center bg-surface-canvas px-4 py-12">
      <div className="flex w-full max-w-[400px] flex-col gap-6">
        <Link
          href="/"
          className="inline-flex min-h-11 items-center self-center rounded-md"
          aria-label="CrossBid — home"
        >
          <Image
            src="/logo-lockup.svg"
            alt="CrossBid"
            width={124}
            height={30}
            priority
            className="block h-[30px] w-auto"
          />
        </Link>
        <div className="flex flex-col gap-5 rounded-[14px] border border-border-default bg-surface-card p-7 shadow-xs">
          {children}
        </div>
        <p className="m-0 text-center [font:var(--type-body-sm)] text-text-muted">
          Crossbid is advisory: it never submits a bid for you.
        </p>
      </div>
    </main>
  )
}
