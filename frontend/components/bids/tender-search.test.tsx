/**
 * What a result card says about a notice the bidder did not choose (ADR-0111).
 *
 * A bidder searched CPV 72000000, France, "Cyber Security" and was shown tenders bought in
 * the UK and Czechia, published years earlier, under the heading "N open notices match". The
 * search itself was fixed in `ted_client.py`; these are the three things the *screen* was
 * getting wrong, and each is invisible to a type checker.
 *
 * The country control filters on `place-of-performance`, which is a list — a pan-European
 * framework is performed in France and bought in London, so it answers a France search
 * honestly. The card has to say so, because otherwise the only available reading is that the
 * filter is broken, which is the reading that produced the bug report.
 */
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { searchTenders, type TedNotice, type TedSearchPage } from '@/lib/tenders'

import { TenderSearch } from './tender-search'

vi.mock('@/lib/tenders', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/tenders')>()
  return { ...actual, searchTenders: vi.fn() }
})

/** Well past every deadline below, so "closed" is a fact of the fixture and not of the day. */
const NOW = new Date('2026-09-20T09:00:00Z')

function noticeFixture(over: Partial<TedNotice> = {}): TedNotice {
  return {
    publication_number: '629621-2026',
    title: 'France – Systems consultancy services',
    buyer: 'SPL Eau du Bassin Rennais',
    buyer_countries: ['FRA'],
    description: null,
    deadline: '2026-12-07',
    deadline_utc_offset_minutes: 120,
    official_languages: ['FRA'],
    submission_languages: ['FRA'],
    cpv: ['72246000'],
    selection_criteria: [],
    notice_pdf_url: null,
    documents_url: null,
    published_on: '2026-09-14',
    ...over,
  }
}

function pageOf(notices: readonly TedNotice[], total = notices.length): TedSearchPage {
  return { notices: [...notices], total, page: 1, limit: 20, reachable_total: total }
}

async function search(notices: readonly TedNotice[], total?: number) {
  vi.mocked(searchTenders).mockResolvedValue(pageOf(notices, total))
  const user = userEvent.setup()
  render(<TenderSearch language="de" onPick={vi.fn()} />)
  await user.click(screen.getByRole('button', { name: /search ted/i }))
  return screen.findByRole('heading', { level: 3 })
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.useFakeTimers({ shouldAdvanceTime: true })
  vi.setSystemTime(NOW)
})

describe('a result card', () => {
  test('names the buyer country when it is not the one searched for', async () => {
    // 59532-2024: bought in GBR, performed in DNK, FRA and GBR. France is the default.
    await search([noticeFixture({ buyer_countries: ['GBR'] })])

    expect(screen.getByText(/Buyer in United Kingdom/)).toBeVisible()
  })

  test('names the buyer country when it is the one searched for too', async () => {
    await search([noticeFixture()])

    expect(screen.getByText(/Buyer in France/)).toBeVisible()
  })

  test('says a passed deadline is closed rather than due', async () => {
    await search([noticeFixture({ deadline: '2019-08-16' })])

    expect(screen.getByText(/Closed/)).toBeVisible()
    expect(screen.queryByText(/^Due /)).toBeNull()
  })

  test('still says due for a deadline that has not passed', async () => {
    await search([noticeFixture({ deadline: '2026-12-07' })])

    expect(screen.getByText(/Due /)).toBeVisible()
    expect(screen.queryByText(/Closed/)).toBeNull()
  })

  test('says nothing about a country the notice does not name', async () => {
    await search([noticeFixture({ buyer_countries: [] })])

    expect(screen.queryByText(/Buyer in/)).toBeNull()
  })

  test('leaves a notice with no published deadline as its own answer', async () => {
    await search([noticeFixture({ deadline: null })])

    expect(screen.getByText('No deadline published')).toBeVisible()
    expect(screen.queryByText(/Closed/)).toBeNull()
  })
})

describe('the result count', () => {
  test('does not call the matches open, because TED does not', async () => {
    const heading = await search([noticeFixture()], 45)

    const list = heading.closest('div')?.parentElement?.parentElement
    expect(within(list as HTMLElement).queryByText(/open notices/)).toBeNull()
    expect(screen.getByText(/45 notices match/)).toBeVisible()
  })
})
