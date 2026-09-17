/**
 * The landing page's long words stay inside their cards.
 *
 * Reported from the running site: in "How it works", card 3 (*Map certificates*) prints
 * `Unbedenklichkeitsbescheinigung` — 30 characters — and the word ran outside the card's
 * border. The section is a five-column grid at `lg`, so each card is about 200 px wide and
 * a German compound noun is simply wider than the box that holds it. Nothing in the app
 * wraps it: the paragraph has no `overflow-wrap`, and the default `normal` will not break
 * inside a word.
 *
 * This is measured, not eyeballed. A word overflowing its container is invisible to `tsc`,
 * to ESLint and to jsdom — jsdom has no layout at all, so `scrollWidth` there is always 0 —
 * and it is invisible in a screenshot at the wrong width, because at `sm` the cards are wide
 * enough to fit it. The assertion is on the painted geometry at the artboard's own 1440 px.
 *
 * The cross-border wedge is why this word is on the page at all: the whole claim is that a
 * French requirement is explained with its German equivalent named. The one place the
 * product shows that off is the one place the layout could not hold it.
 */
import { expect, test } from './support/test'

/** The longest word on the page, and the one that was reported. */
const LONG_WORD = 'Unbedenklichkeitsbescheinigung'

test('a long German compound stays inside its "How it works" card', async ({ page }) => {
  // Arrange
  await page.goto('/')
  const card = page.locator('li', { hasText: LONG_WORD }).first()
  await expect(card).toBeVisible()

  // Act
  const overflow = await card.evaluate((element) => {
    const paragraph = element.querySelector('p')
    if (paragraph === null) throw new Error('the card has no paragraph')
    return {
      // A word too wide to break makes the paragraph's own content wider than its box.
      paragraphOverflowPx: paragraph.scrollWidth - paragraph.clientWidth,
      cardOverflowPx: element.scrollWidth - element.clientWidth,
      cardWidthPx: element.getBoundingClientRect().width,
    }
  })

  // Assert
  expect(
    overflow.paragraphOverflowPx,
    `the paragraph is ${overflow.paragraphOverflowPx}px wider than its ${overflow.cardWidthPx}px card`
  ).toBeLessThanOrEqual(0)
  expect(overflow.cardOverflowPx).toBeLessThanOrEqual(0)
})

test('no text on the landing page is wider than the box that holds it', async ({ page }) => {
  /** The same defect, looked for everywhere rather than in the one card that was reported —
   * `Unbedenklichkeitsbescheinigung` appears in three components, and the next long compound
   * will not be reported by anyone. Measured across every paragraph, heading and list item at
   * the artboard's 1440 px. */
  // Arrange
  await page.goto('/')
  await expect(page.getByText(LONG_WORD).first()).toBeVisible()

  // Act
  const overflowing = await page.evaluate(() =>
    Array.from(document.querySelectorAll('p, h1, h2, h3, li, td, span'))
      .filter((element) => {
        if (element.scrollWidth - element.clientWidth <= 1) return false
        // A clipped element is a deliberate ellipsis — the product mock truncates several
        // labels on purpose, and `scrollWidth > clientWidth` is how truncation looks. What
        // is wrong is text that *paints* outside its box, which only happens while the
        // overflow is visible.
        const { overflowX, textOverflow } = getComputedStyle(element)
        return overflowX === 'visible' && textOverflow !== 'ellipsis'
      })
      .map((element) => ({
        tag: element.tagName,
        overflowPx: element.scrollWidth - element.clientWidth,
        text: (element.textContent ?? '').slice(0, 60),
      }))
  )

  // Assert
  expect(overflowing, JSON.stringify(overflowing)).toEqual([])
})
