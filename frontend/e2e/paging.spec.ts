/**
 * Paging and the conditional poll — audit finding M13, in a real browser.
 *
 * The bid list truncated at 200 and the document list had no limit at all, and neither said
 * so. Both page now, with an opaque cursor. And `GET /bids/{id}`, which a workspace polls
 * every two seconds for the length of a run, answers with every requirement and every matrix
 * row each time — 284 of each on the DE pack — so it now carries an `ETag` and honours
 * `If-None-Match`.
 *
 * Why a browser is the only witness for both halves:
 *
 * - A "Load more" that never appears, or appears on the last page and fetches nothing, is a
 *   rendering question. jsdom would not catch the second — the button exists either way.
 * - The conditional poll's whole failure mode is **silent success**. If the browser stops
 *   sending `If-None-Match`, or cannot read `ETag` because CORS does not expose it, every
 *   screen still works perfectly and the saving simply never happens. Only something that
 *   watches the wire can tell the two apart, which is what `api.requests` is for here.
 *
 * The API is `FakeApi` (see `support/fake-api.ts`): the real app, answers the test wrote.
 */
import {
  awaitingReviewBidFixture,
  bidSummaryFixture,
  companyProfileFixture,
} from './support/fixtures'
import { expect, test } from './support/test'

const TAG = 'W/"a3f1b2c3d4e5f607"'

/** Bids numbered so the assertions can name one, all with distinct ids. */
function bidPage(from: number, count: number) {
  return Array.from({ length: count }, (_, index) => {
    const n = from + index
    return bidSummaryFixture({
      id: `${n}`.padStart(8, '0') + '-0000-4000-8000-000000000000',
      ted_publication_number: `${600000 + n}-2026`,
      title: `Rahmenvertrag ${n}`,
    })
  })
}

