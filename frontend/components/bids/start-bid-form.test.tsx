/**
 * `StartBidForm` — what a picked notice writes onto the bid, and what a 429 does to the
 * button (S4.3.1, S4.4.1; audit findings M10 and M12).
 *
 * **M10.** ADR-0044 said the notice prefills "everything TED actually published"; the code
 * prefilled the buyer and the deadline's offset and put the *date* in a hint for the bidder
 * to retype, and it never sent the title at all — so every bid was named by its publication
 * number while `Dashboard.dc.html` shows the tender's name. A `datetime-local` input cannot
 * hold a date without an hour (the browser sanitises `2026-10-07` to an empty string), which
 * is why the date could only ever be a hint. The field is now a date and a time, the date
 * seeded from TED and the time left blank: TED publishes no hour (CLAUDE.md, ADR-0043), and
 * a `00:00` would be an invented deadline that looks like a read one.
 *
 * **M12.** A 429 on `POST /bids` went down the generic error path with the button still
 * live. The same treatment the ask panel and the upload form give it is asked for here.
 *
 * `useRouter` is stubbed because the form calls `router.push` after a 202 and there is no
 * App Router in jsdom; `startBid` is stubbed because it is the one call the form makes. The
 * inputs, the checklist and the rules are the real components.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { documentFixture } from '@/e2e/support/fixtures'
import { ApiError } from '@/lib/api-client'
import { startBid } from '@/lib/bids'
import { formatTime } from '@/lib/format'
import type { TedNotice } from '@/lib/tenders'

import { StartBidForm } from './start-bid-form'

vi.mock('next/navigation', async (importOriginal) => {
  const actual = await importOriginal<typeof import('next/navigation')>()
  return { ...actual, useRouter: () => ({ push: vi.fn() }) }
})

vi.mock('@/lib/bids', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/bids')>()
  return { ...actual, startBid: vi.fn() }
})

const NOW = new Date('2026-09-16T09:00:00Z')
const PACK_FILE = 'Leistungsbeschreibung.pdf'
const DOCUMENT_ID = '33333333-3333-4333-8333-333333333333'

/** A German contract notice as `GET /tenders/search` returns it: a date, an offset, no hour. */
const NOTICE: TedNotice = {
  publication_number: '614251-2026',
  title: 'Deutschland – IT-Dienstleistungen – Rahmenvertrag VV2',
  buyer: 'Bundesamt für Beispiele',
  buyer_countries: ['DEU'],
  description: null,
  deadline: '2026-10-07',
  deadline_utc_offset_minutes: 120,
  official_languages: ['deu'],
  submission_languages: ['deu'],
  cpv: ['72000000'],
  selection_criteria: [],
  notice_pdf_url: null,
  documents_url: null,
  published_on: '2026-09-01',
}

const READY_PACK = {
  phase: 'loaded',
  documents: [documentFixture({ id: DOCUMENT_ID, name: PACK_FILE })],
} as const

function rateLimited(): ApiError {
  return new ApiError({
    status: 429,
    statusText: 'Too Many Requests',
    method: 'POST',
    url: 'http://localhost:8000/bids',
    body: {
      detail:
        'Rate limit reached for bids started: at most 10 per hour for one company. Try again in 300 seconds — nothing you have already uploaded or started is affected.',
    },
    headers: new Headers({ 'Retry-After': '300' }),
  })
}

async function renderWithPackTicked(notice: TedNotice | undefined) {
  render(<StartBidForm notice={notice} documentList={READY_PACK} />)
  const user = userEvent.setup()
  // The checkbox's name is its label plus its description line, so match the filename in it.
  await user.click(screen.getByRole('checkbox', { name: /Leistungsbeschreibung\.pdf/ }))
  return user
}

