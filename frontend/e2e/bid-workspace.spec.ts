/**
 * The bid workspace at desktop width — `/bids/{id}` (S7.7; blockers 3 and 4 of the
 * 2026-09-15 audit, then the reshape of ADR-0104).
 *
 * **Blocker 3 — the "Review verdict" control was white text on a transparent ground.** Its
 * class string named `bg-accent-default`, which the `@theme` block never declares. Under
 * Tailwind 4's `--color-*: initial` an unknown colour utility emits *no declaration at all*
 * rather than failing, so `tsc`, ESLint and `next build` were all green and the header's one
 * call to action had a contrast of 1.02:1. Nothing but the painted pixels could see it, so
 * the first test reads the control's computed colours and composites them the way the
 * screen does (`support/contrast.ts`).
 *
 * **Blocker 4 — the right column's tab strip was 2 px tall at ≥ 1280 px** — is gone with the
 * strip. ADR-0104 took Source, Ask and Verdict out of one tabbed 400 px column: Ask went
 * above the matrix, the source became a drawer, and the rail now holds the verdict alone.
 * What that blocker was really protecting is still protected, one layer up: the rail is
 * height-capped and sticky, and the three tests below assert the two things ADR-0060 bought
 * and ADR-0104 had to keep — **the verdict is on screen** and **a citation reaches its
 * page** — plus the drawer's own contract.
 *
 * **Each test was measured failing with its fix reverted** (ADR-0063); the reversion is named
 * in each one's comment, because a layout test that has never been red is decoration.
 *
 * The bid is `awaitingReviewBidFixture`: parked at the interrupt with a verdict written, the
 * one state where the header control is an enabled anchor and the rail carries a real panel.
 */
import path from 'node:path'

import { inkBands } from './support/canvas-ink'
import type { FakeApi } from './support/fake-api'
import { paintedContrast } from './support/contrast'
import { awaitingReviewBidFixture, BID_ID, packDocumentsFixture } from './support/fixtures'
import { expect, test } from './support/test'

/** WCAG 2.x AA for text that is neither large nor bold: the control is 14 px medium. */
const MIN_TEXT_CONTRAST = 4.5
/** A real pointer click on a working control takes milliseconds, not Playwright's five seconds. */
const CLICK_BUDGET_MS = 1_500
/** The signed URL's lifetime; far enough out that the panel does not refresh it mid-test. */
const SIGNED_URL_TTL_MS = 10 * 60 * 1_000
/** The one-page PDF the drawer renders. `fixtures/make-source-page-pdf.mjs` wrote it. */
const SOURCE_PDF = path.resolve(__dirname, 'fixtures/source-page.pdf')

