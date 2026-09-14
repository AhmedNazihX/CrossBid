/**
 * Typed calls for the `/companies` routes, and the create-or-update rule (story S4.2.1).
 *
 * The types come from the generated schema, so a field the backend renames stops compiling
 * here rather than failing at run time.
 *
 * **Two routes, one form.** A signed-in bidder who has never filled this in has no company
 * row at all — `owner_user_id` is `NOT NULL`, so a company arrives with its owner or not at
 * all (S0.3.1) — and every other route answers 404 until one exists. `POST /companies`
 * creates it from the verified token; `PUT /companies/me` replaces the profile afterwards.
 * The form does not ask which: `saveProfile` sends the create when the load came back
 * empty, because "have you been here before" is not a question to put to a person.
 */
import type { components } from './api'
import { ApiError, apiRequest } from './api-client'

export type CompanyProfile = components['schemas']['CompanyProfile']
export type CompanyProfileResponse = components['schemas']['CompanyProfileResponse']
export type LegalForm = components['schemas']['LegalForm']
export type Tone = components['schemas']['Tone']
export type TurnoverYear = components['schemas']['TurnoverYear']
export type CertificateHeld = components['schemas']['CertificateHeld']

/** The legal forms the column's check constraint allows, in the order the select offers them. */
export const LEGAL_FORMS: readonly LegalForm[] = [
  'gmbh',
  'ug',
  'ag',
  'sarl',
  'sas',
  'sa',
  'bv',
  'sp_zoo',
  'sole_trader',
  'other',
]

/** German first: the demo company is a German GmbH and the wedge is a German bidder. */
export const LEGAL_FORM_LABELS: Readonly<Record<LegalForm, string>> = {
  gmbh: 'GmbH',
  ug: 'UG (haftungsbeschränkt)',
  ag: 'AG',
  sarl: 'SARL',
  sas: 'SAS',
  sa: 'SA',
  bv: 'BV',
  sp_zoo: 'Sp. z o.o.',
  sole_trader: 'Sole trader',
  other: 'Other',
}

export const TONES: readonly Tone[] = ['plain', 'formal', 'brief']

/** What each tone does to an explanation, said in the words the bidder will recognise. */
export const TONE_LABELS: Readonly<Record<Tone, string>> = {
  plain: 'Plain — everyday words, no legal register',
  formal: 'Formal — the register a procurement office writes in',
  brief: 'Brief — the shortest form that still cites its source',
}

/**
 * The languages an explanation can be written in.
 *
 * Deliberately short, and deliberately not a list of every BCP 47 tag: the column takes any
 * string, but offering 300 of them would suggest the agent has been tested in 300. These
 * are the three the golden tenders cover (ADR-0002).
 */
export const EXPLANATION_LANGUAGES: readonly {
  readonly code: string
  readonly label: string
}[] = [
  { code: 'de', label: 'German' },
  { code: 'en', label: 'English' },
  { code: 'fr', label: 'French' },
]

/** The profile a company starts from: the defaults the backend model already declares. */
export const EMPTY_PROFILE: CompanyProfile = {
  name: '',
  country: 'de',
  legal_form: 'gmbh',
  registration_number: null,
  registration_court: null,
  language: 'de',
  tone: 'plain',
  staff_fte: null,
  staff_fte_relevant: null,
  turnover: [],
  certificates: [],
}

export interface LoadedProfile {
  /** `undefined` when this account has no company yet, which is the onboarding case. */
  readonly profile: CompanyProfileResponse | undefined
}

/**
 * The profile, or `undefined` when there is no company yet.
 *
 * 404 is not an error here: it is the answer for a bidder who has signed in and not yet
 * said who they are, and it is what decides whether the form creates or replaces.
 */
export async function loadProfile(signal?: AbortSignal): Promise<LoadedProfile> {
  try {
    return { profile: await apiRequest('get', '/companies/me', { signal }) }
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return { profile: undefined }
    throw error
  }
}

/** Create the company, or replace its profile when one already exists. */
export async function saveProfile(
  profile: CompanyProfile,
  { exists }: { readonly exists: boolean }
): Promise<CompanyProfileResponse> {
  return exists
    ? apiRequest('put', '/companies/me', { body: profile })
    : apiRequest('post', '/companies', { body: profile })
}

/** The profile fields, stripped of the response-only ones, ready to send back. */
export function editableProfile(saved: CompanyProfileResponse): CompanyProfile {
  return {
    name: saved.name,
    country: saved.country,
    legal_form: saved.legal_form,
    registration_number: saved.registration_number,
    registration_court: saved.registration_court,
    language: saved.language,
    tone: saved.tone,
    staff_fte: saved.staff_fte,
    staff_fte_relevant: saved.staff_fte_relevant,
    turnover: saved.turnover.map((entry) => ({ ...entry })),
    certificates: saved.certificates.map((held) => ({
      name: held.name,
      issuer: held.issuer,
      number: held.number,
      issued_on: held.issued_on,
      expires_on: held.expires_on,
      scope: held.scope,
    })),
  }
}
