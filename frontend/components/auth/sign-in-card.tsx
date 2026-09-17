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
 * **Four methods, one screen (ADR-0038, ADR-0053).** A password for an account that has
 * one, an emailed link for everyone else, a third that registers, and a fourth that mails a
 * reset. They are four `Record<Method, …>` entries rather than four screens because they
 * differ in one input and three strings; the tables below are what keeps a fifth from
 * costing a new component.
 *
 * The link *also* registers when there is no account (`shouldCreateUser` stays at its
 * default), which is the deliberate choice recorded in ADR-0053: refusing would tell a
 * stranger which addresses exist, and the plan's "never manage a password" promise is the
 * one this screen exists to keep.
 *
 * **The link half has two states and they are not the same screen.** Before sending, an
 * email field; after sending, the link has gone to an address and the useful thing to show
 * is *which* address, plus a way back for a typo. A single screen that just greys out the
 * button would leave the bidder watching a mailbox they may have misspelled.
 *
 * **A failure is never silent, and never guessed at.** Supabase's own message is shown as
 * it comes: "email rate limit exceeded" is the one that actually turns up — the built-in
 * mailer allows two messages an hour — and paraphrasing it into "something went wrong"
 * would hide the one fact that explains it. The same goes for "Invalid login credentials".
 *
 * **The address is never confirmed or denied.** Supabase answers the same way for a known
 * and an unknown address on the link and reset paths, and so does this screen: telling a
 * stranger which emails have accounts is an enumeration oracle, and it is why the sent
 * state says "if that address has an account" for both. The password path is the exception
 * and cannot be otherwise — "Invalid login credentials" is the answer to a wrong password
 * and a missing account alike, which is Supabase declining to distinguish them for us.
 */
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useEffect, useRef, useState, type FormEvent } from 'react'

import { AuthCard } from '@/components/auth/auth-card'
import { useSession } from '@/components/auth/session-provider'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/ui/icons'
import { Input } from '@/components/ui/input'
import { Notice } from '@/components/ui/notice'
import { AUTH_MODE, configurationProblem } from '@/lib/auth-mode'
import { safeNextPath } from '@/lib/safe-next-path'

type Stage = 'form' | 'sending' | 'sent'
type Method = 'password' | 'link' | 'register' | 'reset'

