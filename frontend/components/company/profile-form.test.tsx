/**
 * `ProfileForm` — the branches where a wrong answer shipped and nobody saw it (S4.2.1).
 *
 * Two real defects, both fixed in commit 6d91e28, are what these tests exist to catch again:
 *
 * 1. **`1` `.` `5` became `15`.** The number inputs were controlled by the *parsed* value,
 *    so `1.` parsed to `1`, re-rendered as `"1"`, and the decimal point was gone before the
 *    next keystroke. It was possible because a controlled input with a parsed value looks
 *    right for every whole number a developer types while checking it. Only a decimal typed
 *    one key at a time shows it — which is what `userEvent.type` does and a `fireEvent`
 *    with the finished string never would.
 * 2. **A save that worked was headed "Not saved".** `PUT /companies/me` writes the row and
 *    then the agent's memory, and answers 200 with `warning` when only the second write
 *    failed; the form handed that warning to the failure box (`setFailure(result.warning)`).
 *    It was possible because success-with-a-caveat was not a state the component had, so the
 *    only place a sentence could go was the error box.
 *
 * The API is stubbed at `lib/companies` — the two functions the form calls — and nothing
 * else: the inputs, labels, notices and the parse-on-submit are all the real components.
 * jsdom sees none of the layout, so nothing here claims to.
 */
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { ApiError } from '@/lib/api-client'
import {
  loadProfile,
  saveProfile,
  type CompanyProfile,
  type CompanyProfileResponse,
} from '@/lib/companies'

import { ProfileForm } from './profile-form'

vi.mock('@/lib/companies', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/companies')>()
  return { ...actual, loadProfile: vi.fn(), saveProfile: vi.fn() }
})

const NOT_SAVED = 'Not saved'
const SAVED_WITH_WARNING = "Saved, but not yet in the agent's memory"
const MEMORY_WARNING =
  "The profile is saved, but the agent's memory could not be updated. Save again to retry."

function savedResponse(profile: CompanyProfile, warning?: string): CompanyProfileResponse {
  return {
    ...profile,
    registration_number: profile.registration_number ?? null,
    registration_court: profile.registration_court ?? null,
    staff_fte: profile.staff_fte ?? null,
    staff_fte_relevant: profile.staff_fte_relevant ?? null,
    certificates: profile.certificates.map((held) => ({
      name: held.name,
      issuer: held.issuer ?? null,
      number: held.number ?? null,
      issued_on: held.issued_on ?? null,
      expires_on: held.expires_on ?? null,
      scope: held.scope ?? null,
      is_expired: false,
      is_valid: held.expires_on !== null && held.expires_on !== undefined,
    })),
    has_expired_certificates: false,
    checked_on: '2026-09-16',
    warning: warning ?? null,
  }
}

/** A new account: no company row yet, so the form is in its create route. */
async function renderNewCompanyForm() {
  vi.mocked(loadProfile).mockResolvedValue({ profile: undefined })
  render(<ProfileForm />)
  const submit = await screen.findByRole('button', { name: 'Create my company' })
  return { submit, user: userEvent.setup() }
}

beforeEach(() => {
  vi.mocked(loadProfile).mockReset()
  vi.mocked(saveProfile).mockReset()
})

describe('ProfileForm — numbers are text until submit', () => {
  test('typing 1 . 5 into a turnover amount reads 1.5, not 15', async () => {
    const { user } = await renderNewCompanyForm()
    await user.click(screen.getByRole('button', { name: 'Add a financial year' }))
    const amount = screen.getByLabelText('Amount')

    await user.type(amount, '1.5')

    expect(amount).toHaveValue('1.5')
  })

  test('a German decimal comma survives typing and is sent as the number it means', async () => {
    const { user, submit } = await renderNewCompanyForm()
    vi.mocked(saveProfile).mockImplementation(async (profile) => savedResponse(profile))
    const fte = screen.getByLabelText('Total full-time equivalents')

    await user.type(screen.getByLabelText('Legal name'), 'Musterfirma GmbH')
    await user.type(fte, '12,5')
    expect(fte).toHaveValue('12,5')
    await user.click(submit)

    expect(saveProfile).toHaveBeenCalledTimes(1)
    const [sent, route] = vi.mocked(saveProfile).mock.calls[0] ?? []
    expect(route).toEqual({ exists: false })
    expect(sent?.staff_fte).toBe(12.5)
    expect(sent?.name).toBe('Musterfirma GmbH')
  })

  test('a turnover amount is sent as a number, and an empty optional FTE as null', async () => {
    const { user, submit } = await renderNewCompanyForm()
    vi.mocked(saveProfile).mockImplementation(async (profile) => savedResponse(profile))
    await user.click(screen.getByRole('button', { name: 'Add a financial year' }))

    await user.type(screen.getByLabelText('Legal name'), 'Musterfirma GmbH')
    await user.clear(screen.getByLabelText('Year'))
    await user.type(screen.getByLabelText('Year'), '2025')
    await user.type(screen.getByLabelText('Amount'), '1500000,50')
    await user.click(submit)

    const [sent] = vi.mocked(saveProfile).mock.calls[0] ?? []
    expect(sent?.turnover).toEqual([
      { year: 2025, amount: 1500000.5, currency: 'EUR', field_of_activity: null },
    ])
    expect(sent?.staff_fte).toBeNull()
    expect(sent?.staff_fte_relevant).toBeNull()
  })

  test('text that is not a number is refused under its field before anything is sent', async () => {
    const { user, submit } = await renderNewCompanyForm()
    const fte = screen.getByLabelText('Total full-time equivalents')

    await user.type(fte, 'twelve')
    await user.click(submit)

    expect(saveProfile).not.toHaveBeenCalled()
    expect(fte).toBeInvalid()
    expect(fte).toHaveAccessibleDescription('Enter a number, such as 12 or 12,5.')
    const alert = screen.getByRole('alert')
    expect(within(alert).getByText(NOT_SAVED)).toBeInTheDocument()
    expect(
      within(alert).getByText('Some values need changing. See the fields below.')
    ).toBeInTheDocument()
  })
})

