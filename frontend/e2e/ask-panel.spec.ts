/**
 * "Ask the tender" — the question box, and the promises its animation makes (ADR-0107).
 *
 * The box shows a question that changes every few seconds instead of a static "Ask about this
 * tender…", because a reader who has never used this learns more from *"What is the deadline
 * for questions?"* than from an instruction to ask something. Everything about that is invisible
 * to the unit suite: jsdom has no timers a user can watch, no `prefers-reduced-motion`, and no
 * way to tell a rotation that stopped from one that never started.
 *
 * Three promises are asserted here, and the last two are the ones that would decay quietly:
 * the question really does change; it **stops the moment there is something to read in the
 * box**; and under `prefers-reduced-motion: reduce` it **never moves at all** — WCAG 2.2.2 is
 * about auto-updating information, not only about movement, so the honest answer there is one
 * question that stays put rather than the same carousel without the slide.
 */
import path from 'node:path'

import { awaitingReviewBidFixture, BID_ID, packDocumentsFixture } from './support/fixtures'
import { expect, test } from './support/test'

/**
 * Comfortably longer than `ASK_PLACEHOLDER_INTERVAL_MS` plus its fade, so a rotation has
 * certainly had its turn. A window only just wider than the interval is a flaky test: the
 * clock starts when the component mounts, not when the assertion does.
 */
const A_FULL_TURN_MS = 6_000
const SOURCE_PDF = path.resolve(__dirname, 'fixtures/source-page.pdf')
const SIGNED_URL_TTL_MS = 10 * 60 * 1_000

test.describe('Ask the tender — the question that cycles', () => {
  test.use({ viewport: { width: 1440, height: 900 } })

  test.beforeEach(async ({ api, apiOrigin }) => {
    const bid = { ...awaitingReviewBidFixture(), documents: packDocumentsFixture() }
    api.on('GET', `/bids/${BID_ID}`, { status: 200, json: bid })
    api.on('GET', `/bids/${BID_ID}/feedback`, { status: 200, json: { feedback: [] } })
    api.on('GET', '/documents', { status: 200, json: { documents: [] } })
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
  })

  /** The overlay drawn over the empty field. It is `aria-hidden`; the box's name is its label. */
  function placeholder(page: import('@playwright/test').Page) {
    return page.getByTestId('ask-placeholder')
  }

  test('the question changes on its own, and the box is still named by its label', async ({
    page,
  }) => {
    await page.goto(`/bids/${BID_ID}`)
    const box = page.getByRole('textbox', { name: 'Your question about this tender' })
    await expect(box).toBeVisible()

    const first = await placeholder(page).innerText()
    await expect(placeholder(page)).not.toHaveText(first, { timeout: A_FULL_TURN_MS })

    // The rotation is decoration: it must not be what tells a screen reader what this is.
    await expect(placeholder(page)).toHaveAttribute('aria-hidden', 'true')
  })

  test('it stops as soon as there is something to read in the box', async ({ page }) => {
    await page.goto(`/bids/${BID_ID}`)
    const box = page.getByRole('textbox', { name: 'Your question about this tender' })
    await box.fill('Wie lange läuft die Angebotsfrist?')

    // Gone entirely — a suggestion competing with a half-typed question is noise.
    await expect(placeholder(page)).toHaveCount(0)
    await page.waitForTimeout(A_FULL_TURN_MS)
    await expect(placeholder(page)).toHaveCount(0)
    await expect(box).toHaveValue('Wie lange läuft die Angebotsfrist?')
  })

  test('under prefers-reduced-motion it never moves', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.goto(`/bids/${BID_ID}`)
    await expect(placeholder(page)).toBeVisible()

    const first = await placeholder(page).innerText()
    await page.waitForTimeout(A_FULL_TURN_MS)

    expect(
      await placeholder(page).innerText(),
      'the question rotated although the reader asked for reduced motion'
    ).toBe(first)
  })

  /**
   * The box is one line at rest and grows with the question (ADR-0109).
   *
   * It was `rows={2}`, which spent a line of height on a box that is empty almost all of the
   * time — and this card sits directly above the matrix, so every bid paid it. Asserted
   * against the textarea's own height rather than the card's, so it states the behaviour
   * instead of pinning a layout number that any copy change would move.
   *
   * Measured red at `rows={2}`: the box is two lines tall before anything is typed.
   */
  test('the question box is one line until it needs more', async ({ page }) => {
    await page.goto(`/bids/${BID_ID}`)
    const box = page.getByRole('textbox', { name: 'Your question about this tender' })
    await expect(box).toBeVisible()

    const height = async (): Promise<number> =>
      box.evaluate((element) => element.getBoundingClientRect().height)
    const lineHeight = await box.evaluate((element) =>
      Number.parseFloat(getComputedStyle(element).lineHeight)
    )

    const atRest = await height()
    expect(atRest, 'the box is taller than one line before anything is typed').toBeLessThan(
      lineHeight * 2
    )

    await box.fill(
      'Welche Nachweise verlangt der Auftraggeber für die wirtschaftliche und finanzielle ' +
        'Leistungsfähigkeit des Bieters, und bis wann müssen sie eingereicht werden?'
    )
    expect(await height(), 'the box did not grow with the question').toBeGreaterThan(atRest)

    // And it collapses again, so a sent question does not leave the page stretched.
    await box.fill('')
    expect(await height()).toBe(atRest)
  })

  /**
   * The section is still named, although nothing draws its name (ADR-0110).
   *
   * The `Card` that used to wrap this rendered "Ask the tender" as a real `h2`, which is how
   * heading navigation reached it. Taking the card away for the visual reasons in ADR-0110
   * must not take that with it, so the heading stays `sr-only` and names the region. This is
   * the kind of promise that decays silently — nothing on screen changes when it breaks.
   *
   * Measured red by deleting the `sr-only` heading: the region has no accessible name.
   */
  test('the section keeps its name although the title is not drawn', async ({ page }) => {
    await page.goto(`/bids/${BID_ID}`)

    await expect(page.getByRole('region', { name: 'Ask the tender' })).toBeAttached()

    // Named, not drawn. `not.toBeVisible()` is the wrong assertion here and was tried first:
    // Playwright counts an `sr-only` element as visible, because it is 1×1 and clipped rather
    // than hidden. The property that actually distinguishes the two is its size.
    const box = await page.getByRole('heading', { name: 'Ask the tender' }).boundingBox()
    expect(box, 'the heading is not in the layout at all').not.toBeNull()
    expect(box?.height ?? 0, 'the heading is drawn at a readable size').toBeLessThanOrEqual(2)
  })

  test('the send control is named, and only live once there is a question', async ({
    page,
  }) => {
    await page.goto(`/bids/${BID_ID}`)
    // Icon-only, so the name is the only thing a screen reader has.
    const send = page.getByRole('button', { name: 'Ask the tender' })

    await expect(send).toBeDisabled()

    await page.getByRole('textbox', { name: 'Your question about this tender' }).fill('Wann?')

    await expect(send).toBeEnabled()
  })
})
