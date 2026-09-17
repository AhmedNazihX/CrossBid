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

/**
 * The fold — finding L4 of the 2026-09-15 audit.
 *
 * The hero opens with `BrandReveal`, a logo animation added after the canvas was confirmed
 * and the one element on this page with no artboard behind it (ADR-0014). It cost 248 px —
 * a 216 px band and its 32 px margin — and that was the *whole* difference between the app
 * and `Landing.dc.html`: measured at 1440x900, the artboard puts the product mock at y=638
 * and the app put it at y=886, with every other element of the hero matching to the pixel.
 * Fourteen pixels of the mock were on screen, so the one element that shows what the product
 * does was, in effect, below the fold.
 *
 * Asserted as "how much of the mock is on screen" rather than "the band is 96 px tall",
 * because the height is a means: a later change to the pill, the headline's wrapping or the
 * hero's padding can spend the same budget again, and this test is what would notice.
 */
const ARTBOARD_VIEWPORT = { width: 1440, height: 900 }
/** Enough of the frame to read as a screen rather than as an edge. The shipped page had 14. */
const MINIMUM_MOCK_VISIBLE_PX = 120

test('enough of the product mock is above the fold to see what it is', async ({ page }) => {
  await page.setViewportSize(ARTBOARD_VIEWPORT)
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()

  // The framed screenshot of the workspace: the widest card in the hero, below the headline.
  const mock = page.locator('.max-w-\\[980px\\]').first()
  await expect(mock).toBeVisible()
  const box = await mock.boundingBox()
  if (box === null) throw new Error('the product mock has no box, so nothing was measured')

  const visible = ARTBOARD_VIEWPORT.height - box.y
  expect(
    visible,
    `the mock starts at y=${Math.round(box.y)}, leaving ${Math.round(visible)}px on screen`
  ).toBeGreaterThanOrEqual(MINIMUM_MOCK_VISIBLE_PX)
})

/**
 * The reveal's mask fades out inside its own box — the regression L4's fix introduced.
 *
 * The clip overflows its band by design and is masked rather than clipped, so the rings
 * dissolve instead of ending at a line. The mask was one `radial-gradient(ellipse 80% 66%)`,
 * and **those radii are larger than the box**: measured from the centre of a box whose
 * half-width is 50 %, a radius of 80 % reaches transparent well outside it, so at the video's
 * own left and right edges the mask still stood at about 0.59 alpha. The clip was being cut
 * off by the element's edge, not faded out by the mask.
 *
 * That was invisible while the band was 840 px wide — the video was 1200 x 675 and its edges
 * fell outside the hero's content. Shrinking the band to 96 px brought all four into view and
 * painted a rectangle with hard sides across the pill. Reported from the running page; no
 * check here saw it, because nothing here looks at the mask.
 *
 * Asserted on the computed mask rather than on pixels: the hero's 72 px grid means a sampled
 * colour depends on whether the sample landed on a grid line, and an image library to diff
 * regions properly is a dependency this repo has not agreed to. The invariant is exact and
 * this is where it lives — every gradient must reach `transparent` inside the box it masks.
 */
test('the reveal is faded out by its mask, not cut off by its own edge', async ({ page }) => {
  await page.setViewportSize(ARTBOARD_VIEWPORT)
  await page.goto('/')
  const video = page.locator('video')
  await expect(video).toBeAttached()

  const mask = await video.evaluate((element) => {
    const style = getComputedStyle(element)
    return { image: style.maskImage, composite: style.maskComposite }
  })

  // One gradient per axis: a radial one cannot fade differently on each, and the vertical
  // direction is the crowded one — the pill sits 28 px above the band.
  const gradients = splitTopLevel(mask.image).filter((part) => part.includes('gradient'))
  expect(gradients.length, `computed mask: ${mask.image}`).toBeGreaterThanOrEqual(2)
  for (const gradient of gradients) {
    expect(
      gradient,
      'a gradient that never reaches transparent cannot fade anything out'
    ).toMatch(/transparent|rgba\(0,\s*0,\s*0,\s*0\)/)
    // The failure this replaces: radii past 50 % put the transparent stop outside the box.
    const radii = [...gradient.matchAll(/(\d+(?:\.\d+)?)%/g)].map((m) => Number(m[1]))
    expect(Math.max(...radii), `stops past the box: ${gradient}`).toBeLessThanOrEqual(100)
  }
  // Layered without this the two would union, and the union of two bands is a cross.
  //
  // Both spellings are set on the element and Chrome computes the `-webkit-` one, per layer:
  // `source-in, source-in` rather than `intersect`. They mean the same thing — a layer is kept
  // only where what is already composited is opaque — so the assertion accepts either, once
  // for each gradient. Pinning the standard keyword alone would have failed against a page
  // that works.
  const composites = splitTopLevel(mask.composite)
  expect(composites, `computed mask-composite: ${mask.composite}`).toHaveLength(
    gradients.length
  )
  for (const composite of composites) {
    expect(composite).toMatch(/^(intersect|source-in)$/)
  }
})

/**
 * Splits a computed CSS list on its top-level commas.
 *
 * `getComputedStyle` returns colours as `rgba(0, 0, 0, 0)`, so each gradient is full of commas
 * of its own and a plain `split(',')` cuts one gradient into five. The first draft of this test
 * used a lookahead regex, read `" linear-gradient(to right"` as a whole gradient, and failed —
 * for the right reason by accident, which is not the same as being right.
 */
function splitTopLevel(value: string): readonly string[] {
  const parts: string[] = []
  let depth = 0
  let current = ''
  for (const character of value) {
    if (character === '(') depth += 1
    if (character === ')') depth -= 1
    if (character === ',' && depth === 0) {
      parts.push(current)
      current = ''
      continue
    }
    current += character
  }
  return [...parts, current].map((part) => part.trim()).filter((part) => part !== '')
}
