/**
 * S7.4 — the stills the user guide is built around.
 *
 * Not tests, though they would fail like tests if a screen stopped rendering: each one drives
 * the real app to a screen, waits for the thing the guide's paragraph talks about, and writes
 * a PNG into `docs/user-guide/img/`. The `consoleErrors` guard from `e2e/support/test.ts` runs
 * here too, so a screen that paints and logs an error cannot become a screenshot.
 *
 * The data is richer than the suite's, on purpose. A matrix with one row shows nothing about
 * reading a matrix, and the guide's whole job is to teach someone to read one — so the bid
 * below carries a supported row, a partially supported one and an unsupported one, which is
 * also the shape that makes the verdict `conditional` for a reason a reader can follow.
 */
import { mkdir } from 'node:fs/promises'
import path from 'node:path'

import {
  awaitingReviewBidFixture,
  bidSummaryFixture,
  companyProfileFixture,
  documentFixture,
  packDocumentsFixture,
  BID_ID,
} from '../e2e/support/fixtures'
import { expect, test } from '../e2e/support/test'

const SHOTS = path.resolve(__dirname, '../../docs/user-guide/img')

const REQ = {
  turnover: '44444444-4444-4444-8444-444444444444',
  iso: '77777777-7777-4777-8777-777777777777',
  references: '88888888-8888-4888-8888-888888888888',
}
const ROW = {
  turnover: '55555555-5555-4555-8555-555555555555',
  iso: '99999999-9999-4999-8999-999999999999',
  references: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
}

/** The bidder's own evidence pack, as the company screen lists it. */
function evidenceDocuments() {
  return [
    documentFixture({
      id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
      name: 'Zertifikat_ISO_IEC_27001_2022.pdf',
      kind: 'company_evidence',
    }),
    documentFixture({
      id: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
      name: 'Handelsregisterauszug_HRB_84512.pdf',
      kind: 'company_evidence',
    }),
    documentFixture({
      id: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
      name: 'Jahresabschluss_2025.pdf',
      kind: 'company_evidence',
    }),
  ]
}

/** The guide's bid: three requirements, three row statuses, one open item. */
function guideBid() {
  const base = awaitingReviewBidFixture()
  const [turnover] = base.requirements
  return awaitingReviewBidFixture({
    title: 'Rahmenvertrag IT-Dienstleistungen VV2 — Los 2',
    requirements: [
      turnover,
      {
        ...turnover,
        id: REQ.iso,
        category: 'technical_professional',
        source_text:
          'Der Bieter hat ein zertifiziertes Informationssicherheits-Managementsystem nach ISO/IEC 27001 nachzuweisen.',
        document_name: 'Kriterienkatalog_Eignung.pdf',
        page: 6,
        ecertis_criterion_id: null,
      },
      {
        ...turnover,
        id: REQ.references,
        category: 'technical_professional',
        source_text:
          'Es sind mindestens drei vergleichbare Referenzprojekte aus den letzten drei Jahren zu benennen.',
        document_name: 'Kriterienkatalog_Eignung.pdf',
        page: 7,
        ecertis_criterion_id: null,
      },
    ],
    matrix_rows: [
      {
        ...base.matrix_rows[0],
        id: ROW.iso,
        requirement_id: REQ.iso,
        status: 'supported',
        agent_status: 'supported',
        agent_rationale:
          'Zertifikat_ISO_IEC_27001_2022.pdf names the company and is valid until 2027-03-14.',
      },
      { ...base.matrix_rows[0], id: ROW.turnover, requirement_id: REQ.turnover },
      {
        ...base.matrix_rows[0],
        id: ROW.references,
        requirement_id: REQ.references,
        status: 'unsupported',
        agent_status: 'unsupported',
        agent_rationale:
          'No reference project from the last three years was found in the company documents.',
      },
    ],
    verdict: {
      decision: 'conditional',
      gaps: [
        {
          requirement_id: REQ.turnover,
          severity: 'open_item',
          summary: 'One turnover year is not evidenced.',
          required: 'Three fiscal years',
          actual: 'Two fiscal years',
        },
        {
          requirement_id: REQ.references,
          severity: 'open_item',
          summary: 'No comparable reference project was found.',
          required: 'Three references from the last three years',
          actual: 'None found',
        },
      ],
      score: null,
      rationale:
        'One requirement is fully supported, one is partially supported and one is not supported. A reviewer decides whether the missing references can be produced before the deadline.',
      mandatory_total: 3,
      mandatory_supported: 1,
      partially_supported_rows: 1,
    },
  })
}

