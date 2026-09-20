/**
 * The new-bid flow — `/bids/new`, steps 2 and 3 (S7.7; blockers 1 and 2 of the 2026-09-15
 * audit).
 *
 * **Blocker 1 — a file uploaded in step 2 never reached step 3.** `DocumentsPanel` and
 * `StartBidForm` each ran their own `GET /documents` once on mount, and the form mounts the
 * moment a notice is picked — before any upload — so its copy of the list was frozen from
 * then on. The bidder read "No tender documents are waiting" directly under a table that
 * listed the file. It was possible because nothing exercised the two components *together*;
 * each was correct alone. The first test uploads, watches the row poll from `uploaded`
 * through `parsed` to `ready`, and asserts the checklist shows the file, lets it be ticked
 * once ready, and sends its id in `POST /bids`.
 *
 * **Blocker 2 — the upload form defaulted to `company_evidence`,** the one kind the start
 * step filters out (`TENDER_DOCUMENT_KINDS`), so a pack uploaded on the default vanished from
 * the checklist with no explanation. Possible because the default was written for
 * `/company`, where it is right, and the flow reused the form without saying otherwise. The
 * second test reads the select the bidder sees; the first checks the kind the upload
 * *carries*, because the fake derives its answer from the multipart body it received — a
 * form that sent `company_evidence` would produce a document the checklist filters out, and
 * the test would fail exactly where the bidder did.
 *
 * The API is `FakeApi` (see `support/fake-api.ts`): the real app, answers the test wrote.
 */
import { isDocumentKind, TENDER_DOCUMENT_KINDS } from '@/lib/documents'

import {
  BID_ID,
  companyProfileFixture,
  DOCUMENT_ID,
  documentFixture,
  queuedBidFixture,
  SECOND_DOCUMENT_ID,
  type DocumentResponse,
} from './support/fixtures'
import { multipartField, multipartFilename } from './support/fake-api'
import { expect, test } from './support/test'

const PACK_FILE = 'Besondere_Bewerbungsbedingungen_VV2_V1.pdf'
const NOTICE_NUMBER = '614251-2026'
/** Two polls at the app's 2 s cadence (`use-polling.ts`), with room for a dev-mode compile. */
const POLL_SETTLE_MS = 15_000

