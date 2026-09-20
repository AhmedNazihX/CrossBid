/**
 * Finding a cited sentence inside a PDF page's text layer (ADR-0105).
 *
 * **This file is deliberately pure and knows nothing about pdf.js or the DOM.** It takes the
 * strings of a page's text items and the quote to look for, and answers *which item, which
 * characters*. Turning that into boxes on the screen is the browser's job — `pdf-page-view.tsx`
 * puts a `Range` over the matched characters and asks it for client rects — because jsdom has
 * no layout and geometry computed by hand is geometry nobody can test. The split is what makes
 * the hard half (matching) unit-testable at all.
 *
 * **Why matching is hard here.** There are no stored offsets anywhere in this product: the
 * backend keeps a chunk's page and its text and nothing geometric, so a highlight can only be
 * found by looking for the words. The two sides are two different extractions of the same page:
 * the stored quote comes from `pymupdf4llm`, which **renders emphasis as markdown**, so a
 * clause can be stored as `**Umsatz**` where the page says `Umsatz` — the same trap
 * `extract_reqs._normalised` exists for on the backend. On top of that a PDF's text layer
 * breaks lines wherever the typesetter did, joins them with no space, and is full of
 * non-breaking spaces, soft hyphens and typographic quotes that the stored text spells in
 * ASCII.
 *
 * So both sides are normalised the same way before comparing, and the normalisation keeps an
 * index back to the original so a match can be reported in the *page's* coordinates.
 *
 * **A wrong highlight is worse than none.** Matching never guesses: it either finds the quote
 * (or an honest prefix of it, for a quote the page breaks in a way normalisation cannot
 * repair) or it returns nothing and the caller says so out loud.
 */

/** Characters the two extractions spell differently, mapped to what both can agree on. */
const CANONICAL: Readonly<Record<string, string>> = {
  ' ': ' ', // no-break space
  ' ': ' ', // narrow no-break space
  ' ': ' ', // thin space
  ' ': ' ', // figure space
  '‘': "'", // ' '
  '’': "'",
  '‚': "'",
  '“': '"', // " "
  '”': '"',
  '„': '"',
  '–': '-', // en dash
  '—': '-', // em dash
  '−': '-', // minus sign
}

/**
 * The inline HTML `pymupdf4llm` writes into a stored quote, which the rendered page never has.
 *
 * Measured on the real packs: `tenderer<sup>8</sup>`, `above<br>EUR 1 500 000` and
 * `<u>2ème cas` and `<mark>[</mark>` are all quotes the extractor produced where the page
 * draws plain glyphs.
 * Only inline and break tags are listed — anything else inside angle brackets is text.
 */
const INLINE_TAGS = /<\/?(?:sup|sub|u|b|i|em|strong|br|mark|span)\s*\/?>/gi

/** Dropped outright: markdown emphasis from the stored quote, and invisible breaks from the PDF. */
const DROPPED = new Set([
  '*',
  '_',
  '`',
  '­', // soft hyphen
  '​', // zero-width space
  '﻿', // zero-width no-break space
])

export interface Normalised {
  /** The comparable form: canonical characters, no emphasis marks, **no whitespace at all**. */
  readonly text: string
  /**
   * `map[i]` is the index **in the original string** of the character that produced
   * `text[i]`. Normalisation only ever drops or replaces single characters, never expands
   * one into several, so this is always one-to-one.
   */
  readonly map: readonly number[]
}

/**
 * The comparable form of a string, with an index back to where each character came from.
 *
 * **Whitespace is removed, not collapsed, and that is the load-bearing decision.** It was
 * collapsed at first, and measured against the three real tender packs in
 * `backend/tests/fixtures` that lost 16 of 311 German quotes, 13 of 114 French and 24 of 201
 * English. The reason is visible on page 8 of the German notice: the page draws a label and
 * its value as two text items, which join as `Elektronischer Katalog : Nicht zulässig`, while
 * the extractor stored `Elektronischer Katalog: Nicht zulässig`. One space. pdf.js also splits
 * items mid-word for kerning and inserts no space where the page drew none, so any rule about
 * how much whitespace is "the same" is a rule that will be wrong somewhere. Having none at all
 * cannot be.
 *
 * The cost is that `the end` and `then d` compare equal. For the two-hundred-character legal
 * sentences this matches, that is not a risk worth a single lost citation.
 *
 * **A hyphen before removed whitespace goes with it**, because that is hyphenation: page 5 of
 * the same notice breaks `Haupt- oder` across a line, and the extractor stored `Hauptoder`.
 *
 * Case is **not** folded, matching the backend's own rule. The quote is verbatim text from
 * this very page, so case is signal rather than noise.
 */
export function normaliseForMatch(source: string): Normalised {
  const characters: string[] = []
  const map: number[] = []
  const inTag = markTags(source)
  for (let index = 0; index < source.length; index += 1) {
    const original = source[index] ?? ''
    if (inTag[index] === true || DROPPED.has(original)) {
      continue
    }
    const character = CANONICAL[original] ?? original
    if (/\s/.test(character)) {
      // `Haupt-` + line break + `oder` is one hyphenated word, and the side that was read by
      // a markdown parser rather than by a PDF renderer spells it without either.
      if (characters[characters.length - 1] === '-') {
        characters.pop()
        map.pop()
      }
      continue
    }
    characters.push(character)
    map.push(index)
  }
  return { text: characters.join(''), map }
}

