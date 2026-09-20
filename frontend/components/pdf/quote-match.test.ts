/**
 * The quote matcher (ADR-0105) — the half of PDF highlighting that can be tested without a
 * browser, and the half where a bug is silent.
 *
 * A wrong span does not throw and does not look broken: it draws a confident orange box over
 * the wrong sentence of a German tender, which is worse than drawing nothing. These tests are
 * the only thing standing between that and a bidder. The geometry — turning a span into boxes
 * with a DOM `Range` — has no test here on purpose: jsdom has no layout, so `getClientRects`
 * returns nothing and a test of it would assert only that it was called. That half belongs to
 * `e2e/bid-workspace.spec.ts`, which has a real browser and a real PDF.
 */
import { describe, expect, test } from 'vitest'

import { locateQuote, normaliseForMatch } from './quote-match'

describe('normaliseForMatch', () => {
  test('removes whitespace rather than collapsing it', () => {
    // Measured against the three real packs: collapsing lost 53 of 626 citations, because a
    // page draws `Elektronischer Katalog : Nicht zulässig` where the extractor stored
    // `Elektronischer Katalog: Nicht zulässig`. Any rule about how much whitespace counts as
    // the same is wrong somewhere; having none cannot be.
    const { text } = normaliseForMatch('Der   Bieter\n\that')

    expect(text).toBe('DerBieterhat')
  })

  test('drops a hyphen that a line break carried, because the quote will not have it', () => {
    // Page 5 of the German notice breaks `Haupt- oder`; the extractor stored `Hauptoder`.
    expect(normaliseForMatch('als Haupt- oder Unterauftragnehmer').text).toBe(
      'alsHauptoderUnterauftragnehmer'
    )
  })

  test('strips the inline HTML pymupdf4llm writes into a quote', () => {
    // Real quotes from the English pack: `tenderer<sup>8</sup>`, `above<br>EUR 1 500 000`.
    expect(normaliseForMatch('per tenderer<sup>8</sup> .').text).toBe('pertenderer8.')
    expect(normaliseForMatch('years above<br>EUR 1 500 000.').text).toBe(
      'yearsaboveEUR1500000.'
    )
  })

  test('strips the markdown emphasis pymupdf4llm writes into a stored quote', () => {
    // The trap CLAUDE.md records: `to_markdown` keeps bold, `get_text` does not, so the
    // stored quote and the page disagree about four asterisks.
    const { text } = normaliseForMatch('Mindestjahresumsatz von **2 Mio. EUR**')

    expect(text).toBe('Mindestjahresumsatzvon2Mio.EUR')
  })

  test('canonicalises the spaces, dashes and quotes the two extractions spell differently', () => {
    const { text } = normaliseForMatch('2 Mio.–EUR „Nachweis“')

    expect(text).toBe('2Mio.-EUR"Nachweis"')
  })

  test('drops a soft hyphen, which a PDF uses to break a word and a quote never carries', () => {
    const { text } = normaliseForMatch('Ge­schäfts­jahren')

    expect(text).toBe('Geschäftsjahren')
  })

  test('does not fold case, because the quote is verbatim from the page', () => {
    const { text } = normaliseForMatch('Der Bieter')

    expect(text).toBe('DerBieter')
  })

  test('maps every normalised character back to the character that produced it', () => {
    const source = '**Um**satz'
    const { text, map } = normaliseForMatch(source)

    expect(text).toBe('Umsatz')
    expect(map).toHaveLength(text.length)
    // 'U' is at index 2 of the source, past the two asterisks; 's' is at index 6, past two more.
    expect(source[map[0] ?? -1]).toBe('U')
    expect(source[map[2] ?? -1]).toBe('s')
  })
})