test.describe('Analyse tender — upload the pack, then start', () => {
  test.beforeEach(async ({ api, page }) => {
    api.on('GET', '/companies/me', { status: 200, json: companyProfileFixture() })
    api.on('GET', '/documents', { status: 200, json: { documents: [] } })

    // The step-1 button is server-rendered, and a click before hydration does nothing. The
    // flow's first effect asks for the profile, so that answer arriving is the proof React is
    // running — awaited from before navigation, in case it lands before `load` does.
    const hydrated = page.waitForResponse((response) =>
      new URL(response.url()).pathname.endsWith('/companies/me')
    )
    await page.goto('/bids/new')
    await hydrated
    await page.getByRole('button', { name: 'Enter it yourself' }).click()
  })

  test('the upload form starts on a tender kind, not the one step 3 filters out', async ({
    page,
  }) => {
    const kind = page.getByLabel('Document type', { exact: true })
    await expect(kind).toBeVisible()

    const selected = await kind.inputValue()
    expect(isDocumentKind(selected), `"${selected}" is not a DocumentKind`).toBe(true)
    expect(
      isDocumentKind(selected) && TENDER_DOCUMENT_KINDS.has(selected),
      `the default "${selected}" is not one of the kinds the start step lists`
    ).toBe(true)
  })

  test('a pack uploaded in step 2 is in step 3’s checklist, tickable once ready, and sent with the bid', async ({
    api,
    page,
  }) => {
    // The fake's document is *derived from the upload*: name and kind come from the multipart
    // body the form sent, so what the checklist filters on is what the form actually chose.
    let accepted: DocumentResponse | undefined
    api.on('POST', '/documents', ({ body }) => {
      const kind = multipartField(body, 'kind')
      const name = multipartFilename(body)
      if (!isDocumentKind(kind) || name === undefined) {
        return {
          status: 422,
          json: { detail: `e2e: upload carried kind=${kind} name=${name}` },
        }
      }
      accepted = documentFixture({ id: DOCUMENT_ID, name, kind, status: 'uploaded', pages: 0 })
      return { status: 202, json: accepted }
    })
    // The row polls itself every two seconds; it is `parsed` once, then `ready` for good.
    let polls = 0
    api.on('GET', `/documents/${DOCUMENT_ID}`, () => {
      if (accepted === undefined) {
        return { status: 404, json: { detail: 'e2e: polled before any upload' } }
      }
      polls += 1
      const status = polls === 1 ? 'parsed' : 'ready'
      return { status: 200, json: { ...accepted, status, pages: 12 } }
    })
    // The bid the flow lands on lists no documents: this test ends at the workspace's URL,
    // and a bid that carries the DE pack makes the Source panel ask for a signed URL that
    // nothing here stubs — which the `api` fixture rightly fails the test for.
    const landed = queuedBidFixture({ documents: [] })
    api.on('POST', '/bids', { status: 202, json: landed })
    api.on('GET', `/bids/${BID_ID}`, { status: 200, json: landed })
    api.on('GET', `/bids/${BID_ID}/feedback`, { status: 200, json: { feedback: [] } })

    await page.getByLabel('File', { exact: true }).setInputFiles({
      name: PACK_FILE,
      mimeType: 'application/pdf',
      buffer: Buffer.from('%PDF-1.4\n% e2e: never parsed, the API is a fake\n'),
    })
    await page.getByRole('button', { name: 'Upload file' }).click()

    // Step 3's checklist is the fieldset; its legend names it. The row is there the moment
    // the upload is accepted — disabled, because the file is still being read.
    const checklist = page.getByRole('group', { name: 'Procurement documents' })
    const tick = checklist.getByRole('checkbox', { name: PACK_FILE })
    await expect(tick).toBeAttached()
    await expect(tick).toBeDisabled()
    // The count is the Start card's tag, in its header rather than in the fieldset.
    await expect(page.getByText('0 of 1 ready selected')).toBeVisible()

    // Two polls later the panel has heard `ready` and told the form, which enables the tick.
    await expect(tick).toBeEnabled({ timeout: POLL_SETTLE_MS })
    await checklist.getByText(PACK_FILE, { exact: true }).click()
    await expect(tick).toBeChecked()
    await expect(page.getByText('1 of 1 ready selected')).toBeVisible()

    await page.getByLabel('Notice number', { exact: true }).fill(NOTICE_NUMBER)
    const start = page.getByRole('button', { name: 'Start analysis' })
    await expect(start).toBeEnabled()
    await start.click()
    await expect(page).toHaveURL(new RegExp(`/bids/${BID_ID}$`))

    const upload = api.requests.find((r) => r.method === 'POST' && r.path === '/documents')
    expect(upload, 'the form never uploaded').toBeDefined()
    expect(multipartField(upload?.body, 'kind')).toBe('tender_document')

    const started = api.requests.find((r) => r.method === 'POST' && r.path === '/bids')
    expect(started?.body, 'the form never started a bid').toBeDefined()
    expect(JSON.parse(started?.body ?? '{}')).toMatchObject({
      notice_number: NOTICE_NUMBER,
      document_ids: [DOCUMENT_ID],
    })
  })
})