export function SignInCard() {
  const { sendMagicLink, signInWithPassword, register, resetPassword, status } = useSession()
  const router = useRouter()
  const next = safeNextPath(useSearchParams().get('next'))
  const [method, setMethod] = useState<Method>('password')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [stage, setStage] = useState<Stage>('form')
  const [error, setError] = useState<string | undefined>(undefined)
  const [revealed, setRevealed] = useState(false)
  const [complaint, setComplaint] = useState<Complaint | undefined>(undefined)
  const emailField = useRef<HTMLInputElement>(null)
  const passwordField = useRef<HTMLInputElement>(null)

  const busy = stage === 'sending'
  const registering = method === 'register'
  // A password is typed on exactly two of the four screens. `reset` and `link` both ask for
  // an address and mail something to it; neither can be told apart by a password field.
  const needsPassword = method === 'password' || registering
  const incomplete = email.trim() === '' || (needsPassword && password === '')

  /**
   * The first thing wrong with the form, in the order a person fills it in — one message at
   * a time, because two complaints at once do not say which to fix first.
   *
   * This is the browser's `required` and `type="email"` checking, done here because the form
   * carries `noValidate` and would otherwise do none: the native bubble cannot be styled to
   * this card, disappears on the next keystroke, and is not what a screen reader reads. What
   * replaces it is the field's own description, which is read out when focus lands there.
   */
  function firstComplaint(): Complaint | undefined {
    const address = email.trim()
    if (address === '') return { field: 'email', message: 'Enter your work email.' }
    if (!EMAIL_SHAPE.test(address)) {
      return { field: 'email', message: 'That does not look like an email address.' }
    }
    if (needsPassword && password === '') {
      return { field: 'password', message: 'Enter your password.' }
    }
    return undefined
  }

  // Already signed in — reaching the login page then means a stale tab or a bookmark, and
  // showing a form that would email a second link is the wrong answer to either.
  useEffect(() => {
    if (status === 'signedIn') router.replace(next)
  }, [status, router, next])

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const wrong = firstComplaint()
    if (wrong !== undefined) {
      setComplaint(wrong)
      // Focus is the announcement: the field's description now carries the complaint, and a
      // screen reader reads a description when focus arrives. It also puts the cursor where
      // the work is, which is the whole of the sighted version.
      const field = wrong.field === 'email' ? emailField : passwordField
      field.current?.focus()
      return
    }
    setComplaint(undefined)
    setError(undefined)
    setStage('sending')
    try {
      if (method === 'link') {
        await sendMagicLink(email.trim(), next)
        setStage('sent')
        return
      }
      if (method === 'reset') {
        await resetPassword(email.trim())
        setStage('sent')
        return
      }
      if (method === 'register') {
        const { needsConfirmation } = await register(email.trim(), password, next)
        // With "Confirm email" off, Supabase hands back a session and the effect above
        // redirects; with it on, there is a mail to go and read. Only the second is a
        // screen, and it is the same "check your inbox" one the link uses.
        if (needsConfirmation) setStage('sent')
        return
      }
      await signInWithPassword(email.trim(), password)
      // The provider's subscription reports `signedIn` and the effect above redirects, so
      // the form stays in its sending state rather than flashing back to an empty one.
    } catch (cause) {
      setStage('form')
      setError(cause instanceof Error ? cause.message : 'Sign-in failed.')
    }
  }

  function chooseMethod(chosen: Method) {
    setMethod(chosen)
    setError(undefined)
    setPassword('')
    setComplaint(undefined)
    // Revealed is per visit to the field, not a preference: leaving it on would put the next
    // password on screen before it is typed, and the screen may be in front of someone.
    setRevealed(false)
  }

  if (status === 'disabled') {
    return (
      <AuthCard>
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
      </AuthCard>
    )
  }

  if (stage === 'sent') {
    return (
      <AuthCard>
        <div className="flex flex-col gap-2">
          <h1 className="m-0 text-[length:var(--text-lg)] font-semibold text-text-primary">
            Check your inbox
          </h1>
          <p className="m-0 [font:var(--type-body)] text-text-secondary">
            If <span className="font-medium text-text-primary">{email.trim()}</span> has an
            account, {method === 'reset' ? 'a link to set a new password' : 'a sign-in link'} is
            on its way. It expires in an hour and can be used once.
          </p>
        </div>
        <Button variant="ghost" fullWidth onClick={() => setStage('form')}>
          Use a different address
        </Button>
      </AuthCard>
    )
  }

  return (
    <AuthCard>
      <div className="flex flex-col gap-2">
        <h1 className="m-0 text-[length:var(--text-lg)] font-semibold text-text-primary">
          {HEADINGS[method]}
        </h1>
        <p className="m-0 [font:var(--type-body)] text-text-secondary">{BLURBS[method]}</p>
      </div>

      {error !== undefined && (
        <Notice tone="danger" title={FAILURE_TITLES[method]}>
          {error}
        </Notice>
      )}

      <form className="flex flex-col gap-4" onSubmit={onSubmit} noValidate>
        <Input
          ref={emailField}
          label="Work email"
          type="email"
          name="email"
          autoComplete="email"
          required
          autoFocus
          placeholder="sabine@example-it.de"
          error={complaint?.field === 'email' ? complaint.message : undefined}
          value={email}
          onChange={(event) => {
            setEmail(event.target.value)
            setComplaint(undefined)
          }}
          disabled={busy}
        />
        {needsPassword && (
          <Input
            ref={passwordField}
            label="Password"
            type={revealed ? 'text' : 'password'}
            name="password"
            autoComplete={registering ? 'new-password' : 'current-password'}
            hint={registering ? 'Choose one you do not use anywhere else.' : undefined}
            error={complaint?.field === 'password' ? complaint.message : undefined}
            required
            value={password}
            onChange={(event) => {
              setPassword(event.target.value)
              setComplaint(undefined)
            }}
            disabled={busy}
            trailing={
              <button
                type="button"
                onClick={() => setRevealed((shown) => !shown)}
                disabled={busy}
                // The glyph carries no text, so these two lines are the control's entire
                // name — with neither, it is announced as "button" and nothing else. They are
                // not redundant in the same way: `title` is the sentence a mouse hovers, and
                // `aria-label` wins the name computation, so it cannot be heard twice.
                aria-label={revealed ? 'Hide password' : 'Show password'}
                title={revealed ? 'Hide password' : 'Show password'}
                // 24 px of target in a 40 px box: SC 2.5.8's minimum, which a bare 16 px
                // glyph would miss.
                className="inline-flex size-6 shrink-0 items-center justify-center rounded-sm text-text-muted not-disabled:hover:text-text-primary"
              >
                <Icon name={revealed ? 'eyeOff' : 'eye'} size={16} />
              </button>
            }
          />
        )}
        {/*
          `aria-disabled`, not `disabled`. A disabled button is skipped by the tab order and
          swallows the click, so the incomplete form said nothing at all — no message to read
          and no control to reach. This one is announced as unavailable, still reachable, and
          answers a press by naming the field that is empty.
        */}
        <Button type="submit" fullWidth disabled={busy} aria-disabled={busy || incomplete}>
          {busy ? BUSY_LABELS[method] : SUBMIT_LABELS[method]}
        </Button>
      </form>

      <div className="flex flex-col gap-3 border-t border-border-subtle pt-5">
        {OTHER_METHODS[method].map(({ method: other, emphasis }) =>
          emphasis === 'button' ? (
            <Button
              key={other}
              type="button"
              variant="secondary"
              fullWidth
              disabled={busy}
              onClick={() => chooseMethod(other)}
            >
              {SWITCH_LABELS[other]}
            </Button>
          ) : (
            <button
              key={other}
              type="button"
              className="rounded-sm self-center [font:var(--type-body-sm)] text-text-secondary underline-offset-2 hover:text-text-primary hover:underline"
              onClick={() => chooseMethod(other)}
              disabled={busy}
            >
              {SWITCH_LABELS[other]}
            </button>
          )
        )}
      </div>
    </AuthCard>
  )
}

