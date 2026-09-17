/**
 * The bid workspace at desktop width — `/bids/{id}`, `Main.dc.html` (S7.7; blockers 3 and 4
 * of the 2026-09-15 audit).
 *
 * **Blocker 3 — the "Review verdict" control was white text on a transparent ground.** Its
 * class string named `bg-accent-default`, which the `@theme` block never declares. Under
 * Tailwind 4's `--color-*: initial` an unknown colour utility emits *no declaration at all*
 * rather than failing, so `tsc`, ESLint and `next build` were all green and the header's one
 * call to action had a contrast of 1.02:1. Nothing but the painted pixels could see it, so
 * the first test reads the control's computed colours and composites them the way the
 * screen does (`support/contrast.ts`).
 *
 * **Blocker 4 — the right column's tab strip was 2 px tall at ≥ 1280 px.** The column is a
 * height-capped flex column (`max-h-[calc(100dvh-2rem)]`, scrolling internally while sticky)
 * and the tablist had no `shrink-0` and, being `overflow-hidden`, no intrinsic minimum — so
 * once the column's content exceeded the cap, flex took the whole shortfall out of the strip
 * and clipped the 38 px tabs behind its borders. A real click on Source / Ask / Verdict was
 * intercepted for as long as Playwright cared to wait; ADR-0060's control had never worked
 * at the width it was designed for. Possible because the phone layout, which is what got
 * looked at, has no height cap.
 *
 * **The collapse needs pressure, and the test proves it has some.** With little in the
 * column nothing is squeezed and `shrink-0` changes nothing — a first version of this test
 * passed with the defect put back. What squeezed the column in production was the Source
 * panel: a 560 px frame under a chip per document, and a pack has a dozen. So the fixture
 * carries the DE pack, the fake also serves the page the signed URL frames, and the test
 * asserts the column actually overflows before it asserts anything about the strip —
 * without that check a lighter fixture would quietly make the test vacuous again. The
 * strip's height is a weak signal on its own; the strong ones are that the point at a tab's
 * centre hits that tab, and that a real click lands well inside the five seconds the
 * shipped defect swallowed.
 *
 * The bid is `awaitingReviewBidFixture`: parked at the interrupt with a verdict written, the
 * one state where the control is an enabled anchor and the column carries its Verdict tab.
 */
import type { Locator, Page } from '@playwright/test'

import type { FakeApi } from './support/fake-api'
import { paintedContrast } from './support/contrast'
import { awaitingReviewBidFixture, BID_ID, packDocumentsFixture } from './support/fixtures'
import { expect, test } from './support/test'

/** WCAG 2.x AA for text that is neither large nor bold: the control is 14 px medium. */
const MIN_TEXT_CONTRAST = 4.5
/** The segmented control's tabs are 38 px (`components/ui/tabs.tsx`); the shipped strip was 2 px. */
const MIN_TABLIST_HEIGHT_PX = 38
/** The shipped strip swallowed a click for Playwright's default five seconds; a working one takes milliseconds. */
const CLICK_BUDGET_MS = 1_500
/** The signed URL's lifetime; far enough out that the panel does not refresh it mid-test. */
const SIGNED_URL_TTL_MS = 10 * 60 * 1_000