test.describe('Analyse tender — a pack another analysis already uses', () => {
  /**
   * Its own describe because these two set up `GET /documents` *before* the page loads: the
   * panel fetches once on mount, and a reload inside the test would count that fetch twice.
   */
  test.beforeEach(async ({ api }) => {
    api.on('GET', '/companies/me', { status: 200, json: companyProfileFixture() })
    // A bid that lists no documents: these tests end at the workspace's URL, and a bid
    // carrying a pack makes the Source panel ask for a signed URL nothing here stubs.
    api.on('GET', `/bids/${BID_ID}`, { status: 200, json: queuedBidFixture({ documents: [] }) })
    api.on('GET', `/bids/${BID_ID}/feedback`, { status: 200, json: { feedback: [] } })
  })

  async function openStepThree(page: import('@playwright/test').Page) {
    const hydrated = page.waitForResponse((response) =>
      new URL(response.url()).pathname.endsWith('/companies/me')
    )
    await page.goto('/bids/new')
    await hydrated
    await page.getByRole('button', { name: 'Enter it yourself' }).click()
  }

  test('a document other analyses already use is offered, and its id is sent', async ({
    api,
    page,
  }) => {
    /**
     * The defect this change exists for, end to end in a browser (ADR-0103).
     *
     * The picker filtered on `bid_id === null`, so a pack any earlier analysis held was not
     * rendered at all — and re-analysing the same tender meant uploading every file again,
     * paying to embed it again, and keeping a second copy in Storage. A jsdom test can pin
     * the filter; only this one proves the panel's fetch reaches the checklist with the
     * count intact.
     */
    api.on('GET', '/documents', {
      status: 200,
      json: {
        documents: [documentFixture({ id: DOCUMENT_ID, name: PACK_FILE, bid_count: 2 })],
      },
    })
    api.on('POST', '/bids', { status: 202, json: queuedBidFixture({ documents: [] }) })
    await openStepThree(page)

    const checklist = page.getByRole('group', { name: 'Procurement documents' })
    await expect(checklist.getByText(PACK_FILE, { exact: true })).toBeVisible()
    await expect(checklist.getByText(/used by 2 analyses/)).toBeVisible()

    const tick = checklist.getByRole('checkbox', { name: new RegExp(PACK_FILE) })
    await expect(tick).toBeEnabled()
    await checklist.getByText(PACK_FILE, { exact: true }).click()
    await expect(page.getByText('1 of 1 ready selected')).toBeVisible()

    await page.getByLabel('Notice number', { exact: true }).fill(NOTICE_NUMBER)
    await page.getByRole('button', { name: 'Start analysis' }).click()
    await expect(page).toHaveURL(new RegExp(`/bids/${BID_ID}$`))

    const started = api.requests.find((r) => r.method === 'POST' && r.path === '/bids')
    expect(JSON.parse(started?.body ?? '{}')).toMatchObject({
      document_ids: [DOCUMENT_ID],
    })
  })

  test('the documents list is fetched to the end, not one default page', async ({
    api,
    page,
  }) => {
    /**
     * The second, independent way a pack went missing: the panel asked for no `limit`, took
     * the API's default of 50, and left the rest behind a button that sits under step 2's
     * table rather than beside the step 3 checklist that is short of rows.
     */
    const second = documentFixture({ id: SECOND_DOCUMENT_ID, name: 'Anlage_3.pdf' })
    api.on('GET', '/documents', (request) =>
      request.path.includes('cursor=')
        ? { status: 200, json: { documents: [second], next_cursor: null } }
        : {
            status: 200,
            json: {
              documents: [documentFixture({ id: DOCUMENT_ID, name: PACK_FILE })],
              next_cursor: 'page-two',
            },
          }
    )
    await openStepThree(page)

    // No click on "Load more": the second page must arrive on its own.
    const checklist = page.getByRole('group', { name: 'Procurement documents' })
    await expect(checklist.getByText('Anlage_3.pdf', { exact: true })).toBeVisible()

    // The list endpoint only: `/documents/{id}/url` is a different call. Counted by shape
    // rather than exactly, because React's development double-invoke runs the mount effect
    // twice and the number of *fetches* is not what this test is about.
    const listed = api.requests.filter(
      (r) => r.method === 'GET' && /^\/documents(\?|$)/.test(r.path)
    )
    expect(
      listed.every((r) => r.path.includes('limit=200')),
      'every page asks for the ceiling'
    ).toBe(true)
    expect(
      listed.some((r) => r.path.includes('cursor=page-two')),
      'the cursor the first page returned was followed without a click'
    ).toBe(true)
  })
})
