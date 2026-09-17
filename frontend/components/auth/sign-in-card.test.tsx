/**
 * The sign-in form's three affordances — finding L2 of the 2026-09-15 audit (S4.1.1).
 *
 * All three are about a bidder who cannot get in and is told nothing about why:
 *
 * 1. **The password could not be revealed.** On a phone, typing a strong password blind is
 *    the commonest way a sign-in fails, and the screen offered no way to check it.
 * 2. **An incomplete form said nothing.** The submit button was `disabled` while a field was
 *    empty, so pressing it did nothing at all — no message, and nothing for a screen reader
 *    to announce. A disabled control is also skipped by keyboard navigation, so the one
 *    element that would explain the state could not even be reached.
 * 3. **The form turned the browser's own email check off** with `noValidate` and put nothing
 *    in its place, so `sabine` was submitted as an address.
 *
 * These are jsdom tests and not browser ones deliberately: every claim here is about what an
 * element *is* — its `type`, its accessible description, where focus went, whether a call was
 * made — and none is about paint, cascade or layout, which is where `e2e/` earns its cost
 * (ADR-0092). It is also the only way to reach this screen at all under test: the Playwright
 * suite's server runs `NEXT_PUBLIC_AUTH_MODE=dev`, where `/login` renders "this build does
 * not sign people in" and has no form (ADR-0094 records the same obstacle for L1).
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { useSession } from '@/components/auth/session-provider'

import { SignInCard } from './sign-in-card'

const { replace } = vi.hoisted(() => ({ replace: vi.fn() }))

vi.mock('next/navigation', async (importOriginal) => {
  const actual = await importOriginal<typeof import('next/navigation')>()
  return {
    ...actual,
    useRouter: () => ({ replace }),
    useSearchParams: () => new URLSearchParams(),
  }
})

vi.mock('@/components/auth/session-provider', () => ({ useSession: vi.fn() }))

const signInWithPassword = vi.fn<(email: string, password: string) => Promise<void>>()

beforeEach(() => {
  vi.clearAllMocks()
  signInWithPassword.mockResolvedValue(undefined)
  vi.mocked(useSession).mockReturnValue({
    status: 'signedOut',
    session: null,
    signInWithPassword,
    sendMagicLink: vi.fn().mockResolvedValue(undefined),
    register: vi.fn().mockResolvedValue({ needsConfirmation: false }),
    resetPassword: vi.fn().mockResolvedValue(undefined),
    signOut: vi.fn().mockResolvedValue(undefined),
  } as unknown as ReturnType<typeof useSession>)
})

describe('Sign in — showing the password', () => {
  test('the password is masked until Show is pressed, and masked again after Hide', async () => {
    const user = userEvent.setup()
    render(<SignInCard />)

    const password = screen.getByLabelText('Password')
    expect(password).toHaveAttribute('type', 'password')

    await user.click(screen.getByRole('button', { name: /show password/i }))
    expect(password).toHaveAttribute('type', 'text')

    await user.click(screen.getByRole('button', { name: /hide password/i }))
    expect(password).toHaveAttribute('type', 'password')
  })

  test('the reveal control is a glyph, so the label carries its whole name', () => {
    render(<SignInCard />)

    const toggle = screen.getByRole('button', { name: 'Show password' })
    // Nothing visible to fall back on, which is the cost of choosing an icon over the word.
    // Measured with both the label and the title removed, because with only the `aria-label`
    // gone the `title` still names the control — which the first draft of this comment had
    // wrong, and which the revert run is for.
    expect(toggle.textContent).toBe('')
    expect(toggle).toHaveAccessibleName('Show password')
  })

  test('the toggle does not submit the form it sits inside', async () => {
    const user = userEvent.setup()
    render(<SignInCard />)

    await user.type(screen.getByLabelText('Work email'), 'sabine@example-it.de')
    await user.type(screen.getByLabelText('Password'), 'a-long-passphrase')
    await user.click(screen.getByRole('button', { name: /show password/i }))

    expect(signInWithPassword).not.toHaveBeenCalled()
  })

  test('switching to another method does not leave a password on screen', async () => {
    const user = userEvent.setup()
    render(<SignInCard />)

    await user.type(screen.getByLabelText('Password'), 'a-long-passphrase')
    await user.click(screen.getByRole('button', { name: /show password/i }))
    // Away to a method with no password field, and back.
    await user.click(screen.getByRole('button', { name: /email me a sign-in link instead/i }))
    await user.click(screen.getByRole('button', { name: /i already have an account/i }))

    expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password')
  })
})

describe('Sign in — what an empty or malformed submit says', () => {
  test('the submit button can be reached and pressed while the form is incomplete', async () => {
    render(<SignInCard />)

    const submit = screen.getByRole('button', { name: 'Sign in' })
    // `disabled` would take it out of the tab order entirely, so the one element that could
    // explain the state is the one a keyboard cannot reach.
    expect(submit).not.toBeDisabled()
    expect(submit).toHaveAttribute('aria-disabled', 'true')
  })

  test('an empty submit names the email field, focuses it, and sends nothing', async () => {
    const user = userEvent.setup()
    render(<SignInCard />)

    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    const email = screen.getByLabelText('Work email')
    expect(email).toHaveAccessibleDescription(/enter your work email/i)
    expect(email).toHaveFocus()
    expect(signInWithPassword).not.toHaveBeenCalled()
  })

  test('an address with no password names the password field, not the email', async () => {
    const user = userEvent.setup()
    render(<SignInCard />)

    await user.type(screen.getByLabelText('Work email'), 'sabine@example-it.de')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    const password = screen.getByLabelText('Password')
    expect(password).toHaveAccessibleDescription(/enter your password/i)
    expect(password).toHaveFocus()
    expect(signInWithPassword).not.toHaveBeenCalled()
  })

  test('an address that is not one is refused here, since the browser was told not to', async () => {
    const user = userEvent.setup()
    render(<SignInCard />)

    await user.type(screen.getByLabelText('Work email'), 'sabine')
    await user.type(screen.getByLabelText('Password'), 'a-long-passphrase')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(screen.getByLabelText('Work email')).toHaveAccessibleDescription(
      /does not look like an email address/i
    )
    expect(signInWithPassword).not.toHaveBeenCalled()
  })

  test('the complaint clears as soon as the field is typed into', async () => {
    const user = userEvent.setup()
    render(<SignInCard />)

    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    // Seen present first: an assertion that a message is *gone* passes against a build that
    // never showed one, which is ADR-0063's shape and has already been shipped twice here.
    expect(screen.getByLabelText('Work email')).toHaveAccessibleDescription(
      /enter your work email/i
    )

    await user.type(screen.getByLabelText('Work email'), 's')

    expect(screen.getByLabelText('Work email')).not.toHaveAccessibleDescription(
      /enter your work email/i
    )
  })

  test('a complete form still signs in', async () => {
    const user = userEvent.setup()
    render(<SignInCard />)

    await user.type(screen.getByLabelText('Work email'), '  sabine@example-it.de  ')
    await user.type(screen.getByLabelText('Password'), 'a-long-passphrase')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(signInWithPassword).toHaveBeenCalledWith('sabine@example-it.de', 'a-long-passphrase')
  })
})
