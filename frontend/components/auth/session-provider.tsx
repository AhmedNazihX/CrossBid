'use client'

/**
 * Who is signed in, for the whole app (story S4.1.1).
 *
 * One provider at the root holds the Supabase session and keeps three things in step:
 * the React tree, `api-client`'s bearer token, and Supabase's own refresh timer. It is
 * the only place `getSupabaseClient()` is subscribed to, so a token that has just been
 * refreshed reaches the next API call without any screen knowing that happened.
 *
 * **`status` is three-valued on purpose.** `loading` is not `signedOut`: on the first
 * paint the session is still being read out of `localStorage`, and a guard that treated
 * the two the same would bounce every returning visitor to the login page before their
 * session had loaded. Screens wait for `loading` to end; `RequireSession` is the one that
 * does it for the whole `(app)` group.
 *
 * On the dev bridge (`isAuthEnabled === false`) there is no client to subscribe to, and
 * the provider reports `disabled` — every screen then renders exactly as it did before
 * this story, with `X-Dev-Company` doing the work.
 *
 * **`failed` exists because `loading` used to be a state with no exit.** The bootstrap
 * below was a bare `void (async () => …)()`: when the dynamic import of the auth client
 * rejected — a `next dev` server recompiled while the tab was open, so the chunk it asked
 * for was gone — the rejection went to the console as an uncaught error and `status`
 * stayed `loading`. Every guarded route then showed `RequireSession`'s "Loading…" with no
 * message, no button and no end, and nothing but DevTools said why (reproduced 2026-09-16
 * while chasing a report that blamed the bid workspace, which was in fact fine). The same
 * held when `getSession()` simply never answered: supabase-js retries a token refresh for
 * up to 30 s and then gives up, but a refresh that hangs at the transport is never retried
 * and never rejects. So the bootstrap now has a `catch` and a deadline, both of which land
 * on `failed` with a sentence in `problem`, and `RequireSession` draws that as an error
 * with a way forward. A session that arrives late still wins: `adopt` overwrites `failed`.
 */
import type { Session } from '@supabase/supabase-js'
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

import { setAccessToken } from '@/lib/api-client'
import { isAuthEnabled } from '@/lib/auth-mode'
import { PASSWORD_RESET_PATH } from '@/lib/safe-next-path'
import { authCallbackUrl, getSupabaseClient } from '@/lib/supabase'

export type SessionStatus = 'loading' | 'signedIn' | 'signedOut' | 'disabled' | 'failed'

/**
 * How long the first read of the session may take before the shell stops waiting.
 *
 * Longer than supabase-js's own 30 s refresh-retry window (`AUTO_REFRESH_TICK_DURATION_MS`)
 * on purpose: a refresh that *fails* inside that window ends in `signedOut` and a redirect to
 * sign in, which is the right answer, and a deadline shorter than the window would show an
 * error card first and then snatch it away. Only a read that has neither succeeded nor
 * failed by then is a hang, and that is the one this catches.
 */
export const SESSION_READ_DEADLINE_MS = 45_000

export interface SessionState {
  readonly status: SessionStatus
  /** Why `status` is `failed`, as one sentence for the screen; `undefined` otherwise. */
  readonly problem: string | undefined
  /** The signed-in user's email, or `undefined`. Shown in the sidebar, never sent anywhere. */
  readonly email: string | undefined
  /**
   * Ask Supabase to email a magic link. Resolves when the mail has been accepted for
   * sending. `next` is the path to land on afterwards, carried through the mailbox.
   *
   * This is also the sign-*up* path: `signInWithOtp` creates the user when there is none,
   * so a first-time bidder needs no separate form and no password to invent.
   *
   * `shouldCreateUser` is left at its default of `true` deliberately, and the trade is
   * known (ADR-0053). Setting it to `false` makes an unknown address return an error where
   * a known one succeeds, which is a user-enumeration oracle — and one Supabase cannot
   * currently close (supabase/auth#1955, open since November 2024). Creating the account is
   * the answer that reveals nothing. The cost is that a typo registers rather than failing,
   * which is why `resetPassword` below is the enumeration-safe path it is.
   */
  readonly sendMagicLink: (email: string, next?: string) => Promise<void>
  /**
   * Sign in with a password (ADR-0038). Resolves once the session exists; the subscription
   * above then reports `signedIn` and the screen redirects, exactly as it does for a link.
   */
  readonly signInWithPassword: (email: string, password: string) => Promise<void>
  /**
   * Register with a password, answering whether a confirmation email was sent (ADR-0039).
   *
   * Which of the two happens is the project's "Confirm email" setting, not ours: with it
   * off, Supabase returns a session and the screen redirects; with it on, it returns a
   * user and no session, and the person has to go to their inbox. The caller cannot know
   * in advance, so it is told which happened rather than guessing.
   */
  /**
   * Email a password-reset link. Resolves whether or not the address has an account.
   *
   * **This one genuinely cannot leak, and that is Supabase's doing, not ours.**
   * `resetPasswordForEmail` returns without error for an address it has never seen and
   * simply sends nothing — so unlike `shouldCreateUser: false`, there is no answer here to
   * tell a known address from an unknown one. The screen says "if that address has an
   * account" because that is precisely as much as anyone, including us, can know.
   *
   * The link lands on `/auth/callback`, which exchanges the code like any other arrival and
   * then forwards to `/auth/new-password`. Recovery is an ordinary session: what makes it a
   * reset is only that the next thing the screen does is `updatePassword`.
   */
  readonly resetPassword: (email: string) => Promise<void>
  /**
   * Set a new password on the signed-in account (`PASSWORD_RESET_PATH`'s form).
   *
   * Requires a session, which the recovery link has just provided. It is not reset-only —
   * the same call changes a password for anyone already signed in — so nothing here checks
   * *how* the session was obtained; Supabase refuses the call without one.
   */
  readonly updatePassword: (password: string) => Promise<void>
  readonly register: (
    email: string,
    password: string,
    next?: string
  ) => Promise<{ readonly needsConfirmation: boolean }>
  readonly signOut: () => Promise<void>
}

