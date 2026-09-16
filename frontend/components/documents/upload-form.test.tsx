/**
 * `UploadForm` — what a bidder sees when the hour's uploads are used up (S4.2.2, audit
 * finding M12).
 *
 * Why this was quietly wrong: a 429 went down the generic error path. The API's own
 * sentence was shown — it carries the wait in seconds — but the button stayed live, so the
 * bidder pressed it again and was refused again, and the number in the sentence was stale
 * from the moment it appeared. The ask panel had already got this right (ADR-0058): read
 * `Retry-After`, disable the control until that second, name the clock time, and re-enable
 * without a reload. This test asks the upload form for the same treatment.
 *
 * `Date` alone is faked, so `formatTime` and the hook agree on "now" while `userEvent` keeps
 * its real timers. The hook's own countdown is pinned in `lib/use-rate-limit.test.ts`.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { ApiError } from '@/lib/api-client'
import { formatTime } from '@/lib/format'

import { UploadForm, type UploadFormProps } from './upload-form'

const NOW = new Date('2026-10-07T14:30:00Z')
const RETRY_AFTER_SECONDS = 120
const MILLISECONDS_PER_SECOND = 1000

/** `POST /documents` refused by `document_upload_limit`, header and sentence both present. */
function rateLimited(headers?: Headers): ApiError {
  return new ApiError({
    status: 429,
    statusText: 'Too Many Requests',
    method: 'POST',
    url: 'http://localhost:8000/documents',
    body: {
      detail:
        'Rate limit reached for document uploads: at most 30 per hour for one company. Try again in 120 seconds — nothing you have already uploaded or started is affected.',
    },
    headers,
  })
}

function pdf(): File {
  return new File(['%PDF-1.4\n'], 'Leistungsbeschreibung.pdf', { type: 'application/pdf' })
}

async function uploadOnce(onUpload: UploadFormProps['onUpload']) {
  render(<UploadForm onUpload={onUpload} defaultKind="tender_document" />)
  const user = userEvent.setup()
  await user.upload(screen.getByLabelText('File'), pdf())
  await user.click(screen.getByRole('button', { name: 'Upload file' }))
  return user
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(NOW)
})

afterEach(() => {
  vi.useRealTimers()
})

describe('UploadForm — a 429 is a wait, not an error', () => {
  test('disables the button until the second the API named, and says the clock time', async () => {
    const onUpload = vi
      .fn()
      .mockRejectedValue(rateLimited(new Headers({ 'Retry-After': '120' })))

    await uploadOnce(onUpload)

    const liftsAt = formatTime(
      new Date(NOW.getTime() + RETRY_AFTER_SECONDS * MILLISECONDS_PER_SECOND)
    )
    expect(screen.getByRole('button', { name: 'Upload file' })).toBeDisabled()
    expect(
      screen.getByText(`This company has used its hour's uploads. Try again at ${liftsAt}.`)
    ).toBeInTheDocument()
  })

  test('shows the API’s own sentence when the wait cannot be read', async () => {
    const onUpload = vi.fn().mockRejectedValue(rateLimited(new Headers()))

    await uploadOnce(onUpload)

    expect(screen.getByRole('button', { name: 'Upload file' })).toBeEnabled()
    expect(screen.getByText(/Try again in 120 seconds/)).toBeInTheDocument()
  })

  test('any other refusal keeps the button live and shows the detail', async () => {
    const onUpload = vi.fn().mockRejectedValue(
      new ApiError({
        status: 415,
        statusText: 'Unsupported Media Type',
        method: 'POST',
        url: 'http://localhost:8000/documents',
        body: { detail: 'Only PDF files are accepted.' },
      })
    )

    await uploadOnce(onUpload)

    expect(screen.getByRole('button', { name: 'Upload file' })).toBeEnabled()
    expect(screen.getByText('Only PDF files are accepted.')).toBeInTheDocument()
  })
})