interface Complaint {
  readonly field: 'email' | 'password'
  readonly message: string
}

/**
 * Enough of an address to be worth sending: something, an `@`, something, a dot, something.
 * Deliberately not an RFC 5322 attempt — the only real test of an address is mail arriving
 * at it, and a stricter pattern here would refuse valid addresses for a guess. This catches
 * the typo the browser's own `type="email"` would have caught, which is what was lost.
 */
const EMAIL_SHAPE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

const HEADINGS: Readonly<Record<Method, string>> = {
  password: 'Sign in',
  link: 'Sign in',
  register: 'Create your account',
  reset: 'Reset your password',
}

const BLURBS: Readonly<Record<Method, string>> = {
  password: 'With the password on your account, or ask for a link instead.',
  link: 'We email you a link. Nothing to remember, and nothing to lose.',
  register: 'Your email and a password. Next you tell Crossbid about your company.',
  reset: 'We email you a link that lets you set a new one.',
}

const FAILURE_TITLES: Readonly<Record<Method, string>> = {
  password: 'Not signed in',
  link: 'The link could not be sent',
  register: 'Account not created',
  reset: 'The reset link could not be sent',
}

const SUBMIT_LABELS: Readonly<Record<Method, string>> = {
  password: 'Sign in',
  link: 'Email me a sign-in link',
  register: 'Create my account',
  reset: 'Email me a reset link',
}

const BUSY_LABELS: Readonly<Record<Method, string>> = {
  password: 'Signing in…',
  link: 'Sending…',
  register: 'Creating…',
  reset: 'Sending…',
}

/** How each way in is offered from the others. Phrased as the action, not as the method. */
const SWITCH_LABELS: Readonly<Record<Method, string>> = {
  password: 'I already have an account',
  link: 'Email me a sign-in link instead',
  register: 'Create an account', // the secondary button on the sign-in screen
  reset: 'Forgotten your password?',
}

interface Alternative {
  readonly method: Method
  /** `button` for a real destination, `link` for a correction. See `OTHER_METHODS`. */
  readonly emphasis: 'button' | 'link'
}

/**
 * What the footer offers from each screen, and with how much weight.
 *
 * **Creating an account is a button, and going back to sign-in is not.** From the sign-in
 * screen, registering is a different destination a first-time visitor is genuinely choosing
 * between — a text link makes the one action a new bidder needs the least visible thing on
 * the page. From the registration screen, "I already have an account" is a correction of a
 * wrong turn, and giving it equal weight would leave two buttons competing where one is
 * plainly the point of the screen. The asymmetry is the intent, not an oversight.
 *
 * Sign-up is not offered from the link screen at all: the link already creates the account
 * when there is none, so a second route to the same place would be a choice without a
 * difference.
 */
const OTHER_METHODS: Readonly<Record<Method, readonly Alternative[]>> = {
  password: [
    { method: 'register', emphasis: 'button' },
    { method: 'link', emphasis: 'link' },
    { method: 'reset', emphasis: 'link' },
  ],
  link: [{ method: 'password', emphasis: 'link' }],
  register: [{ method: 'password', emphasis: 'link' }],
  // Only back to the password screen: offering a magic link here would answer "I forgot my
  // password" with "then do not use one", which is a fair answer to a different question.
  reset: [{ method: 'password', emphasis: 'link' }],
}