test.describe('Bid workspace — the desktop layout of ADR-0060', () => {
  test.use({ viewport: { width: 1440, height: 900 } })

  test.beforeEach(async ({ api, apiOrigin, page }) => {
    const bid = awaitingReviewBidFixture()
    api.on('GET', `/bids/${BID_ID}`, { status: 200, json: bid })
    api.on('GET', `/bids/${BID_ID}/feedback`, { status: 200, json: { feedback: [] } })
    // The attach control lists company evidence while the bid is parked.
    api.on('GET', '/documents', { status: 200, json: { documents: [] } })
    // The source panel opens the first document: it asks for a signed URL, then frames it.
    // The fake hands out a URL on its own origin and serves the page, so the frame is the
    // real 560 px thing it is on a real bid, and no request leaves the test.
    const sourcePage = `${apiOrigin}/e2e/source-page`
    api.on('GET', /^\/documents\/[^/]+\/url$/, () => ({
      status: 200,
      json: {
        url: sourcePage,
        expires_at: new Date(Date.now() + SIGNED_URL_TTL_MS).toISOString(),
      },
    }))
    api.on('GET', '/e2e/source-page', {
      status: 200,
      contentType: 'text/html',
      body: '<!doctype html><title>e2e source page</title><p>The PDF viewer would be here.</p>',
    })

    await page.goto(`/bids/${BID_ID}`)
    await expect(page.getByRole('heading', { level: 1, name: bid.title })).toBeVisible()
    await expect(page.getByTitle(/page 1$/)).toBeVisible()
  })

  test('the Review verdict control is painted, with readable contrast', async ({ page }) => {
    const control = page.getByRole('link', { name: 'Review verdict' })
    await expect(control).toBeVisible()

    const paint = await paintedContrast(control)
    expect(
      paint.ownBackgroundAlpha,
      `the control's own background is ${paint.ownBackground}: a colour utility that resolved to nothing`
    ).toBe(1)
    expect(
      paint.ratio,
      `${paint.color} on ${paint.ownBackground} is ${paint.ratio.toFixed(2)}:1`
    ).toBeGreaterThanOrEqual(MIN_TEXT_CONTRAST)
  })

  test('the right column’s tab strip keeps its height under pressure, and a click lands', async ({
    page,
  }) => {
    const tablist = page.getByRole('tablist', { name: 'Workspace panels' })
    await expect(tablist).toBeAttached()
    const ask = tablist.getByRole('tab', { name: 'Ask' })
    const source = tablist.getByRole('tab', { name: 'Source' })

    // The strip is the first child of the sticky column; the column is what caps the height.
    const column = tablist.locator('..')
    const measured = await measureStrip(tablist, ask, column)
    test.info().annotations.push({
      type: 'tablist',
      description: `height ${measured.tablistHeight}px; column scrollHeight ${measured.columnScrollHeight}px, clientHeight ${measured.columnClientHeight}px; centre of Ask hits: ${measured.askCentreHits}`,
    })

    expect(
      measured.tablistHeight,
      `the tablist is ${measured.tablistHeight}px tall: flex has shrunk it to its borders`
    ).toBeGreaterThanOrEqual(MIN_TABLIST_HEIGHT_PX)
    expect(
      measured.askCentreHits,
      `the point at the Ask tab’s centre lands on "${measured.askCentreHits}", not on the tab: it is clipped or covered`
    ).toBe('tab')

    // A real pointer click, on a budget far under the five seconds the defect swallowed.
    await expect(source).toHaveAttribute('aria-selected', 'true')
    await ask.click({ timeout: CLICK_BUDGET_MS })
    await expect(ask).toHaveAttribute('aria-selected', 'true')
    await expect(source).toHaveAttribute('aria-selected', 'false')
    await expect(
      page.getByRole('textbox', { name: 'Your question about this tender' })
    ).toBeVisible()
    await expect(await panelOf(page, source)).toBeHidden()

    // The header's control is the third way in: it opens the Verdict tab (ADR-0060).
    await page.getByRole('link', { name: 'Review verdict' }).click({ timeout: CLICK_BUDGET_MS })
    const verdict = tablist.getByRole('tab', { name: 'Verdict' })
    await expect(verdict).toHaveAttribute('aria-selected', 'true')
    await expect(await panelOf(page, verdict)).toBeVisible()

    // Last, the precondition: the column really was over its cap, so the strip really was
    // under the pressure that collapsed it. A lighter fixture makes this test say nothing,
    // and this is where it would say so.
    expect(
      measured.columnScrollHeight,
      'the side column is not over its height cap: nothing squeezes the strip, and this test cannot fail for the defect it protects'
    ).toBeGreaterThan(measured.columnClientHeight)
  })
})

interface StripMeasurement {
  readonly tablistHeight: number
  readonly columnScrollHeight: number
  readonly columnClientHeight: number
  /** `'tab'` when `elementFromPoint` at the tab's centre is the tab; otherwise what it hit. */
  readonly askCentreHits: string
}

