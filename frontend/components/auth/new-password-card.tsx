'use client'

/**
 * Where a recovery link ends up: set a new password, then go on to the app.
 *
 * **The session is the proof, and it has already happened by the time this renders.** A
 * recovery link is an ordinary PKCE arrival — `/auth/callback` exchanges its code exactly
 * as it does for a magic link, then forwards here. So this screen never sees a token and
 * never validates one; `updateUser({ password })` is refused by Supabase without a session,
 * which makes "was this link real?" a question already answered upstream.
 *
 * **Three states, none of them a spinner that waits forever.** Signed in is the form.
 * Signed out means the link expired, was already used, or was opened in a browser that
 * never started the reset — one message, because a visitor can do the same thing about all
 * three, and because saying which would confirm an address to someone holding a stale link.
 * `loading` is the brief moment before the provider has read storage, and it says so.
 *
 * **Both fields are typed, not one.** A password set from a mistyped string locks the
 * account out of the very flow that would fix it, and the person would not find out until
 * their next sign-in. The confirmation is compared here rather than on submit so the
 * mismatch is visible while the second field still has focus.
 */
import { useRouter } from 'next/navigation'
import { useState, type FormEvent } from 'react'

import { AuthCard } from '@/components/auth/auth-card'
import { useSession } from '@/components/auth/session-provider'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Notice } from '@/components/ui/notice'
import { DEFAULT_AFTER_SIGN_IN } from '@/lib/safe-next-path'

/** Supabase's own floor. Stated here so the form can refuse before the round trip. */
const MIN_PASSWORD_LENGTH = 6

export function NewPasswordCard() {
  const { status, updatePassword } = useSession()
  const router = useRouter()
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | undefined>(undefined)

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(undefined)
    setSaving(true)
    try {
      await updatePassword(password)
      // Signed in already — the recovery session is a session. Straight to the app rather
      // than back to a sign-in form that would ask for the password just set.
      router.replace(DEFAULT_AFTER_SIGN_IN)
    } catch (cause) {
      setSaving(false)
      setError(cause instanceof Error ? cause.message : 'The password was not changed.')
    }
  }

  if (status === 'loading') {
    return (
      <AuthCard>
        <p className="m-0 [font:var(--type-body)] text-text-secondary">Checking your link…</p>
      </AuthCard>
    )
  }

  if (status !== 'signedIn') {
    return (
      <AuthCard>
        <Notice tone="danger" title="This link cannot be used">
          A reset link works once and expires after an hour, and it has to be opened in a
          browser that can reach your session. Ask for a new one and open it from the same
          device.
        </Notice>
        <Button asChild variant="secondary" fullWidth>
          <a href="/login">Back to sign in</a>
        </Button>
      </AuthCard>
    )
  }

  const tooShort = password !== '' && password.length < MIN_PASSWORD_LENGTH
  const mismatched = confirmation !== '' && confirmation !== password
  const incomplete =
    password.length < MIN_PASSWORD_LENGTH || confirmation === '' || confirmation !== password

  return (
    <AuthCard>
      <div className="flex flex-col gap-2">
        <h1 className="m-0 text-[length:var(--text-lg)] font-semibold text-text-primary">
          Set a new password
        </h1>
        <p className="m-0 [font:var(--type-body)] text-text-secondary">
          This replaces the old one everywhere. You stay signed in on this device.
        </p>
      </div>

      {error !== undefined && (
        <Notice tone="danger" title="The password was not changed">
          {error}
        </Notice>
      )}

      <form className="flex flex-col gap-4" onSubmit={onSubmit} noValidate>
        <Input
          label="New password"
          type="password"
          name="password"
          autoComplete="new-password"
          required
          autoFocus
          hint={`At least ${MIN_PASSWORD_LENGTH} characters. Choose one you do not use anywhere else.`}
          error={tooShort ? `Use at least ${MIN_PASSWORD_LENGTH} characters.` : undefined}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          disabled={saving}
        />
        <Input
          label="New password again"
          type="password"
          name="confirmation"
          autoComplete="new-password"
          required
          error={mismatched ? 'The two passwords do not match.' : undefined}
          value={confirmation}
          onChange={(event) => setConfirmation(event.target.value)}
          disabled={saving}
        />
        <Button type="submit" fullWidth disabled={saving || incomplete}>
          {saving ? 'Saving…' : 'Save my new password'}
        </Button>
      </form>
    </AuthCard>
  )
}
