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