describe('ProfileForm — three outcomes, not two', () => {
  test('a 200 that carries a warning is headed as saved, never "Not saved"', async () => {
    const { user, submit } = await renderNewCompanyForm()
    vi.mocked(saveProfile).mockImplementation(async (profile) =>
      savedResponse(profile, MEMORY_WARNING)
    )

    await user.type(screen.getByLabelText('Legal name'), 'Musterfirma GmbH')
    await user.click(submit)

    const notice = await screen.findByRole('status')
    expect(within(notice).getByText(SAVED_WITH_WARNING)).toBeInTheDocument()
    expect(within(notice).getByText(MEMORY_WARNING)).toBeInTheDocument()
    expect(screen.queryByText(NOT_SAVED)).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  test('a plain 200 is headed "Saved" and the button now reads as an update', async () => {
    const { user, submit } = await renderNewCompanyForm()
    vi.mocked(saveProfile).mockImplementation(async (profile) => savedResponse(profile))

    await user.type(screen.getByLabelText('Legal name'), 'Musterfirma GmbH')
    await user.click(submit)

    const notice = await screen.findByRole('status')
    expect(within(notice).getByText('Saved')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeInTheDocument()
    expect(screen.queryByText(NOT_SAVED)).not.toBeInTheDocument()
  })

  test("a 422 from the server lands under the field pydantic named, and the heading is 'Not saved'", async () => {
    const { user, submit } = await renderNewCompanyForm()
    vi.mocked(saveProfile).mockRejectedValue(
      new ApiError({
        status: 422,
        statusText: 'Unprocessable Content',
        method: 'POST',
        url: 'http://localhost:8000/companies',
        body: {
          detail: [
            {
              type: 'greater_than_equal',
              loc: ['body', 'staff_fte'],
              msg: 'Input should be greater than or equal to 0',
              input: -3,
              ctx: { ge: 0 },
            },
          ],
        },
      })
    )
    const fte = screen.getByLabelText('Total full-time equivalents')

    await user.type(screen.getByLabelText('Legal name'), 'Musterfirma GmbH')
    await user.type(fte, '-3')
    await user.click(submit)

    const alert = await screen.findByRole('alert')
    expect(within(alert).getByText(NOT_SAVED)).toBeInTheDocument()
    expect(fte).toBeInvalid()
    expect(fte).toHaveAccessibleDescription('Input should be greater than or equal to 0')
    // The bidder's text is kept for correcting, not wiped by the refusal.
    expect(fte).toHaveValue('-3')
  })

  test('a failure other than a 422 is "Not saved" with the API sentence, and nothing is marked saved', async () => {
    const { user, submit } = await renderNewCompanyForm()
    vi.mocked(saveProfile).mockRejectedValue(
      new ApiError({
        status: 503,
        statusText: 'Service Unavailable',
        method: 'POST',
        url: 'http://localhost:8000/companies',
        body: { detail: 'The database is not reachable.' },
      })
    )

    await user.type(screen.getByLabelText('Legal name'), 'Musterfirma GmbH')
    await user.click(submit)

    const alert = await screen.findByRole('alert')
    expect(within(alert).getByText(NOT_SAVED)).toBeInTheDocument()
    expect(within(alert).getByText(/The database is not reachable\./)).toBeInTheDocument()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})