/** The wedge: a French tender, a German bidder, every row explained in German. */
function crossBorderBid() {
  const base = guideBid()
  const [turnover] = base.requirements
  return awaitingReviewBidFixture({
    title: 'Prestations de conseil en architecture d’entreprise',
    notice_number: '618320-2026',
    source_language: 'fr',
    bidder_language: 'de',
    requirements: [
      {
        ...turnover,
        source_text:
          'Le candidat doit justifier d’un chiffre d’affaires annuel minimal de 3 000 000 EUR sur les trois derniers exercices.',
        source_lang: 'fr',
        document_name: '26023_AOO_Conseil_Architecure_SI_RC_v1.pdf',
        page: 13,
        translation:
          'Der Bieter muss einen Mindestjahresumsatz von 3 Mio. EUR in den letzten drei Geschäftsjahren nachweisen.',
      },
    ],
    matrix_rows: [base.matrix_rows[1]],
    verdict: {
      decision: 'conditional',
      gaps: [
        {
          requirement_id: REQ.turnover,
          severity: 'open_item',
          summary: 'One turnover year is not evidenced.',
          required: 'Three fiscal years',
          actual: 'Two fiscal years',
        },
      ],
      score: null,
      rationale:
        'Der Mindestumsatz ist für zwei der drei geforderten Geschäftsjahre belegt. Eine Prüferin entscheidet, ob der dritte Nachweis vor Fristende beigebracht werden kann.',
      mandatory_total: 1,
      mandatory_supported: 0,
      partially_supported_rows: 1,
    },
  })
}

/** The measured no-go: the committed demo company against the real DE tender.
 *
 * The figures are the ones `tests/fixtures/bids/de.qualified.json` recorded on 2026-09-16 —
 * the bidder has 21.5 relevant FTE and the buyer's minimum is 25 (Los 1) / 29 (Los 2), so a
 * mandatory row is unsupported and the bid is blocked. It is the tender's staff requirement
 * and not its turnover requirement, because that is what the run actually found (ADR-0073).
 */
function noGoBid() {
  const base = guideBid()
  const [turnover] = base.requirements
  const staff = {
    ...turnover,
    id: REQ.references,
    category: 'technical_professional' as const,
    source_text:
      'Die durchschnittliche Zahl der Fachkräfte im einschlägigen Geschäftsbereich muss pro Geschäftsjahr mindestens 25 VZÄ für Los 1 bzw. 29 VZÄ für Los 2 betragen.',
    document_name: 'Kriterienkatalog_Eignung.pdf',
    page: 5,
  }
  return awaitingReviewBidFixture({
    title: 'Rahmenvertrag IT-Dienstleistungen VV2 — Los 2',
    requirements: [staff],
    matrix_rows: [
      {
        ...base.matrix_rows[0],
        requirement_id: REQ.references,
        status: 'unsupported',
        agent_status: 'unsupported',
        agent_rationale:
          'Die Eigenerklärung nennt 21,5 VZÄ Fachkräfte im einschlägigen Geschäftsbereich. Der Auftraggeber verlangt mindestens 29 VZÄ für Los 2.',
      },
    ],
    verdict: {
      decision: 'no_go',
      gaps: [
        {
          requirement_id: REQ.references,
          severity: 'blocking',
          summary:
            'Die Mindestzahl an Fachkräften im einschlägigen Geschäftsbereich wird nicht erreicht.',
          required: '29 VZÄ (Los 2)',
          actual: '21,5 VZÄ',
        },
      ],
      score: null,
      rationale:
        'Eine zwingende Anforderung ist nicht belegt: die Zahl der Fachkräfte liegt unter dem geforderten Mindestwert. Eine Prüferin entscheidet, ob die Angabe veraltet ist oder die Ausschreibung außer Reichweite liegt.',
      mandatory_total: 1,
      mandatory_supported: 0,
      partially_supported_rows: 0,
    },
  })
}

test.beforeAll(async () => {
  await mkdir(SHOTS, { recursive: true })
})

test('01 — the company profile', async ({ api, page }) => {
  api.on('GET', '/companies/me', { status: 200, json: companyProfileFixture() })
  api.on('GET', '/documents', { status: 200, json: { documents: evidenceDocuments() } })

  await page.goto('/company')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await expect(page.locator('input[value="Beispiel IT Services GmbH"]')).toBeVisible()

  await page.screenshot({ path: path.join(SHOTS, '01-company-profile.png'), fullPage: true })
})

test('02 — the dashboard', async ({ api, page }) => {
  api.on('GET', '/bids', {
    status: 200,
    json: {
      bids: [
        bidSummaryFixture(),
        bidSummaryFixture({
          id: '66666666-6666-4666-8666-666666666666',
          ted_publication_number: '618320-2026',
          title: 'Prestations de conseil en architecture d’entreprise',
          buyer: 'Ministère de l’éducation nationale',
          source_language: 'fr',
          status: 'complete',
          decision: 'go',
          open_items: 0,
        }),
      ],
    },
  })

  await page.goto('/dashboard')
  await expect(page.getByRole('heading', { level: 1, name: 'Dashboard' })).toBeVisible()

  await page.screenshot({ path: path.join(SHOTS, '02-dashboard.png'), fullPage: true })
})

