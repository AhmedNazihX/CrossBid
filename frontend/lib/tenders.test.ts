/**
 * The two facts a result card states about a notice it did not choose (ADR-0111).
 *
 * Both exist because the search filters on `place-of-performance` and the list said "open
 * notices". A bidder searching France was shown British and Czech tenders published in 2019
 * with nothing on screen to explain either, and reported it as a broken country filter.
 */
import { describe, expect, test } from 'vitest'

import { countryNameOf, isBoughtElsewhere, isNoticeClosed, type TedNotice } from './tenders'

function noticeFixture(over: Partial<TedNotice> = {}): TedNotice {
  return {
    publication_number: '629621-2026',
    title: 'France – Systems consultancy services',
    buyer: 'SPL Eau du Bassin Rennais',
    buyer_countries: ['FRA'],
    description: null,
    deadline: '2026-10-07',
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

describe('countryNameOf', () => {
  test('names an EU member the bidder can search for', () => {
    expect(countryNameOf('FRA')).toBe('France')
  })

  test('names a non-EU buyer, which is the case that caused the bug report', () => {
    expect(countryNameOf('GBR')).toBe('United Kingdom')
  })

  test('falls back to the code itself rather than showing nothing', () => {
    expect(countryNameOf('ZZZ')).toBe('ZZZ')
  })

  test('reads a lower-case code, since TED is not the only caller', () => {
    expect(countryNameOf('cze')).toBe('Czechia')
  })
})

describe('isBoughtElsewhere', () => {
  test('a French-bought notice in a French search is not flagged', () => {
    expect(isBoughtElsewhere(noticeFixture(), 'fr')).toBe(false)
  })

  test('a British-bought notice in a French search is flagged', () => {
    // 59532-2024: performed in DNK, FRA and GBR, so it answers a France search honestly.
    expect(isBoughtElsewhere(noticeFixture({ buyer_countries: ['GBR'] }), 'fr')).toBe(true)
  })

  test('a notice naming no buyer country is unknown, not foreign', () => {
    expect(isBoughtElsewhere(noticeFixture({ buyer_countries: [] }), 'fr')).toBe(false)
  })

  test('a notice bought in several countries is home if any of them is the one searched', () => {
    const notice = noticeFixture({ buyer_countries: ['DEU', 'FRA'] })

    expect(isBoughtElsewhere(notice, 'fr')).toBe(false)
  })
})

describe('isNoticeClosed', () => {
  const now = new Date('2026-09-20T09:00:00Z')

  test('a deadline in the past is closed', () => {
    expect(isNoticeClosed(noticeFixture({ deadline: '2019-08-16' }), now)).toBe(true)
  })

  test('a deadline in the future is not', () => {
    expect(isNoticeClosed(noticeFixture({ deadline: '2026-10-07' }), now)).toBe(false)
  })

  test('a notice with no published deadline is not closed, because we do not know', () => {
    expect(isNoticeClosed(noticeFixture({ deadline: null }), now)).toBe(false)
  })

  test('a deadline falling today is still open — the bidder has the day', () => {
    expect(isNoticeClosed(noticeFixture({ deadline: '2026-09-20' }), now)).toBe(false)
  })
})