test.describe('Bid workspace — the desktop layout of ADR-0104', () => {
  test.use({ viewport: { width: 1440, height: 900 } })

  test.beforeEach(async ({ api, apiOrigin, page }) => {
    const bid = awaitingReviewBidFixture()
    api.on('GET', `/bids/${BID_ID}`, { status: 200, json: bid })
    api.on('GET', `/bids/${BID_ID}/feedback`, { status: 200, json: { feedback: [] } })
    // The attach control lists company evidence while the bid is parked.
    api.on('GET', '/documents', { status: 200, json: { documents: [] } })
    // The drawer opens the cited document: it asks for a signed URL, then renders it with
    // pdf.js. The fake hands out a URL on its own origin and serves a **real one-page PDF**
    // (`e2e/fixtures/source-page.pdf`), because since ADR-0105 the drawer parses those bytes
    // — an HTML body would fail to parse, fall back to the `<iframe>`, and quietly turn every
    // assertion below into a test of the fallback. No request leaves the test.
    const sourcePage = `${apiOrigin}/e2e/source-page.pdf`
    api.on('GET', /^\/documents\/[^/]+\/url$/, () => ({
      status: 200,
      json: {
        url: sourcePage,
        expires_at: new Date(Date.now() + SIGNED_URL_TTL_MS).toISOString(),
      },
    }))
    api.on('GET', '/e2e/source-page.pdf', {
      status: 200,
      contentType: 'application/pdf',
      path: SOURCE_PDF,
    })

    await page.goto(`/bids/${BID_ID}`)
    await expect(page.getByRole('heading', { level: 1, name: bid.title })).toBeVisible()
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

  /**
   * ADR-0060's whole finding, restated for the shape that replaced it: the product's one
   * output is on the first screen. It used to be at y=13 876. Under ADR-0060 it was one tab
   * click away; now it is simply there.
   *
   * Measured red by dropping the grid's second column, which is where ADR-0060's predecessor
   * had the verdict — stacked after the matrix instead of beside it. On this one-requirement
   * fixture the rail's top came back at **y=1 022 in a 900 px viewport**, and it is 144 rows
   * further down on the FR bid.
   */
  test('the verdict is on the first screen, with no scrolling and no click', async ({
    page,
  }) => {
    const rail = page.locator('#verdict')
    await expect(rail).toBeVisible()

    const viewportHeight = page.viewportSize()?.height ?? 0
    const top = await rail.evaluate((element) => element.getBoundingClientRect().top)
    expect(
      top,
      `the verdict rail starts at y=${Math.round(top)} in a ${viewportHeight}px viewport: it is below the fold`
    ).toBeLessThan(viewportHeight)

    // Not merely present — the recommendation itself is readable without moving.
    await expect(rail.getByRole('heading', { name: 'CrossBid recommends' })).toBeVisible()
    await expect(rail.getByText(/mandatory requirement.? supported/i).first()).toBeVisible()
  })

  /**
   * The other thing ADR-0060 bought and ADR-0104 had to keep: a citation lands on its page.
   * It used to switch the column to its Source tab; it now opens the drawer, which is the
   * design system's dialog — so Escape closes it and focus comes back to where it started,
   * and both of those are part of the contract rather than Radix trivia.
   *
   * Measured red twice, each on the assertion it protects: with `setSourceOpen(true)` removed
   * from `handleCite` the click opened nothing and `getByRole('dialog')` was never found;
   * with `onCloseAutoFocus` removed from `SourceDrawer`, Escape still closed the drawer and
   * `toBeFocused` failed — Radix prevents the default restore and focuses a trigger this
   * drawer does not have, so focus landed on the body. That second one is the whole reason
   * the handler exists.
   */
  test('a citation opens the source drawer, and Escape closes it and gives focus back', async ({
    page,
  }) => {
    const citation = page
      .getByRole('button', { name: /^Open .*, page \d+, in the source/ })
      .first()
    await expect(citation).toBeVisible()

    await citation.click({ timeout: CLICK_BUDGET_MS })
    const drawer = page.getByRole('dialog')
    await expect(drawer).toBeVisible()
    // The page it cites is actually rendered, not just a shell that slid in.
    await expect(drawer.locator('canvas')).toBeVisible()

    await page.keyboard.press('Escape')
    await expect(drawer).toBeHidden()
    await expect(citation).toBeFocused()
  })

  /**
   * The other half of ADR-0105: the cited sentence is marked **on the page**, not merely
   * opened at. Everything this asserts is invisible to the unit suite — jsdom has no layout,
   * so `getClientRects` returns nothing there and the boxes have no size to check. The
   * matching that decides *which* characters is pinned in `components/pdf/quote-match.test.ts`,
   * including against this very fixture's text.
   *
   * The boxes are asserted by geometry, not by count alone: a highlight covering the whole
   * page and a highlight of zero size are both "at least one box", and both are broken.
   *
   * **Why the canvas pixels are read at the end.** The first version of this test compared the
   * highlight only with the text layer, and passed with `--total-scale-factor` deleted — the
   * line whose absence mis-sizes the whole text layer. It had to: the boxes come from a
   * `Range` over that layer's own spans, so they inherit its geometry and move with its bugs.
   * The glyphs pdf.js painted on the canvas are the one witness that does not, which is why
   * the last block reads them (`support/canvas-ink.ts`).
   *
   * Measured red three ways: with `quote` dropped from the `Citation` built in
   * `requirement-list.tsx` (no boxes at all); with `--total-scale-factor` removed from
   * `pdf-page-view.tsx` (the boxes no longer cover the ink); and with `locateQuote` made to
   * match the whole page (a box lands on the distractor line).
   */
  test('the cited sentence is marked on the page, and nothing else is', async ({ page }) => {
    const citation = page
      .getByRole('button', { name: /^Open .*, page \d+, in the source/ })
      .first()
    await citation.click({ timeout: CLICK_BUDGET_MS })

    const drawer = page.getByRole('dialog')
    const canvas = drawer.locator('canvas')
    await expect(canvas).toBeVisible()

    // The text layer is what makes the page readable to a screen reader and selectable at
    // all; it is also where the highlight gets its geometry. Its absence is a silent
    // accessibility regression, so it is asserted directly.
    await expect(drawer.locator('.textLayer')).toContainText('Mindestjahresumsatz')

    const boxes = drawer.locator('[data-testid="pdf-highlight"]')
    await expect(boxes.first()).toBeVisible()

    const canvasBox = await canvas.boundingBox()
    const count = await boxes.count()
    expect(canvasBox).not.toBeNull()
    for (let index = 0; index < count; index += 1) {
      const box = await boxes.nth(index).boundingBox()
      expect(box, `highlight ${index} has no box`).not.toBeNull()
      if (box === null || canvasBox === null) continue
      // Inside the page…
      expect(box.x).toBeGreaterThanOrEqual(canvasBox.x - 2)
      expect(box.y).toBeGreaterThanOrEqual(canvasBox.y - 2)
      expect(box.x + box.width).toBeLessThanOrEqual(canvasBox.x + canvasBox.width + 2)
      // …and the size of a line of text, not of the page and not of nothing.
      expect(box.width).toBeGreaterThan(20)
      expect(box.height).toBeGreaterThan(4)
      expect(box.height).toBeLessThan(canvasBox.height / 4)
    }

    // The sentence wraps in the fixture, so it is marked as two runs.
    expect(count).toBeGreaterThanOrEqual(2)

    // **The independent check.** Everything above compares the highlight with the text layer,
    // and the highlight is *derived* from the text layer — so if that layer is misaligned with
    // the page, the highlight is misaligned by exactly as much and every assertion so far
    // still passes. The glyphs painted on the canvas are the only witness that does not share
    // the bug, so the boxes are checked against the ink itself.
    const bands = await inkBands(canvas)
    expect(bands.length, 'the fixture paints three lines of text').toBeGreaterThanOrEqual(3)
    const [firstLine, , thirdLine] = bands
    const first = await boxes.first().boundingBox()
    expect(first).not.toBeNull()
    if (first !== null && firstLine !== undefined && canvasBox !== null) {
      const left = first.x - canvasBox.x
      const right = left + first.width
      // The first cited line is covered: the box starts no later than the ink and ends no
      // earlier, within a couple of pixels of slack for the quad's rounding.
      expect(left, 'the highlight starts right of the first glyph').toBeLessThanOrEqual(
        firstLine.left + 2
      )
      expect(right, 'the highlight ends left of the last glyph').toBeGreaterThanOrEqual(
        firstLine.right - 2
      )
      // …and it is that line's ink, not a band of the page at some other height.
      const top = first.y - canvasBox.y
      expect(top).toBeLessThanOrEqual(firstLine.top + 2)
      expect(top + first.height).toBeGreaterThanOrEqual(firstLine.bottom - 2)
    }

    // The third band is the distractor, which was never cited and must stay unmarked.
    const lowest = Math.max(
      ...(await Promise.all(
        Array.from({ length: count }, async (_unused, index) => {
          const box = await boxes.nth(index).boundingBox()
          return box === null || canvasBox === null ? 0 : box.y + box.height - canvasBox.y
        })
      ))
    )
    expect(thirdLine, 'the distractor line is not on the page').not.toBeUndefined()
    if (thirdLine !== undefined) {
      expect(lowest, 'a highlight reaches the line that was never cited').toBeLessThan(
        thirdLine.top
      )
    }
  })

  /**
   * Safari, reproduced in Chromium by removing the one API it lacks.
   *
   * Reported from the real product on 2026-09-20: the drawer fell back to the browser's viewer
   * with *"undefined is not a function (near '...value of readableStream...')"*. That is
   * pdf.js's `getTextContent()`, whose body is `for await (const value of readableStream)` —
   * and **async iteration of a `ReadableStream` did not reach Safari until 18.4**. Playwright's
   * WebKit is newer than the reporter's Safari and has it, so running the suite in WebKit would
   * *not* have caught this and will not keep it away. Deleting the API does both, in the
   * browser the suite already runs.
   *
   * Measured red against the previous implementation: with `getTextContent()` restored, the
   * drawer shows the fallback notice and no highlight.
   */
  test('the page still renders where ReadableStream cannot be async-iterated', async ({
    page,
  }) => {
    await page.addInitScript(() => {
      // Safari < 18.4, exactly: the stream works, iterating it with `for await` does not.
      delete (ReadableStream.prototype as unknown as Record<symbol, unknown>)[
        Symbol.asyncIterator
      ]
    })
    await page.reload()

    await page
      .getByRole('button', { name: /^Open .*, page \d+, in the source/ })
      .first()
      .click({ timeout: CLICK_BUDGET_MS })

    const drawer = page.getByRole('dialog')
    await expect(drawer.locator('canvas')).toBeVisible()
    await expect(drawer.locator('[data-testid="pdf-highlight"]').first()).toBeVisible()
    await expect(drawer.getByText(/without the citation marked on it/i)).toHaveCount(0)
  })

  /**
   * A citation whose words are not on the page says so, and still shows the page.
   *
   * This is the failure mode that matters most: a matcher that guesses would draw a confident
   * box over the wrong clause of a German tender, and nothing about the screen would look
   * wrong. Measured red by making `locateQuote` fall back to the first text item when it finds
   * nothing — the notice disappears and a box appears.
   */
  test('a quote that is not on the page is said out loud, not guessed at', async ({
    api,
    page,
  }) => {
    const bid = awaitingReviewBidFixture()
    const requirement = bid.requirements[0]
    if (requirement === undefined) throw new Error('the parked fixture carries no requirement')
    api.on('GET', `/bids/${BID_ID}`, {
      status: 200,
      json: {
        ...bid,
        requirements: [
          { ...requirement, source_text: 'Eine Klausel die auf dieser Seite gar nicht steht.' },
        ],
      },
    })
    await page.reload()

    await page
      .getByRole('button', { name: /^Open .*, page \d+, in the source/ })
      .first()
      .click({ timeout: CLICK_BUDGET_MS })

    const drawer = page.getByRole('dialog')
    await expect(drawer.locator('canvas')).toBeVisible()
    await expect(drawer.getByText(/were not found on page/i)).toBeVisible()
    await expect(drawer.locator('[data-testid="pdf-highlight"]')).toHaveCount(0)
  })

  /**
   * The rail is `sticky` and scrolls internally rather than leaving the screen. The measured
   * page is 23 204 px tall on the FR bid and a non-sticky column had gone by row 20.
   *
   * The precondition is asserted first and deliberately: on a short fixture the page does not
   * scroll at all, `sticky` changes nothing, and this test would pass with the property
   * deleted — which is exactly how the first version of blocker 4's test went vacuous
   * (ADR-0063). It is not hypothetical here: the first version of *this* test used the shipped
   * one-requirement fixture, whose page is 1 468 px, and the precondition caught it. Measured
   * red by removing `xl:sticky xl:top-4` with the forty-row fixture in place.
   */
  test('the verdict rail stays on screen while the matrix scrolls', async ({ api, page }) => {
    // The shipped fixture is one requirement and renders a page shorter than the viewport,
    // where `sticky` is unobservable. The pressure is the point of this test, so it brings
    // its own: forty rows, which is a quarter of the FR bid's 144.
    api.on('GET', `/bids/${BID_ID}`, { status: 200, json: longMatrixBidFixture(40) })
    await page.reload()
    const rail = page.locator('#verdict')
    await expect(rail).toBeVisible()
    const viewportHeight = page.viewportSize()?.height ?? 0

    const documentHeight = await page.evaluate(() => document.documentElement.scrollHeight)
    expect(
      documentHeight,
      `the page is ${documentHeight}px in a ${viewportHeight}px viewport: nothing scrolls, and this test cannot fail for the defect it protects`
    ).toBeGreaterThan(viewportHeight * 2)

    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight))
    await expect(rail).toBeInViewport()
  })
})

/**
 * The parked bid with its single requirement repeated `count` times, ids made unique so the
 * matrix indexes them as distinct rows. Only the height matters here, not the content.
 */
function longMatrixBidFixture(count: number) {
  const base = awaitingReviewBidFixture()
  const requirement = base.requirements[0]
  const row = base.matrix_rows[0]
  if (requirement === undefined || row === undefined) {
    throw new Error('the parked fixture no longer carries a requirement and a row')
  }
  const requirements = Array.from({ length: count }, (_unused, index) => ({
    ...requirement,
    id: `${requirement.id}-${index}`,
  }))
  const matrixRows = requirements.map((each, index) => ({
    ...row,
    id: `${row.id}-${index}`,
    requirement_id: each.id,
  }))
  return { ...base, requirements, matrix_rows: matrixRows }
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