const startButton = () => screen.getByRole('button', { name: 'Start analysis' })

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(NOW)
  vi.mocked(startBid).mockReset()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('StartBidForm — what the notice prefills (M10)', () => {
  test('seeds the deadline date from TED and leaves the hour blank', async () => {
    await renderWithPackTicked(NOTICE)

    expect(screen.getByLabelText('Deadline date (optional)')).toHaveValue('2026-10-07')
    expect(screen.getByLabelText('Deadline time')).toHaveValue('')
    expect(screen.getByLabelText('Its time zone')).toHaveValue('120')
  })

  test('a seeded date with no hour blocks Start and says why, rather than dropping the deadline', async () => {
    const user = await renderWithPackTicked(NOTICE)

    expect(startButton()).toBeDisabled()
    expect(
      screen.getByText(
        'Add the hour the notice states, or clear the date. TED publishes no time of day.'
      )
    ).toBeInTheDocument()

    await user.clear(screen.getByLabelText('Deadline date (optional)'))

    expect(startButton()).toBeEnabled()
  })

  test('sends the title, the buyer and the assembled deadline once the hour is given', async () => {
    const user = await renderWithPackTicked(NOTICE)
    vi.mocked(startBid).mockResolvedValue({ id: 'bid-1' } as never)

    fireEvent.change(screen.getByLabelText('Deadline time'), { target: { value: '16:00' } })
    await user.click(startButton())

    expect(startBid).toHaveBeenCalledTimes(1)
    expect(vi.mocked(startBid).mock.calls[0]?.[0]).toMatchObject({
      notice_number: '614251-2026',
      title: 'Deutschland – IT-Dienstleistungen – Rahmenvertrag VV2',
      buyer: 'Bundesamt für Beispiele',
      source_language: 'de',
      deadline: '2026-10-07T16:00:00+02:00',
      document_ids: [DOCUMENT_ID],
    })
  })

  test('a bid typed in by hand sends no title and no deadline', async () => {
    const user = await renderWithPackTicked(undefined)
    vi.mocked(startBid).mockResolvedValue({ id: 'bid-1' } as never)

    await user.type(screen.getByLabelText('Notice number'), '618320-2026')
    await user.click(startButton())

    const sent = vi.mocked(startBid).mock.calls[0]?.[0]
    expect(sent).toBeDefined()
    expect(sent?.title ?? undefined).toBeUndefined()
    expect(sent?.deadline).toBeNull()
  })
})

describe('StartBidForm — a 429 is a wait, not an error (M12)', () => {
  test('disables Start until the second the API named, and says the clock time', async () => {
    const user = await renderWithPackTicked(undefined)
    vi.mocked(startBid).mockRejectedValue(rateLimited())
    await user.type(screen.getByLabelText('Notice number'), '618320-2026')

    await user.click(startButton())

    const liftsAt = formatTime(new Date(NOW.getTime() + 300_000))
    expect(startButton()).toBeDisabled()
    expect(
      screen.getByText(`This company has used its hour's bids. Try again at ${liftsAt}.`)
    ).toBeInTheDocument()
  })
})

describe('StartBidForm — a document other analyses already use', () => {
  const IN_USE = {
    phase: 'loaded',
    documents: [documentFixture({ id: DOCUMENT_ID, name: PACK_FILE, bid_count: 2 })],
  } as const

  test('offers a document two other analyses are already using', async () => {
    /**
     * The clause no test ever pinned, and the whole reason a pack had to be uploaded twice.
     *
     * The picker filtered on `bid_id === null`, so a document any earlier analysis held was
     * not rendered at all — not greyed out, not explained, simply absent. Comparing two
     * configurations on one tender meant re-uploading every file and re-paying to embed it.
     */
    render(<StartBidForm notice={NOTICE} documentList={IN_USE} />)

    const box = screen.getByRole('checkbox', { name: /Leistungsbeschreibung\.pdf/ })
    expect(box).toBeEnabled()

    await userEvent.setup().click(box)
    expect(screen.getByText('1 of 1 ready selected')).toBeInTheDocument()
  })

  test('says how many analyses are using it, and says nothing when none are', () => {
    const mixed = {
      phase: 'loaded',
      documents: [
        documentFixture({ id: DOCUMENT_ID, name: PACK_FILE, bid_count: 2 }),
        documentFixture({ id: 'd2', name: 'Anlage_3.pdf', bid_count: 0 }),
      ],
    } as const
    render(<StartBidForm notice={NOTICE} documentList={mixed} />)

    expect(screen.getByText(/used by 2 analyses/)).toBeInTheDocument()
    expect(screen.queryByText(/Anlage_3\.pdf.*used by/)).not.toBeInTheDocument()
  })

  test('puts the count in the checkbox name, where a screen reader reaches it', () => {
    // A marker rendered beside the label rather than inside it is invisible to assistive
    // technology, which is the regression this guards.
    render(<StartBidForm notice={NOTICE} documentList={IN_USE} />)

    expect(screen.getByRole('checkbox', { name: /used by 2 analyses/ })).toBeInTheDocument()
  })

  test('still refuses to tick a document that is in use and not yet ready', () => {
    const unready = {
      phase: 'loaded',
      documents: [
        documentFixture({ id: DOCUMENT_ID, name: PACK_FILE, bid_count: 2, status: 'parsed' }),
      ],
    } as const
    render(<StartBidForm notice={NOTICE} documentList={unready} />)

    expect(screen.getByRole('checkbox', { name: /Leistungsbeschreibung\.pdf/ })).toBeDisabled()
  })
})
