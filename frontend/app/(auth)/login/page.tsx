import type { Metadata } from 'next'
import { Suspense } from 'react'

import { SignInCard } from '@/components/auth/sign-in-card'

export const metadata: Metadata = {
  title: 'Sign in — CrossBid',
  description: 'Sign in to CrossBid with a link sent to your email.',
}

/**
 * The login page (S4.1.1). Outside the `(app)` group, so it renders without the shell.
 *
 * The `Suspense` boundary is what `useSearchParams` needs to read `?next=` without forcing
 * the whole page to render on every request.
 */
export default function LoginPage() {
  return (
    <Suspense>
      <SignInCard />
    </Suspense>
  )
}
