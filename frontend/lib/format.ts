/**
 * The few formatting rules the screens share, so a date or a language pair reads the same
 * on the tender list, the workspace header and a citation. English UI, precise numbers,
 * no locale guessing: `en-GB` is fixed so the server and the browser agree.
 */

const DATE_TIME = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})

/** "11 Sept 2026, 14:32", or an em dash when the API sent no timestamp. */
export function formatDateTime(iso: string | null | undefined): string {
  if (iso === null || iso === undefined) {
    return '—'
  }
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? '—' : DATE_TIME.format(date)
}

const TIME_ONLY = new Intl.DateTimeFormat('en-GB', {
  hour: '2-digit',
  minute: '2-digit',
})

/**
 * "14:32" on the bidder's own clock — for a moment inside the current hour, such as when
 * a rate limit lifts, where the date would be noise.
 */
export function formatTime(date: Date): string {
  return Number.isNaN(date.getTime()) ? '—' : TIME_ONLY.format(date)
}

const DATE_ONLY = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
})

/**
 * "7 Oct 2026", or an em dash when there is no date.
 *
 * Separate from `formatDateTime` because a TED deadline genuinely has no time of day — the
 * hour comes from the notice or the bidder (ADR-0043) — and rendering one as midnight would
 * put an hour on the screen that nobody published. Parsed as UTC rather than as a local
 * timestamp: `new Date('2026-10-07')` is midnight UTC, which is the *previous day* west of
 * Greenwich, so the date is split rather than handed to the browser's timezone.
 */
export function formatDate(iso: string | null | undefined): string {
  if (iso === null || iso === undefined) {
    return '—'
  }
  const [year, month, day] = iso.slice(0, 10).split('-').map(Number)
  if (year === undefined || month === undefined || day === undefined) {
    return '—'
  }
  const date = new Date(Date.UTC(year, month - 1, day))
  return Number.isNaN(date.getTime()) ? '—' : DATE_ONLY.format(date)
}

/** "fr" → "FR"; unknown → "—". */
export function formatLanguage(code: string | null | undefined): string {
  return code === null || code === undefined || code.length === 0 ? '—' : code.toUpperCase()
}

/** "FR → DE", or just "DE" when the tender is already in the bidder's language. */
export function formatLanguagePair(source: string | null | undefined, bidder: string): string {
  const from = formatLanguage(source)
  const to = formatLanguage(bidder)
  return from === to || from === '—' ? to : `${from} → ${to}`
}

/** "Page 19", "Pages 19 and 23", "Pages 1, 2 and 3". Empty input gives an empty string. */
export function formatPageList(pages: readonly number[]): string {
  if (pages.length === 0) {
    return ''
  }
  if (pages.length === 1) {
    return `Page ${pages[0]}`
  }
  const head = pages.slice(0, -1).join(', ')
  return `Pages ${head} and ${pages[pages.length - 1]}`
}

export const CITATION_NAME_CHARS = 10
export const TAB_NAME_CHARS = 18

/**
 * A filename short enough for a citation or a document tab: the extension dropped, the
 * middle elided once it passes `maxChars`. The full name stays in the accessible label.
 */
export function shortDocumentName(name: string, maxChars = TAB_NAME_CHARS): string {
  const stem = name.replace(/\.[A-Za-z0-9]{1,5}$/, '')
  if (stem.length <= maxChars) {
    return stem
  }
  const keep = Math.floor((maxChars - 1) / 2)
  return `${stem.slice(0, keep)}…${stem.slice(-keep)}`
}

/** "REQ-001" for the first row — a display index, not the requirement's uuid5 id. */
export function requirementLabel(index: number): string {
  return `REQ-${String(index + 1).padStart(3, '0')}`
}

/** "1 page" / "25 pages", and so on for any unit. */
export function plural(count: number, unit: string, pluralUnit = `${unit}s`): string {
  return `${count} ${count === 1 ? unit : pluralUnit}`
}

const REGION_NAMES = safeRegionNames()

function safeRegionNames(): Intl.DisplayNames | undefined {
  try {
    return new Intl.DisplayNames(['en-GB'], { type: 'region' })
  } catch {
    return undefined
  }
}

/**
 * "de" → "Germany", for the eCertis card's sentence. Falls back to the uppercase code when
 * the runtime cannot name the region, so the card never renders an empty country.
 */
export function formatCountry(code: string | null | undefined): string {
  if (code === null || code === undefined || code.length !== 2) {
    return formatLanguage(code)
  }
  const upper = code.toUpperCase()
  try {
    return REGION_NAMES?.of(upper) ?? upper
  } catch {
    return upper
  }
}

/** "a, b and c" — the list form the evidence and issuer lines use. */
export function formatList(items: readonly string[]): string {
  if (items.length <= 1) {
    return items[0] ?? ''
  }
  return `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`
}
