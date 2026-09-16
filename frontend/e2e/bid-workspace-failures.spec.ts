/**
 * The bid workspace when `GET /bids/{id}` does not come back — `/bids/{id}`, the `failed`
 * branch of `components/bids/bid-workspace.tsx`.
 *
 * **Written against a report that turned out to be wrong, and one defect it hid.** On
 * 2026-09-16, with migrations pending, the API raised on `GET /bids/{id}` and Starlette
 * dropped the CORS headers from its 500; the browser saw `TypeError: Failed to fetch`, and
 * the report said the workspace "sits at 'Loading…'" for ever on a failed fetch. It does
 * not, and the first test pins that: a request that fails at the transport lands in the
 * danger notice with **Try again** and **Back to tenders**, and Try again really reloads.
 * The endless "Loading…" was the shell's session guard in a different failure, which has
 * its own tests in `components/auth/*.test.tsx`.
 *
 * What the investigation did find here is the second test: a request that *never settles*
 * had no exit — `getBid` neither resolved nor rejected, so neither branch ran and "Loading
 * the bid…" stayed for as long as the tab was open. The workspace now gives that read a
 * deadline (`BID_LOAD_DEADLINE_MS`) and lands in the same notice with a sentence that names
 * the wait. This test waits the real twenty seconds rather than shortening them: the figure
 * is the product's, and a test that could not see it fire would not know the deadline was
 * there.
 *
 * The bid is `queuedBidFixture` with no documents: once loaded it polls the same route
 * (answered by the same stub) and asks for its feedback, and nothing else.
 */
import { BID_ID, queuedBidFixture } from './support/fixtures'
import { expect, test } from './support/test'

/**
 * `BID_LOAD_DEADLINE_MS` in `components/bids/bid-workspace.tsx`, repeated because a
 * Playwright spec runs in Node and cannot import a client component. Change both together.
 */
const BID_LOAD_DEADLINE_MS = 20_000
/** Room for the notice to render after the deadline fires; generous, because a dev server compiles on first request. */
const DEADLINE_SLACK_MS = 5_000

const COULD_NOT_BE_LOADED = 'The bid could not be loaded'

test.describe('Bid workspace — when GET /bids/{id} does not come back', () => {
  test.beforeEach(({ api }) => {
    api.on('GET', `/bids/${BID_ID}/feedback`, { status: 200, json: { feedback: [] } })
  })

  test('a request that fails at the transport shows the error card, and Try again recovers', async ({
    api,
    apiOrigin,
    page,
  }) => {
    const bid = queuedBidFixture({ documents: [] })
    api.on('GET', `/bids/${BID_ID}`, { failure: 'abort' })

    await page.goto(`/bids/${BID_ID}`)

    const notice = page.getByRole('alert').filter({ hasText: COULD_NOT_BE_LOADED })
    await expect(notice).toBeVisible()
    await expect(notice).toContainText(`The API at ${apiOrigin} could not be reached`)
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(
      'This bid could not be opened'
    )
    await expect(page.getByRole('link', { name: 'Back to tenders' })).toHaveAttribute(
      'href',
      '/bids'
    )

    // The API comes back; the newest handler wins.
    api.on('GET', `/bids/${BID_ID}`, { status: 200, json: bid })
    await page.getByRole('button', { name: 'Try again' }).click()

    await expect(page.getByRole('heading', { level: 1, name: bid.title })).toBeVisible()
    await expect(notice).toBeHidden()
  })

  test('a request that never settles stops waiting at the deadline', async ({
    api,
    apiOrigin,
    page,
  }) => {
    api.on('GET', `/bids/${BID_ID}`, { failure: 'hang' })

    await page.goto(`/bids/${BID_ID}`)

    await expect(page.getByRole('status').filter({ hasText: 'Loading the bid…' })).toBeVisible()

    const notice = page.getByRole('alert').filter({ hasText: COULD_NOT_BE_LOADED })
    await expect(notice).toBeVisible({ timeout: BID_LOAD_DEADLINE_MS + DEADLINE_SLACK_MS })
    await expect(notice).toContainText(
      `The API at ${apiOrigin} did not answer within ${BID_LOAD_DEADLINE_MS / 1000} seconds`
    )
    await expect(page.getByRole('button', { name: 'Try again' })).toBeVisible()
  })
})