const SessionContext = createContext<SessionState | undefined>(undefined)

export function SessionProvider({ children }: Readonly<{ children: React.ReactNode }>) {
  const [session, setSession] = useState<Session | null>(null)
  const [status, setStatus] = useState<SessionStatus>(isAuthEnabled ? 'loading' : 'disabled')

  const [problem, setProblem] = useState<string | undefined>(undefined)

  useEffect(() => {
    if (!isAuthEnabled) return
    let active = true
    let unsubscribe: (() => void) | undefined

    // `deadline` is declared below, after the closures that clear it; none of them runs
    // before the timer exists.
    const settle = () => clearTimeout(deadline)
    const adopt = (next: Session | null) => {
      if (!active) return
      settle()
      setSession(next)
      setProblem(undefined)
      setStatus(next === null ? 'signedOut' : 'signedIn')
      setAccessToken(next?.access_token)
    }
    const fail = (sentence: string) => {
      if (!active) return
      settle()
      setProblem(sentence)
      setStatus('failed')
    }

    const deadline = setTimeout(() => fail(describeDeadline()), SESSION_READ_DEADLINE_MS)
    void (async () => {
      try {
        const supabase = await getSupabaseClient()
        if (supabase === null || !active) return
        // Subscribed before the first read, not after: the magic-link exchange can complete
        // while `getSession` is still in flight, and a listener attached afterwards would
        // miss the one event that matters on this page.
        const { data } = supabase.auth.onAuthStateChange((_event, next) => adopt(next))
        unsubscribe = () => data.subscription.unsubscribe()
        const { data: current } = await supabase.auth.getSession()
        adopt(current.session)
      } catch (cause: unknown) {
        fail(describeBootstrapFailure(cause))
      }
    })()

    return () => {
      active = false
      settle()
      unsubscribe?.()
    }
  }, [])

  const sendMagicLink = useCallback(async (email: string, next?: string) => {
    const supabase = await getSupabaseClient()
    if (supabase === null) throw new Error('Sign-in is not configured for this build.')
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: authCallbackUrl(next) },
    })
    if (error !== null) throw error
  }, [])

  const signInWithPassword = useCallback(async (email: string, password: string) => {
    const supabase = await getSupabaseClient()
    if (supabase === null) throw new Error('Sign-in is not configured for this build.')
    const { error } = await supabase.auth.signInWithPassword({ email, password })
    if (error !== null) throw error
  }, [])

  const register = useCallback(async (email: string, password: string, next?: string) => {
    const supabase = await getSupabaseClient()
    if (supabase === null) throw new Error('Sign-in is not configured for this build.')
    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: { emailRedirectTo: authCallbackUrl(next) },
    })
    if (error !== null) throw error
    return { needsConfirmation: data.session === null }
  }, [])

  const resetPassword = useCallback(async (email: string) => {
    const supabase = await getSupabaseClient()
    if (supabase === null) throw new Error('Sign-in is not configured for this build.')
    const { error } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: authCallbackUrl(PASSWORD_RESET_PATH),
    })
    if (error !== null) throw error
  }, [])

  const updatePassword = useCallback(async (password: string) => {
    const supabase = await getSupabaseClient()
    if (supabase === null) throw new Error('Sign-in is not configured for this build.')
    const { error } = await supabase.auth.updateUser({ password })
    if (error !== null) throw error
  }, [])

  const signOut = useCallback(async () => {
    const supabase = await getSupabaseClient()
    if (supabase === null) return
    await supabase.auth.signOut()
    setAccessToken(undefined)
  }, [])

  const value = useMemo<SessionState>(
    () => ({
      status,
      problem,
      email: session?.user.email,
      sendMagicLink,
      signInWithPassword,
      register,
      resetPassword,
      updatePassword,
      signOut,
    }),
    [
      status,
      problem,
      session,
      sendMagicLink,
      signInWithPassword,
      register,
      resetPassword,
      updatePassword,
      signOut,
    ]
  )

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

function describeDeadline(): string {
  return (
    `Checking your session took longer than ${SESSION_READ_DEADLINE_MS / 1000} seconds. ` +
    'The sign-in service may be unreachable from this network.'
  )
}

/**
 * The one cause seen in the wild gets its own sentence. A chunk that fails to load is a
 * page from a build the server no longer serves — the dev server recompiled, or a deploy
 * went out — and the fix is a reload, which the card offers. Anything else is named as it
 * came, because the next cause will be one nobody has seen yet.
 */
function describeBootstrapFailure(cause: unknown): string {
  const message = cause instanceof Error ? cause.message : ''
  const isStaleBuild =
    (cause instanceof Error && cause.name === 'ChunkLoadError') || /chunk/i.test(message)
  if (isStaleBuild) {
    return (
      'The sign-in code could not be loaded. This usually means the app was updated while ' +
      'this page was open; reloading fetches the current version.'
    )
  }
  return message.length > 0
    ? `Your session could not be checked: ${message}`
    : 'Your session could not be checked.'
}

export function useSession(): SessionState {
  const value = useContext(SessionContext)
  if (value === undefined) {
    throw new Error('useSession must be used inside <SessionProvider>')
  }
  return value
}
