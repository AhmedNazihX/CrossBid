/**
 * The matcher measured against three real tender packs (ADR-0105).
 *
 * **This test exists because the hand-made fixture lied.** `quote-match.test.ts` was written
 * alongside the implementation, against a PDF this repo generated, and it passed — while the
 * feature failed on the first real tender a bidder opened, reporting *"The cited words were
 * not found on page 3"*. A fixture an implementation agrees with proves only that they agree.
 *
 * So the corpus here is not invented: every case is a requirement the agent really extracted
 * from `backend/tests/fixtures/extractions/*.live.json`, paired with the text items pdf.js
 * really reports for the page it cites. `scripts/capture-real-quotes.mjs` captured it; the
 * PDFs are not needed at run time, so this costs milliseconds and no network.
 *
 * Measured on 2026-09-20, before and after the fix:
 *
 * | | before | after |
 * |---|---|---|
 * | DE | 295 / 311 | **311 / 311** |
 * | FR | 101 / 114 | **113 / 114** |
 * | EN | 177 / 201 | **201 / 201** |
 * | total | 573 / 626 (91.5 %) | **625 / 626 (99.8 %)** |
 *
 * The one that still misses is not a matcher failure: that French clause appears on **no page
 * of the document**, in any form — the extractor produced a quote the PDF does not contain, so
 * the honest answer is the "not found" notice the panel shows.
 *
 * The floors below are deliberately a little under the measured numbers, so a small fixture
 * refresh does not fail the build, and far enough above the old behaviour that the regression
 * this test was written for cannot come back unseen.
 */
import { describe, expect, test } from 'vitest'

import corpus from './__fixtures__/real-quotes.json'
import { locateQuote } from './quote-match'

interface Corpus {
  readonly capturedWith: string
  readonly pages: readonly (readonly string[])[]
  readonly cases: readonly {
    readonly lang: string
    readonly document: string
    readonly page: number
    readonly pageIndex: number
    readonly quote: string
  }[]
}

const { pages, cases } = corpus as Corpus

/** Per language: how many of its citations must be located. Measured: 311, 113, 201. */
const FLOORS: Readonly<Record<string, { readonly located: number; readonly total: number }>> = {
  de: { located: 309, total: 311 },
  fr: { located: 111, total: 114 },
  en: { located: 199, total: 201 },
}

function located(lang: string): number {
  return cases.filter(
    (one) => one.lang === lang && locateQuote(pages[one.pageIndex] ?? [], one.quote).length > 0
  ).length
}

describe('the matcher against real tender packs', () => {
  test('the corpus is the one that was captured, not an empty file', () => {
    expect(cases).toHaveLength(626)
    expect(pages.length).toBeGreaterThan(100)
  })

  for (const [lang, floor] of Object.entries(FLOORS)) {
    test(`${lang.toUpperCase()}: locates at least ${floor.located} of ${floor.total} real citations`, () => {
      const total = cases.filter((one) => one.lang === lang).length
      expect(total, 'the corpus lost cases').toBe(floor.total)

      const hits = located(lang)

      expect(
        hits,
        `${hits}/${total} located — collapsing whitespace instead of removing it scored 295/311, 101/114 and 177/201`
      ).toBeGreaterThanOrEqual(floor.located)
    })
  }

  test('across all three packs, at least 99 % of citations are located', () => {
    const hits = Object.keys(FLOORS).reduce((sum, lang) => sum + located(lang), 0)

    expect(hits / cases.length).toBeGreaterThanOrEqual(0.99)
  })
})