test.describe('Paging a list that has outgrown one page', () => {
  test.beforeEach(async ({ api }) => {
    api.on('GET', '/companies/me', { status: 200, json: companyProfileFixture() })
  })

  test('a full first page offers more, and the rows append rather than replace', async ({
    api,
    page,
  }) => {
    // Arrange
    api.on('GET', '/bids', (request) =>
      request.path.includes('cursor=')
        ? { status: 200, json: { bids: bidPage(3, 2), next_cursor: null } }
        : { status: 200, json: { bids: bidPage(1, 2), next_cursor: 'take-me-to-page-two' } }
    )

    // Act
    await page.goto('/bids')
    await expect(page.getByRole('link', { name: 'Rahmenvertrag 1' })).toBeVisible()
    await page.getByRole('button', { name: 'Load more tenders' }).click()

    // Assert: page one is still there, page two is under it.
    await expect(page.getByRole('link', { name: 'Rahmenvertrag 4' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Rahmenvertrag 1' })).toBeVisible()
  })

  test('the cursor the API gave is the cursor the browser sends back', async ({
    api,
    page,
  }) => {
    // Arrange
    api.on('GET', '/bids', (request) =>
      request.path.includes('cursor=')
        ? { status: 200, json: { bids: bidPage(3, 1), next_cursor: null } }
        : { status: 200, json: { bids: bidPage(1, 2), next_cursor: 'take-me-to-page-two' } }
    )

    // Act
    await page.goto('/bids')
    await expect(page.getByRole('link', { name: 'Rahmenvertrag 1' })).toBeVisible()
    await page.getByRole('button', { name: 'Load more tenders' }).click()
    await expect(page.getByRole('link', { name: 'Rahmenvertrag 3' })).toBeVisible()

    // Assert
    const asked = api.requests.filter((request) => request.path.startsWith('/bids?'))
    expect(asked.at(-1)?.path).toContain('cursor=take-me-to-page-two')
  })

  test('the offer appears only while the API says there is more', async ({ api, page }) => {
    /** Both halves in one journey, deliberately. A test that only asserted the button's
     * absence on a last page would pass if the button were deleted altogether — which is
     * ADR-0063's defect, and it happened here first: this test passed against a build with
     * no `LoadMore` in it at all. `next_cursor` is the only signal; counting rows against the
     * page size would put a control on the screen that fetches an empty page. */
    // Arrange: a first page that has more behind it.
    api.on('GET', '/bids', {
      status: 200,
      json: { bids: bidPage(1, 2), next_cursor: 'take-me-to-page-two' },
    })

    // Act / Assert: offered.
    await page.goto('/bids')
    await expect(page.getByRole('link', { name: 'Rahmenvertrag 1' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Load more tenders' })).toBeVisible()

    // Arrange: the same list, now the last page.
    api.on('GET', '/bids', { status: 200, json: { bids: bidPage(1, 2), next_cursor: null } })

    // Act / Assert: not offered.
    await page.reload()
    await expect(page.getByRole('link', { name: 'Rahmenvertrag 1' })).toBeVisible()
    await expect(page.getByRole('button', { name: /Load more/ })).toHaveCount(0)
  })
})

test.describe('The conditional poll', () => {
  test.beforeEach(async ({ api, apiOrigin }) => {
    api.on('GET', '/companies/me', { status: 200, json: companyProfileFixture() })
    api.on('GET', '/documents', { status: 200, json: { documents: [], next_cursor: null } })
    api.on('GET', /^\/bids\/[0-9a-f-]+\/feedback$/, { status: 200, json: { feedback: [] } })
    // The source panel opens the pack's first document; the fake serves both halves so no
    // request leaves the test.
    const sourcePage = `${apiOrigin}/e2e/source-page`
    api.on('GET', /^\/documents\/[^/]+\/url$/, () => ({
      status: 200,
      json: { url: sourcePage, expires_at: new Date(Date.now() + 600_000).toISOString() },
    }))
    api.on('GET', '/e2e/source-page', {
      status: 200,
      contentType: 'text/html',
      body: '<!doctype html><title>e2e source page</title><p>The PDF viewer would be here.</p>',
    })
  })

  test('the second poll sends back the tag the first answer carried', async ({ api, page }) => {
    // Arrange: a running bid, so the poll keeps ticking.
    const bid = awaitingReviewBidFixture({ status: 'checking' })
    api.on('GET', new RegExp('^/bids/[0-9a-f-]+$'), {
      status: 200,
      json: bid,
      headers: { ETag: TAG },
    })

    // Act
    await page.goto(`/bids/${bid.id}`)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    // `GET` only: sending `If-None-Match` cross-origin is not CORS-safelisted, so the
    // browser also sends an `OPTIONS` preflight to the same path, carrying no tag of its own.
    const polls = () =>
      api.requests.filter((r) => r.method === 'GET' && r.path === `/bids/${bid.id}`)
    await expect
      .poll(() => polls().filter((r) => r.headers['if-none-match'] === TAG).length, {
        timeout: 20_000,
      })
      .toBeGreaterThan(0)

    // Assert: it starts unconditional — the workspace holds nothing yet — and becomes
    // conditional once an answer has given it a tag. Both halves matter: a first request
    // that sent a tag would be wrong, and one that never starts sending one is the defect.
    expect(polls()[0]?.headers['if-none-match']).toBeUndefined()
  })

  test('a 304 leaves the workspace showing what it already had', async ({ api, page }) => {
    /** The answer carries no body at all, so a browser that mishandled it would blank the
     * screen — which is the one way this optimisation could be worse than not having it. */
    // Arrange
    const bid = awaitingReviewBidFixture({
      status: 'checking',
      title: 'Netztechnik Rahmenvertrag',
    })
    api.on('GET', new RegExp('^/bids/[0-9a-f-]+$'), (request) =>
      request.headers['if-none-match'] === TAG
        ? { status: 304, headers: { ETag: TAG } }
        : { status: 200, json: bid, headers: { ETag: TAG } }
    )

    // Act
    await page.goto(`/bids/${bid.id}`)
    await expect(page.getByText('Netztechnik Rahmenvertrag').first()).toBeVisible()
    await expect
      .poll(
        () =>
          api.requests.filter(
            (r) => r.path === `/bids/${bid.id}` && r.headers['if-none-match'] === TAG
          ).length,
        { timeout: 15_000 }
      )
      .toBeGreaterThan(0)

    // Assert: still on the screen after an answer with no body.
    await expect(page.getByText('Netztechnik Rahmenvertrag').first()).toBeVisible()
  })
})