/** Which characters of `source` are part of an inline HTML tag, so the loop can skip them. */
function markTags(source: string): readonly boolean[] {
  const flags = new Array<boolean>(source.length).fill(false)
  for (const match of source.matchAll(INLINE_TAGS)) {
    const at = match.index
    if (at === undefined) continue
    for (let offset = 0; offset < match[0].length; offset += 1) {
      flags[at + offset] = true
    }
  }
  return flags
}

/** A run of characters inside one text item of the page. `end` is exclusive. */
export interface QuoteSpan {
  readonly itemIndex: number
  readonly start: number
  readonly end: number
}

/**
 * The shortest prefix of a quote still worth highlighting, in normalised characters.
 *
 * A quote the page has broken in a way normalisation cannot repair — a hyphenated word split
 * across a column, a footnote marker dropped into the middle of a sentence — will not match
 * whole. Landing the reader on the first clause of the right sentence is still the right
 * answer; landing them on eight characters that happen to appear on the page is not.
 */
const MIN_PREFIX_CHARS = 40

/**
 * Where `quote` sits in a page whose text items are `items`, as a span per item it covers.
 *
 * Empty when the quote is not on this page. The items are joined with a newline before
 * searching — the separator is whitespace so that the de-hyphenation rule above can see an
 * item ending in `-` as a broken word. Since all whitespace is then removed, two items are
 * effectively glued, which is deliberate: pdf.js splits a word across items whenever the
 * kerning changes, and refusing to join them lost real citations (see `normaliseForMatch`).
 */
export function locateQuote(items: readonly string[], quote: string): readonly QuoteSpan[] {
  if (items.length === 0 || quote.trim() === '') {
    return []
  }
  const { joined, itemOf, offsetOf } = joinItems(items)
  const page = normaliseForMatch(joined)
  const needle = normaliseForMatch(quote)
  if (needle.text === '') {
    return []
  }

  const at = findLongestPrefix(page.text, needle.text)
  if (at === undefined) {
    return []
  }

  const firstSource = page.map[at.index]
  const lastSource = page.map[at.index + at.length - 1]
  if (firstSource === undefined || lastSource === undefined) {
    return []
  }
  return spansOver(firstSource, lastSource + 1, itemOf, offsetOf)
}

/**
 * The whole quote if the page carries it, else the **longest** prefix of it that the page
 * does carry, down to `MIN_PREFIX_CHARS`.
 *
 * Binary search, because "found" is monotonic in the prefix length: if the page has the first
 * *n* characters it has the first *n-1*. This replaced a halving loop that tried 200, 100 and
 * 50 characters and gave up — and so missed a French clause the page carried to 50-odd
 * characters but not 60, with the true boundary in a gap the halving stepped straight over.
 * Both cost about the same number of `indexOf` calls; only one of them answers the question.
 */
function findLongestPrefix(
  haystack: string,
  needle: string
): { readonly index: number; readonly length: number } | undefined {
  const whole = haystack.indexOf(needle)
  if (whole !== -1) {
    return { index: whole, length: needle.length }
  }
  // A quote shorter than the floor is searched whole or not at all: no prefix of it is long
  // enough to be evidence of anything.
  if (needle.length <= MIN_PREFIX_CHARS) {
    return undefined
  }
  let low = MIN_PREFIX_CHARS
  let high = needle.length
  let best: { index: number; length: number } | undefined
  while (low <= high) {
    const middle = Math.floor((low + high) / 2)
    const index = haystack.indexOf(needle.slice(0, middle))
    if (index === -1) {
      high = middle - 1
      continue
    }
    best = { index, length: middle }
    low = middle + 1
  }
  return best
}

interface JoinedItems {
  readonly joined: string
  /** For each character of `joined`, the index of the item it came from; `-1` for a separator. */
  readonly itemOf: readonly number[]
  /** For each character of `joined`, its offset within that item; `-1` for a separator. */
  readonly offsetOf: readonly number[]
}

function joinItems(items: readonly string[]): JoinedItems {
  const parts: string[] = []
  const itemOf: number[] = []
  const offsetOf: number[] = []
  items.forEach((item, itemIndex) => {
    if (itemIndex > 0) {
      parts.push('\n')
      itemOf.push(-1)
      offsetOf.push(-1)
    }
    parts.push(item)
    for (let offset = 0; offset < item.length; offset += 1) {
      itemOf.push(itemIndex)
      offsetOf.push(offset)
    }
  })
  return { joined: parts.join(''), itemOf, offsetOf }
}

/** The matched source range, cut at item boundaries and with the separators dropped. */
function spansOver(
  from: number,
  to: number,
  itemOf: readonly number[],
  offsetOf: readonly number[]
): readonly QuoteSpan[] {
  const spans: QuoteSpan[] = []
  let current: { itemIndex: number; start: number; end: number } | undefined
  for (let index = from; index < to; index += 1) {
    const itemIndex = itemOf[index]
    const offset = offsetOf[index]
    if (itemIndex === undefined || offset === undefined || itemIndex < 0) {
      continue
    }
    if (current !== undefined && current.itemIndex === itemIndex) {
      current.end = offset + 1
      continue
    }
    if (current !== undefined) {
      spans.push({ ...current })
    }
    current = { itemIndex, start: offset, end: offset + 1 }
  }
  if (current !== undefined) {
    spans.push({ ...current })
  }
  return spans
}