describe('locateQuote', () => {
  test('finds a quote that sits inside one text item', () => {
    const items = ['Der Bieter hat einen Mindestjahresumsatz von 2 Mio. EUR nachzuweisen.']

    const spans = locateQuote(items, 'Mindestjahresumsatz von 2 Mio. EUR')

    expect(spans).toHaveLength(1)
    const [span] = spans
    expect(span?.itemIndex).toBe(0)
    expect(items[0]?.slice(span?.start, span?.end)).toBe('Mindestjahresumsatz von 2 Mio. EUR')
  })

  test('finds a quote split across two items, and reports one span per item', () => {
    // A PDF breaks a line wherever the typesetter did; the sentence does not care.
    const items = ['Der Bieter hat einen', 'Mindestjahresumsatz nachzuweisen.']

    const spans = locateQuote(items, 'einen Mindestjahresumsatz')

    expect(spans).toHaveLength(2)
    expect(spans[0]?.itemIndex).toBe(0)
    expect(items[0]?.slice(spans[0]?.start, spans[0]?.end)).toBe('einen')
    expect(spans[1]?.itemIndex).toBe(1)
    expect(items[1]?.slice(spans[1]?.start, spans[1]?.end)).toBe('Mindestjahresumsatz')
  })

  test('finds a bolded stored quote on a page that has no bold', () => {
    const items = ['Der Bieter hat einen Mindestjahresumsatz von 2 Mio. EUR nachzuweisen.']

    const spans = locateQuote(items, 'einen **Mindestjahresumsatz** von 2 Mio. EUR')

    expect(spans).toHaveLength(1)
    expect(items[0]?.slice(spans[0]?.start, spans[0]?.end)).toBe(
      'einen Mindestjahresumsatz von 2 Mio. EUR'
    )
  })

  test('falls back to the longest prefix when the page breaks the quote unrepairably', () => {
    // The page carries the opening of the clause and then something the quote does not have.
    const opening = 'Der Bieter hat einen Mindestjahresumsatz von zwei Millionen Euro'
    const items = [`${opening} [Fussnote 4] in den letzten drei Geschaeftsjahren`]

    const spans = locateQuote(items, `${opening} in den letzten drei Geschaeftsjahren`)

    expect(spans).toHaveLength(1)
    const matched = items[0]?.slice(spans[0]?.start, spans[0]?.end) ?? ''
    expect(opening.startsWith(matched)).toBe(true)
    expect(matched.length).toBeGreaterThanOrEqual(40)
  })

  test('returns nothing when the quote is not on the page', () => {
    const items = ['Der Bieter hat einen Mindestjahresumsatz nachzuweisen.']

    expect(locateQuote(items, 'Drei vergleichbare Referenzen aus drei Jahren')).toEqual([])
  })

  test('returns nothing rather than a near-miss for a short quote', () => {
    // Below the prefix floor there is no prefix long enough to be evidence, so a quote that
    // is not present whole must not match on its first few letters.
    const items = ['Umsatznachweis erforderlich']

    expect(locateQuote(items, 'Umsatzsteuer')).toEqual([])
  })

  test("matches the browser suite's fixture page, which is the contract between them", () => {
    // Verbatim from `e2e/fixtures/source-page.pdf` as pdf.js actually reads it — the cited
    // sentence is split across two text items by the line break, and the third item is a
    // distractor that must stay untouched. If this fails, the browser test is about to fail
    // too, and this says so in milliseconds instead of minutes.
    const items = [
      'Der Bieter hat einen Mindestjahresumsatz von 2 Mio. EUR in den',
      'letzten drei Geschäftsjahren nachzuweisen.',
      'Diese Zeile ist nicht zitiert und darf nicht markiert werden.',
    ]
    const sourceText =
      'Der Bieter hat einen Mindestjahresumsatz von 2 Mio. EUR in den letzten drei Geschäftsjahren nachzuweisen.'

    const spans = locateQuote(items, sourceText)

    expect(spans.map((span) => span.itemIndex)).toEqual([0, 1])
    expect(items[0]?.slice(spans[0]?.start, spans[0]?.end)).toBe(items[0])
    expect(items[1]?.slice(spans[1]?.start, spans[1]?.end)).toBe(items[1])
  })

  test('is empty for an empty page or an empty quote', () => {
    expect(locateQuote([], 'anything')).toEqual([])
    expect(locateQuote(['a page'], '   ')).toEqual([])
  })

  test('joins two items into one word, which is what a mid-word split needs', () => {
    // This test asserted the opposite until 2026-09-20, when the matcher was measured against
    // the three real tender packs and missed 53 of 626 citations. pdf.js splits an item
    // wherever the kerning changes, so `Umsatz` + `steuer` really is `Umsatzsteuer` on the
    // page more often than it is two words, and refusing to join cost far more than it saved.
    // The guard against a nonsense match is not spacing but length — `MIN_PREFIX_CHARS`, and
    // the fact that these quotes are whole legal sentences.
    const items = ['Umsatz', 'steuer ist hier gemeint und dieser Satz ist lang genug']

    const spans = locateQuote(items, 'Umsatzsteuer ist hier gemeint und dieser Satz')

    expect(spans.map((span) => span.itemIndex)).toEqual([0, 1])
  })
})
