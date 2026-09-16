/**
 * `RequireSession` over a real `SessionProvider` — the two ways the provider used to stay
 * `loading` for ever (S4.1.1; found 2026-09-16).
 *
 * The report that started this blamed the bid workspace for "sitting at 'Loading…'" after a
 * failed fetch. The workspace was fine; the word was this guard's, and it was on screen
 * because the provider's bootstrap had no `catch`: when the dynamic import of the auth client
 * rejected — a chunk the dev server had stopped serving — the rejection was an uncaught error
 * in the console and `status` never left `loading`. The second way was quieter still: a
 * `getSession()` that neither resolved nor rejected, which supabase-js does when a token
 * refresh hangs at the transport. Neither showed a sentence or a button.
 *
 * Both are driven here through the real provider, with only `getSupabaseClient` replaced:
 * the first test hands it a rejection, the second a client whose `getSession` never answers
 * and a fake clock to walk up to the deadline. `next/navigation` is stubbed because the
 * guard redirects through `useRouter` — and *not* redirecting is one of the claims: a
 * session that could not be read is not a session that is absent, and bouncing to the login
 * page would hide the cause behind a form that cannot work either.
 */
import type { Session, SupabaseClient } from '@supabase/supabase-js'
import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { getSupabaseClient } from '@/lib/supabase'

import { RequireSession } from './require-session'
import { SESSION_READ_DEADLINE_MS, SessionProvider } from './session-provider'

const PATHNAME = '/bids/abc'

const { replace } = vi.hoisted(() => ({ replace: vi.fn() }))

// The provider only looks for a session when the build says sign-in is on.
vi.mock('@/lib/auth-mode', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/auth-mode')>()
  return { ...actual, isAuthEnabled: true }
})

vi.mock('@/lib/supabase', () => ({ getSupabaseClient: vi.fn() }))

vi.mock('next/navigation', async (importOriginal) => {
  const actual = await importOriginal<typeof import('next/navigation')>()
  return { ...actual, useRouter: () => ({ replace }), usePathname: () => PATHNAME }
})

/** Enough of a client for the provider's bootstrap: a subscription and one `getSession`. */
function fakeClient(
  getSession: () => Promise<{ data: { session: Session | null } }>
): SupabaseClient {
  const client = {
    auth: {
      onAuthStateChange: () => ({ data: { subscription: { unsubscribe: () => undefined } } }),
      getSession,
    },
  }
  // The provider touches nothing else on the client; the cast is the price of not building
  // the other hundred members it never reads.
  return client as unknown as SupabaseClient
}

/** Advance the fake clock inside React's `act`, so every state update it causes is flushed. */
async function elapse(ms: number): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

function renderGuardedPage() {
  return render(
    <SessionProvider>
      <RequireSession>
        <p>The page</p>
      </RequireSession>
    </SessionProvider>
  )
}

beforeEach(() => {
  vi.mocked(getSupabaseClient).mockReset()
  replace.mockReset()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('RequireSession', () => {
  test('when the auth client cannot be loaded, says so and offers a way forward', async () => {
    vi.mocked(getSupabaseClient).mockRejectedValue(new Error('Loading chunk 4711 failed.'))

    renderGuardedPage()

    const notice = await screen.findByRole('alert')
    expect(notice).toHaveTextContent('Your session could not be checked')
    expect(notice).toHaveTextContent('reloading fetches the current version')
    expect(screen.getByRole('button', { name: 'Reload the page' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Sign in' })).toHaveAttribute(
      'href',
      `/login?next=${encodeURIComponent(PATHNAME)}`
    )
    expect(screen.queryByText('The page')).not.toBeInTheDocument()
    expect(replace).not.toHaveBeenCalled()
  })

  test('when getSession never answers, stops waiting at the deadline', async () => {
    vi.useFakeTimers()
    vi.mocked(getSupabaseClient).mockResolvedValue(
      fakeClient(() => new Promise(() => undefined))
    )

    renderGuardedPage()
    await elapse(0)

    expect(screen.getByRole('status')).toHaveTextContent('Loading…')
    await elapse(SESSION_READ_DEADLINE_MS - 1)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()

    await elapse(1)
    expect(screen.getByRole('alert')).toHaveTextContent(
      `took longer than ${SESSION_READ_DEADLINE_MS / 1000} seconds`
    )
    expect(screen.getByRole('button', { name: 'Reload the page' })).toBeInTheDocument()
    expect(screen.queryByText('The page')).not.toBeInTheDocument()
    expect(replace).not.toHaveBeenCalled()
  })

  test('a session that arrives in time renders the page, and the deadline never fires', async () => {
    vi.useFakeTimers()
    // The provider reads `access_token` and `user.email`; the rest of a Session is never touched.
    const session = { access_token: 'token', user: { email: 'bidder@example.com' } }
    vi.mocked(getSupabaseClient).mockResolvedValue(
      fakeClient(() => Promise.resolve({ data: { session: session as unknown as Session } }))
    )

    renderGuardedPage()
    await elapse(0)

    expect(screen.getByText('The page')).toBeInTheDocument()
    await elapse(SESSION_READ_DEADLINE_MS)
    expect(screen.getByText('The page')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
