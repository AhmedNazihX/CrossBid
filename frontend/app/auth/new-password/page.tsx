import type { Metadata } from 'next'

import { NewPasswordCard } from '@/components/auth/new-password-card'

export const metadata: Metadata = {
  title: 'Set a new password — CrossBid',
  description: 'Choose a new password for your CrossBid account.',
}

/**
 * Where `/auth/callback` forwards a recovery arrival (`PASSWORD_RESET_PATH`).
 *
 * Beside the callback rather than inside `(app)`, for the same reason the callback is: the
 * shell's `RequireCompany` would send a bidder with a valid recovery session to the company
 * form before they had set the password they came here to set.
 *
 * No `Suspense` boundary — unlike the login page this reads no search params. The code was
 * spent by the callback and the session is what carries the proof.
 */
export default function NewPasswordPage() {
  return <NewPasswordCard />
}
