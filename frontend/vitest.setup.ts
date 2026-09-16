/**
 * Runs before every test file. Two jobs: the jest-dom matchers (`toBeInTheDocument`,
 * `toHaveAccessibleDescription`, ...) on Vitest's `expect`, and the one Next.js stub the
 * component tests cannot do without.
 *
 * Every stub here says why it exists. A stub nobody can justify is how a test keeps passing
 * against a component that stopped working.
 */
import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

// Testing Library only unmounts between tests on its own when the runner exposes globals,
// and `globals` is off here so that `describe`/`test` stay explicit imports. Without this,
// a second render in the same file would find the first test's DOM still standing.
afterEach(() => {
  cleanup()
})

// `useSearchParams` reads Next's router context, and outside the App Router that context
// is `null`: the hook returns `null` and `.get('next')` throws before the form has rendered
// a single field. The stub answers "no query string" — the case every test here is about.
// Everything else in `next/navigation` is left real, so a component that starts using
// `useRouter` or `usePathname` fails loudly here rather than passing against a fake.
vi.mock('next/navigation', async (importOriginal) => {
  const actual = await importOriginal<typeof import('next/navigation')>()
  return {
    ...actual,
    useSearchParams: () => new URLSearchParams(),
  }
})