async function measureStrip(
  tablist: Locator,
  tab: Locator,
  column: Locator
): Promise<StripMeasurement> {
  const [tablistHeight, columnBox, askCentreHits] = await Promise.all([
    tablist.evaluate((element) => element.getBoundingClientRect().height),
    column.evaluate((element) => ({
      scrollHeight: element.scrollHeight,
      clientHeight: element.clientHeight,
    })),
    tab.evaluate((element) => {
      const rect = element.getBoundingClientRect()
      const hit = document.elementFromPoint(
        rect.left + rect.width / 2,
        rect.top + rect.height / 2
      )
      if (hit === null) return 'nothing'
      return element.contains(hit)
        ? 'tab'
        : `${hit.tagName.toLowerCase()}[role=${hit.getAttribute('role')}]`
    }),
  ])
  return {
    tablistHeight,
    columnScrollHeight: columnBox.scrollHeight,
    columnClientHeight: columnBox.clientHeight,
    askCentreHits,
  }
}

/** The panel a tab controls, found through its ARIA wiring rather than through a class or an id. */
async function panelOf(page: Page, tab: Locator): Promise<Locator> {
  const controls = await tab.getAttribute('aria-controls')
  if (controls === null) {
    throw new Error('the tab names no panel: aria-controls is missing')
  }
  return page.locator(`[role="tabpanel"][id="${controls}"]`)
}

test.describe('Bid workspace — a pack Ask cannot read', () => {
  test.use({ viewport: { width: 1440, height: 900 } })

  /** The source panel opens the first document, so its two calls need answers here too. */
  function stubTheSourcePanel(api: FakeApi, apiOrigin: string): void {
    const sourcePage = `${apiOrigin}/e2e/source-page`
    api.on('GET', /^\/documents\/[^/]+\/url$/, () => ({
      status: 200,
      json: {
        url: sourcePage,
        expires_at: new Date(Date.now() + SIGNED_URL_TTL_MS).toISOString(),
      },
    }))
    api.on('GET', '/e2e/source-page', {
      status: 200,
      contentType: 'text/html',
      body: '<!doctype html><title>e2e source page</title><p>The PDF viewer would be here.</p>',
    })
  }

  /**
   * The workspace says the pack is not searchable, rather than leaving it to be discovered.
   *
   * Reported 2026-09-17: a bid analysed the day before `parse_docs` began writing
   * `tender_chunks` has a complete matrix and an empty retrieval corpus, so every question put
   * to Ask came back "I could not find anything about this in the tender documents" — about
   * documents whose pages the matrix beside it was citing (ADR-0098). Nothing on this screen
   * said so: *Problems flagged* read 0, and read it correctly, because nothing had failed.
   */
  test('a bid whose documents were never indexed says so on the workspace', async ({
    api,
    apiOrigin,
    page,
  }) => {
    stubTheSourcePanel(api, apiOrigin)
    const bid = {
      ...awaitingReviewBidFixture(),
      documents: packDocumentsFixture({ searchable: false }),
    }
    api.on('GET', `/bids/${BID_ID}`, { status: 200, json: bid })
    api.on('GET', `/bids/${BID_ID}/feedback`, { status: 200, json: { feedback: [] } })
    api.on('GET', '/documents', { status: 200, json: { documents: [] } })

    await page.goto(`/bids/${BID_ID}`)

    const notice = page.getByRole('status').filter({ hasText: /ask cannot read/i })
    await expect(notice).toBeVisible()
    await expect(notice).toContainText(/matrix/i)
    // Nothing else on the screen carries the fact: this is what "Problems flagged: 0" hides.
    await expect(page.getByText('Problems flagged')).toBeVisible()
  })

  test('a bid whose documents were indexed says nothing', async ({ api, apiOrigin, page }) => {
    stubTheSourcePanel(api, apiOrigin)
    const bid = awaitingReviewBidFixture()
    api.on('GET', `/bids/${BID_ID}`, { status: 200, json: bid })
    api.on('GET', `/bids/${BID_ID}/feedback`, { status: 200, json: { feedback: [] } })
    api.on('GET', '/documents', { status: 200, json: { documents: [] } })

    await page.goto(`/bids/${BID_ID}`)
    await expect(page.getByRole('heading', { level: 1, name: bid.title })).toBeVisible()

    await expect(page.getByText(/ask cannot read/i)).toHaveCount(0)
  })
})
