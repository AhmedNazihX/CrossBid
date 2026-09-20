/**
 * Answers for the fake API, typed from the generated schema (`lib/api.ts`).
 *
 * Every builder returns a complete `components['schemas'][…]` object, so a field the backend
 * renames or adds stops these tests compiling — the same guarantee `lib/*.ts` has, and the
 * reason the fake can stand in for the API without drifting from it. The values are the
 * DE fixture's vocabulary (`backend/tests/fixtures/tenders/de`), so a screenshot reads like
 * the product rather than like a test.
 */
import type { components } from '@/lib/api'

type Schemas = components['schemas']

export type DocumentResponse = Schemas['DocumentResponse']
export type BidResponse = Schemas['BidResponse']
export type BidSummary = Schemas['BidSummary']
export type CompanyProfileResponse = Schemas['CompanyProfileResponse']
export type DocumentKind = Schemas['DocumentKind']
export type BidDocumentResponse = Schemas['BidDocumentResponse']

/** The tenant the e2e server is built with (`NEXT_PUBLIC_DEV_COMPANY_ID`); the fake never checks it. */
export const E2E_COMPANY_ID = '11111111-1111-4111-8111-111111111111'
export const BID_ID = '22222222-2222-4222-8222-222222222222'
export const DOCUMENT_ID = '33333333-3333-4333-8333-333333333333'
/** A second document, for the tests that need two pages of them. */
export const SECOND_DOCUMENT_ID = '33333333-3333-4333-8333-333333333334'
const REQUIREMENT_ID = '44444444-4444-4444-8444-444444444444'
const MATRIX_ROW_ID = '55555555-5555-4555-8555-555555555555'

const CREATED_AT = '2026-09-16T08:00:00Z'
const NOTICE_NUMBER = '614251-2026'

export function documentFixture(
  overrides: Partial<DocumentResponse> & Pick<DocumentResponse, 'id' | 'name'>
): DocumentResponse {
  return {
    kind: 'tender_document',
    bid_count: 0,
    status: 'ready',
    failure_reason: null,
    pages: 12,
    unread_pages: [],
    unread_page_count: 0,
    flagged_chunks: [],
    flagged_chunk_count: 0,
    created_at: CREATED_AT,
    updated_at: CREATED_AT,
    ...overrides,
  }
}

export function companyProfileFixture(): CompanyProfileResponse {
  return {
    name: 'Beispiel IT Services GmbH',
    country: 'de',
    legal_form: 'gmbh',
    registration_number: 'HRB 84512',
    registration_court: 'Amtsgericht Berlin-Charlottenburg',
    language: 'de',
    tone: 'plain',
    staff_fte: 42,
    staff_fte_relevant: 30,
    turnover: [],
    certificates: [],
    has_expired_certificates: false,
    checked_on: '2026-09-16',
    warning: null,
  }
}

/**
 * The DE pack's files (`backend/tests/fixtures/tenders/de/documents`), as the bid lists them.
 *
 * These are what put the desktop's right column under height pressure: the Source panel it
 * opens with frames the current document at a fixed 560 px and draws a chip per file above
 * it, and the chips wrap into rows. With the whole pack the column's content exceeds its
 * `max-h-[calc(100dvh-2rem)]` at 1440×900 — which is the precondition for the tab strip to
 * collapse at all (see `bid-workspace.spec.ts`). A bid with no documents never squeezes it.
 */
const DE_PACK_FILES: readonly string[] = [
  'Aufforderungsschreiben_VV2_V1.pdf',
  'Besondere_Bewerbungsbedingungen_VV2_V1.pdf',
  'Allgemeine_Bewerbungsbedingungen_elektronisch.pdf',
  'Anlage_Unternehmensdaten_VV2.pdf',
  'EVB_IT_Dienstleistung_Muster1_Leistungsnachweis_VV2_V1.pdf',
  'Liste_Bedarfstraeger_VV2_V1.pdf',
  'Leistungsbeschreibung_VV2_V1.pdf',
  'Preisblatt_VV2_V1.pdf',
  'Eigenerklaerung_Ausschlussgruende_VV2_V1.pdf',
  'Verpflichtungserklaerung_Nachunternehmer_VV2_V1.pdf',
  'Erklaerung_Bietergemeinschaft_VV2_V1.pdf',
  'AGB.pdf',
]