test('03 — the requirement matrix, parked for review', async ({ api, page }) => {
  api.on('GET', new RegExp(`/bids/${BID_ID}$`), { status: 200, json: guideBid() })
  api.on('GET', new RegExp(`/bids/${BID_ID}/documents$`), {
    status: 200,
    json: { documents: packDocumentsFixture() },
  })
  api.on('GET', '/documents', { status: 200, json: { documents: evidenceDocuments() } })
  api.on('GET', '/companies/me', { status: 200, json: companyProfileFixture() })
  // The workspace signs every pack document for the source panel and reads the row's ratings.
  api.on('GET', /\/documents\/[0-9a-f-]+\/url$/, {
    status: 200,
    json: { url: 'about:blank', expires_in: 600 },
  })
  api.on('GET', new RegExp(`/bids/${BID_ID}/feedback$`), {
    status: 200,
    json: { feedback: [] },
  })

  await page.goto(`/bids/${BID_ID}`)
  await expect(page.getByText('Rahmenvertrag IT-Dienstleistungen VV2 — Los 2')).toBeVisible()

  await page.screenshot({ path: path.join(SHOTS, '03-matrix.png'), fullPage: true })
})

test('04 — the verdict and its open items', async ({ api, page }) => {
  api.on('GET', new RegExp(`/bids/${BID_ID}$`), { status: 200, json: guideBid() })
  api.on('GET', new RegExp(`/bids/${BID_ID}/documents$`), {
    status: 200,
    json: { documents: packDocumentsFixture() },
  })
  api.on('GET', '/documents', { status: 200, json: { documents: evidenceDocuments() } })
  api.on('GET', '/companies/me', { status: 200, json: companyProfileFixture() })
  api.on('GET', /\/documents\/[0-9a-f-]+\/url$/, {
    status: 200,
    json: { url: 'about:blank', expires_in: 600 },
  })
  api.on('GET', new RegExp(`/bids/${BID_ID}/feedback$`), {
    status: 200,
    json: { feedback: [] },
  })

  await page.goto(`/bids/${BID_ID}`)
  // The right-hand panel opens on Source; the verdict is a tab, so the shot has to ask for
  // it. Without this, 03 and 04 are the same image — which is how the first run came out.
  await page.getByRole('tab', { name: 'Verdict' }).click()
  await expect(page.getByText(/mandatory requirements supported/i).first()).toBeVisible()

  await page.screenshot({ path: path.join(SHOTS, '04-verdict.png'), fullPage: true })
})

test('06 — a French tender read in German', async ({ api, page }) => {
  const bid = crossBorderBid()
  api.on('GET', new RegExp(`/bids/${BID_ID}$`), { status: 200, json: bid })
  api.on('GET', new RegExp(`/bids/${BID_ID}/documents$`), {
    status: 200,
    json: { documents: packDocumentsFixture() },
  })
  api.on('GET', '/documents', { status: 200, json: { documents: evidenceDocuments() } })
  api.on('GET', '/companies/me', { status: 200, json: companyProfileFixture() })
  api.on('GET', /\/documents\/[0-9a-f-]+\/url$/, {
    status: 200,
    json: { url: 'about:blank', expires_in: 600 },
  })
  api.on('GET', new RegExp(`/bids/${BID_ID}/feedback$`), {
    status: 200,
    json: { feedback: [] },
  })

  await page.goto(`/bids/${BID_ID}`)
  await expect(page.getByText(/Mindestjahresumsatz von 3 Mio/)).toBeVisible()

  await page.screenshot({ path: path.join(SHOTS, '06-cross-border.png'), fullPage: true })
})

test('05 — starting a bid from a TED notice', async ({ api, page }) => {
  api.on('GET', '/companies/me', { status: 200, json: companyProfileFixture() })
  api.on('GET', '/documents', { status: 200, json: { documents: [] } })

  await page.goto('/bids/new')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()

  await page.screenshot({ path: path.join(SHOTS, '05-start-a-bid.png'), fullPage: true })
})

test('07 — a bid the agent recommends against', async ({ api, page }) => {
  api.on('GET', new RegExp(`/bids/${BID_ID}$`), { status: 200, json: noGoBid() })
  api.on('GET', new RegExp(`/bids/${BID_ID}/documents$`), {
    status: 200,
    json: { documents: packDocumentsFixture() },
  })
  api.on('GET', '/documents', { status: 200, json: { documents: evidenceDocuments() } })
  api.on('GET', '/companies/me', { status: 200, json: companyProfileFixture() })
  api.on('GET', /\/documents\/[0-9a-f-]+\/url$/, {
    status: 200,
    json: { url: 'about:blank', expires_in: 600 },
  })
  api.on('GET', new RegExp(`/bids/${BID_ID}/feedback$`), {
    status: 200,
    json: { feedback: [] },
  })

  await page.goto(`/bids/${BID_ID}`)
  await expect(page.getByText(/no.go/i).first()).toBeVisible()

  await page.screenshot({ path: path.join(SHOTS, '07-no-go.png'), fullPage: true })
})
