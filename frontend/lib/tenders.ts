/**
 * Typed calls for `/tenders/search` (story S4.3.1, over S1.2.1's route).
 *
 * The types come from the generated schema, so a field the backend renames stops compiling
 * here. There is no TED-specific logic in this file on purpose: the expert-query rules, the
 * language resolution and the retry all live in `reference/ted_client.py`, tested once,
 * rather than being half-reimplemented in TypeScript (ADR-0043).
 */
import type { components } from './api'
import { apiRequest } from './api-client'

export type TedNotice = components['schemas']['TedNotice']
export type TedSearchPage = components['schemas']['TedSearchPage']

export interface TenderSearchFilters {
  readonly cpv: readonly string[]
  readonly countries: readonly string[]
  readonly keyword: string
}

/** Eight digits, the only shape TED accepts — `IN (72)` is a 400 (ADR-0043). */
export const CPV_PATTERN = /^\d{8}$/

/**
 * A short list of CPV divisions rather than the whole 9 454-code taxonomy.
 *
 * The full vocabulary is a searchable tree in its own right, and offering it as a select
 * would be a worse version of TED's own portal — which is the thing this screen exists to
 * save the bidder from. These are the divisions an IT services bidder actually competes in,
 * and the field accepts any eight digits typed directly for everything else.
 */
export const CPV_SUGGESTIONS: readonly { readonly code: string; readonly label: string }[] = [
  { code: '72000000', label: 'IT services: consulting, software, internet and support' },
  { code: '48000000', label: 'Software package and information systems' },
  { code: '79000000', label: 'Business services: law, marketing, consulting' },
  { code: '71000000', label: 'Architectural, construction and engineering services' },
  { code: '73000000', label: 'Research and development services' },
  { code: '80000000', label: 'Education and training services' },
]

export async function searchTenders(
  filters: TenderSearchFilters,
  options: {
    readonly language?: string
    readonly limit?: number
    readonly signal?: AbortSignal
  } = {}
): Promise<TedSearchPage> {
  return apiRequest('get', '/tenders/search', {
    query: {
      cpv: [...filters.cpv],
      country: [...filters.countries],
      keyword: filters.keyword.trim() === '' ? undefined : filters.keyword.trim(),
      limit: options.limit ?? 20,
      language: options.language,
    },
    signal: options.signal,
  })
}

/**
 * The source language to start the bid in, from what TED says the notice is written in.
 *
 * `StartBidForm` offers the three the golden tenders cover, so a notice in Polish falls back
 * to French rather than to a language the extractor has never been measured on — and the
 * bidder can change it, because they can see the notice and we cannot.
 */
export function sourceLanguageOf(notice: TedNotice): 'fr' | 'de' | 'en' {
  const first = notice.official_languages[0]?.toLowerCase()
  if (first === 'deu' || first === 'ger') return 'de'
  if (first === 'eng') return 'en'
  return 'fr'
}

/**
 * ISO alpha-3 → the alpha-2 the rest of the app speaks, and the name a bidder reads.
 *
 * Alpha-3 is the key because that is what TED sends and **the codes that matter most are not
 * all EU**: the notice that provoked ADR-0111 is bought in `GBR`. Keying on the app's
 * `BIDDER_COUNTRIES` instead would have resolved every country a bidder can search for and
 * blanked exactly the ones they cannot, which is the opposite of useful here.
 */
const COUNTRIES: Readonly<Record<string, { readonly alpha2: string; readonly label: string }>> =
  {
    AUT: { alpha2: 'at', label: 'Austria' },
    BEL: { alpha2: 'be', label: 'Belgium' },
    BGR: { alpha2: 'bg', label: 'Bulgaria' },
    HRV: { alpha2: 'hr', label: 'Croatia' },
    CYP: { alpha2: 'cy', label: 'Cyprus' },
    CZE: { alpha2: 'cz', label: 'Czechia' },
    DNK: { alpha2: 'dk', label: 'Denmark' },
    EST: { alpha2: 'ee', label: 'Estonia' },
    FIN: { alpha2: 'fi', label: 'Finland' },
    FRA: { alpha2: 'fr', label: 'France' },
    DEU: { alpha2: 'de', label: 'Germany' },
    GRC: { alpha2: 'gr', label: 'Greece' },
    HUN: { alpha2: 'hu', label: 'Hungary' },
    IRL: { alpha2: 'ie', label: 'Ireland' },
    ITA: { alpha2: 'it', label: 'Italy' },
    LVA: { alpha2: 'lv', label: 'Latvia' },
    LTU: { alpha2: 'lt', label: 'Lithuania' },
    LUX: { alpha2: 'lu', label: 'Luxembourg' },
    MLT: { alpha2: 'mt', label: 'Malta' },
    NLD: { alpha2: 'nl', label: 'Netherlands' },
    POL: { alpha2: 'pl', label: 'Poland' },
    PRT: { alpha2: 'pt', label: 'Portugal' },
    ROU: { alpha2: 'ro', label: 'Romania' },
    SVK: { alpha2: 'sk', label: 'Slovakia' },
    SVN: { alpha2: 'si', label: 'Slovenia' },
    ESP: { alpha2: 'es', label: 'Spain' },
    SWE: { alpha2: 'se', label: 'Sweden' },
    // Not EU members, and every one of them appears as a buyer on EU notices.
    GBR: { alpha2: 'gb', label: 'United Kingdom' },
    NOR: { alpha2: 'no', label: 'Norway' },
    CHE: { alpha2: 'ch', label: 'Switzerland' },
    ISL: { alpha2: 'is', label: 'Iceland' },
    TUR: { alpha2: 'tr', label: 'Türkiye' },
    UKR: { alpha2: 'ua', label: 'Ukraine' },
    SRB: { alpha2: 'rs', label: 'Serbia' },
    USA: { alpha2: 'us', label: 'United States' },
  }

/** The country's English name, or the code itself when it is one we do not carry. */
export function countryNameOf(alpha3: string): string {
  const code = alpha3.trim().toUpperCase()
  return COUNTRIES[code]?.label ?? code
}

/**
 * Is this notice bought somewhere other than the country the bidder searched on?
 *
 * The search filters on `place-of-performance`, which is a *list* — a pan-European framework
 * is performed in France and bought in London, and answers a France search honestly. That is
 * not a bug, but it is invisible, so the card says so. A notice naming no buyer country is
 * not foreign; it is unknown, and unknown is not a warning.
 */
export function isBoughtElsewhere(notice: TedNotice, searchedAlpha2: string): boolean {
  const searched = searchedAlpha2.trim().toLowerCase()
  if (notice.buyer_countries.length === 0 || searched === '') return false
  return !notice.buyer_countries.some(
    (alpha3) => COUNTRIES[alpha3.trim().toUpperCase()]?.alpha2 === searched
  )
}

/**
 * Has the deadline already passed?
 *
 * **A notice with no published deadline is not closed** — we do not know, and saying
 * otherwise would repeat the "open notices" claim this replaces. Only 170 of 521 recent
 * French CPV-72 contract notices carry a lot-level deadline at all (ADR-0111), so silence
 * is the common case, not the odd one.
 *
 * Compared as dates and in UTC, because TED publishes a deadline with no time of day. UTC
 * makes it deterministic, and it errs towards *not* calling a notice closed — the only safe
 * direction when the alternative is telling a bidder to skip a tender they could still win.
 * A deadline falling today is open: the bidder still has the day.
 */
export function isNoticeClosed(notice: TedNotice, now: Date = new Date()): boolean {
  return notice.deadline !== null && notice.deadline < now.toISOString().slice(0, 10)
}