export function packDocumentsFixture(
  { searchable }: { readonly searchable: boolean } = { searchable: true }
): readonly BidDocumentResponse[] {
  return DE_PACK_FILES.map((name, index) => ({
    id: `77777777-7777-4777-8777-${String(index + 1).padStart(12, '0')}`,
    name,
    pages: 4 + index * 3,
    unread_pages: [],
    // A healthy bid by default: its pack was indexed while it was analysed. `false` is a bid
    // from before 2026-09-15, whose documents were parsed and never kept (ADR-0098) — the
    // state the workspace now says out loud instead of leaving Ask to refuse and be blamed.
    searchable,
  }))
}

/**
 * A bid parked at its interrupt with the agent's verdict written — the one state in which
 * the header's "Review verdict" control is an enabled anchor and the desktop column carries
 * its Verdict tab (`bid-workspace.tsx`). One requirement and one row, so the matrix renders a
 * real row rather than its empty message, and the DE pack as its documents, so the Source
 * panel is the real, tall thing it is on a real bid (`packDocumentsFixture`).
 */
export function awaitingReviewBidFixture(overrides: Partial<BidResponse> = {}): BidResponse {
  return {
    id: BID_ID,
    notice_number: NOTICE_NUMBER,
    title: 'Rahmenvertrag IT-Dienstleistungen VV2',
    source_language: 'de',
    bidder_language: 'de',
    status: 'awaiting_review',
    failure_reason: null,
    requirements: [
      {
        id: REQUIREMENT_ID,
        bid_id: BID_ID,
        category: 'economic_financial',
        kind: 'mandatory',
        stage: 'bid_eligibility',
        checkable: 'company_property',
        source: 'tender_document',
        source_text:
          'Der Bieter hat einen Mindestjahresumsatz von 2 Mio. EUR in den letzten drei Geschäftsjahren nachzuweisen.',
        source_lang: 'de',
        document_name: 'Besondere_Bewerbungsbedingungen_VV2_V1.pdf',
        page: 4,
        translation: null,
        ecertis_criterion_id: '499efc97-2ac1-4af2-9e84-323c2ca67747',
      },
    ],
    matrix_rows: [
      {
        id: MATRIX_ROW_ID,
        requirement_id: REQUIREMENT_ID,
        status: 'partially_supported',
        evidence: [],
        ecertis_evidence: null,
        agent_rationale: 'Turnover is stated for two of the three years the buyer asks for.',
        agent_status: 'partially_supported',
        reviewer_status: 'pending',
        override_reason: null,
        attached_doc_ids: [],
        reviewed_at: null,
      },
    ],
    verdict: {
      decision: 'conditional',
      gaps: [
        {
          requirement_id: REQUIREMENT_ID,
          severity: 'open_item',
          summary: 'One turnover year is not evidenced.',
          required: 'Three fiscal years',
          actual: 'Two fiscal years',
        },
      ],
      score: null,
      rationale: 'Every mandatory requirement is at least partially supported.',
      mandatory_total: 1,
      mandatory_supported: 0,
      partially_supported_rows: 1,
    },
    decision: null,
    problems: [],
    documents: [...packDocumentsFixture()],
    created_at: CREATED_AT,
    updated_at: CREATED_AT,
    ...overrides,
  }
}

/** The 202 body `POST /bids` answers with: nothing extracted yet, nothing to review. */
export function queuedBidFixture(overrides: Partial<BidResponse> = {}): BidResponse {
  return {
    ...awaitingReviewBidFixture(),
    status: 'queued',
    requirements: [],
    matrix_rows: [],
    verdict: null,
    ...overrides,
  }
}

export function bidSummaryFixture(overrides: Partial<BidSummary> = {}): BidSummary {
  return {
    id: BID_ID,
    company_id: E2E_COMPANY_ID,
    ted_publication_number: NOTICE_NUMBER,
    title: 'Rahmenvertrag IT-Dienstleistungen VV2',
    buyer: 'Bundesverwaltungsamt',
    source_language: 'de',
    deadline: '2026-10-07T12:00:00+02:00',
    deadline_utc_offset_minutes: 120,
    status: 'awaiting_review',
    decision: null,
    open_items: 3,
    created_at: CREATED_AT,
    updated_at: CREATED_AT,
    ...overrides,
  }
}
