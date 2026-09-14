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
 */
import type { Session } from '@supabase/supabase-js'
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

import { setAccessToken } from '@/lib/api-client'
import { isAuthEnabled } from '@/lib/auth-mode'
import { authCallbackUrl, getSupabaseClient } from '@/lib/supabase'

export type SessionStatus = 'loading' | 'signedIn' | 'signedOut' | 'disabled'

export interface SessionState {
  readonly status: SessionStatus
  /** The signed-in user's email, or `undefined`. Shown in the sidebar, never sent anywhere. */
  readonly email: string | undefined
  /**
   * Ask Supabase to email a magic link. Resolves when the mail has been accepted for
   * sending. `next` is the path to land on afterwards, carried through the mailbox.
   *
   * This is also the sign-*up* path: `signInWithOtp` creates the user when there is none,
   * so a first-time bidder needs no separate form and no password to invent.
   */
  readonly sendMagicLink: (email: string, next?: string) => Promise<void>
  /**
   * Sign in with a password (ADR-0038). Resolves once the session exists; the subscription
   * above then reports `signedIn` and the screen redirects, exactly as it does for a link.
   */
  readonly signInWithPassword: (email: string, password: string) => Promise<void>
  readonly signOut: () => Promise<void>
}

const SessionContext = createContext<SessionState | undefined>(undefined)

export function SessionProvider({ children }: Readonly<{ children: React.ReactNode }>) {
  const [session, setSession] = useState<Session | null>(null)
  const [status, setStatus] = useState<SessionStatus>(isAuthEnabled ? 'loading' : 'disabled')

  useEffect(() => {
    let active = true
    let unsubscribe: (() => void) | undefined

    const adopt = (next: Session | null) => {
      if (!active) return
      setSession(next)
      setStatus(next === null ? 'signedOut' : 'signedIn')
      setAccessToken(next?.access_token)
    }

    void (async () => {
      const supabase = await getSupabaseClient()
      if (supabase === null || !active) return
      // Subscribed before the first read, not after: the magic-link exchange can complete
      // while `getSession` is still in flight, and a listener attached afterwards would
      // miss the one event that matters on this page.
      const { data } = supabase.auth.onAuthStateChange((_event, next) => adopt(next))
      unsubscribe = () => data.subscription.unsubscribe()
      const { data: current } = await supabase.auth.getSession()
      adopt(current.session)
    })()

    return () => {
      active = false
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

  const signOut = useCallback(async () => {
    const supabase = await getSupabaseClient()
    if (supabase === null) return
    await supabase.auth.signOut()
    setAccessToken(undefined)
  }, [])

  const value = useMemo<SessionState>(
    () => ({
      status,
      email: session?.user.email,
      sendMagicLink,
      signInWithPassword,
      signOut,
    }),
    [status, session, sendMagicLink, signInWithPassword, signOut]
  )

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

export function useSession(): SessionState {
  const value = useContext(SessionContext)
  if (value === undefined) {
    throw new Error('useSession must be used inside <SessionProvider>')
  }
  return value
}
