/**
 * `RequireCompany` — the wait that had no end (S4.2.1; found 2026-09-16).
 *
 * The guard's `catch` was sound: a `/companies/me` that failed let the screen render and
 * report its own trouble. A `/companies/me` that never *settled* reached neither branch, and
 * every route under the shell showed "Loading…" for as long as the tab was open. The first
 * test drives exactly that — `loadProfile` rejects only when its signal is aborted, the way
 * `fetch` does — and walks a fake clock up to the deadline. The others pin the two answers
 * that were already right, so the deadline cannot be "fixed" by dropping the check.
 *
 * `useSession` is replaced because the guard reads one field of it, and `next/navigation`
 * because the redirect goes through `useRouter` — which is what the second test asserts on.
 */
import { act, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { loadProfile } from '@/lib/companies'

import { COMPANY_CHECK_DEADLINE_MS, RequireCompany } from './require-company'

const PATHNAME = '/bids/abc'

const { replace } = vi.hoisted(() => ({ replace: vi.fn() }))

vi.mock('@/lib/companies', () => ({ loadProfile: vi.fn() }))

vi.mock('@/components/auth/session-provider', () => ({
  useSession: () => ({ status: 'signedIn' }),
}))

vi.mock('next/navigation', async (importOriginal) => {
  const actual = await importOriginal<typeof import('next/navigation')>()
  return { ...actual, useRouter: () => ({ replace }), usePathname: () => PATHNAME }
})

type Loaded = Awaited<ReturnType<typeof loadProfile>>

/** A request that never answers — until it is aborted, when it rejects as `fetch` would. */
function neverAnswers(signal?: AbortSignal): Promise<Loaded> {
  return new Promise((_resolve, reject) => {
    signal?.addEventListener('abort', () => reject(signal.reason as unknown))
  })
}

/** Advance the fake clock inside React's `act`, so every state update it causes is flushed. */
async function elapse(ms: number): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

function renderGuardedPage() {
  return render(
    <RequireCompany>
      <p>The page</p>
    </RequireCompany>
  )
}

beforeEach(() => {
  vi.mocked(loadProfile).mockReset()
  replace.mockReset()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('RequireCompany', () => {
  test('when /companies/me never answers, lets the page render at the deadline', async () => {
    vi.useFakeTimers()
    vi.mocked(loadProfile).mockImplementation(neverAnswers)

    renderGuardedPage()
    await elapse(0)

    expect(screen.getByRole('status')).toHaveTextContent('Loading…')
    expect(screen.queryByText('The page')).not.toBeInTheDocument()

    await elapse(COMPANY_CHECK_DEADLINE_MS)
    expect(screen.getByText('The page')).toBeInTheDocument()
    expect(replace).not.toHaveBeenCalled()
  })

  test('sends an account with no company to the form, carrying the path it asked for', async () => {
    vi.mocked(loadProfile).mockResolvedValue({ profile: undefined })

    renderGuardedPage()

    await waitFor(() =>
      expect(replace).toHaveBeenCalledWith(`/company?next=${encodeURIComponent(PATHNAME)}`)
    )
  })

  test('renders the page once a company is found, without redirecting', async () => {
    const profile = { name: 'Beispiel IT Services GmbH' } as unknown as NonNullable<
      Loaded['profile']
    >
    vi.mocked(loadProfile).mockResolvedValue({ profile })

    renderGuardedPage()

    expect(await screen.findByText('The page')).toBeInTheDocument()
    expect(replace).not.toHaveBeenCalled()
  })
})
