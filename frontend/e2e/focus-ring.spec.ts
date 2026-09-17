/**
 * The focus ring — finding M6 of the 2026-09-15 audit.
 *
 * The sheet drew every ring as `box-shadow: var(--shadow-focus)` from a rule in `@layer base`,
 * ink at 20 %. Two things follow, and neither is visible to `tsc`, ESLint, the build or a
 * jsdom test — only to a browser that has painted the pixels, which is why this spec is here
 * and not in `tests/`:
 *
 * 1. **A `shadow-*` utility deletes the ring.** Tailwind's utilities layer comes after
 *    `base`, and the cascade settles layers before specificity, so a static `shadow-xs`
 *    beats the `:focus-visible` rule outright. `components/ui/select.tsx` carries
 *    `shadow-xs`, so **every `<select>` in the app** had a 1 px border colour change as its
 *    only focus feedback — and the base rule's `outline: none` had already thrown away the
 *    fallback the browser would have drawn.
 * 2. **Where the ring did survive it was too faint.** Ink at 20 % composites to about
 *    1.55:1 against the canvas. WCAG 2.2 SC 1.4.11 asks for 3:1.
 *
 * The fix (ADR-0092) moves the ring to a real `outline`, which no shadow utility can reach,
 * at full ink. `--shadow-focus` stays as decoration.
 *
 * Both controls measured here are on step 2 of `/bids/new`: the document-kind `<Select>`,
 * which is the cascade victim, and the `<Input>` beside it, whose ring is drawn on the
 * wrapper through `focus-within` and was the faint one.
 *
 * The API is `FakeApi` (see `support/fake-api.ts`): the real app, answers the test wrote.
 */
import { companyProfileFixture } from './support/fixtures'
import { focusByKeyboard, paintedFocusRing } from './support/focus-ring'
import { expect, test } from './support/test'

/** WCAG 2.2 SC 1.4.11 Non-text Contrast. */
const MINIMUM_RATIO = 3
/** SC 2.4.11 Focus Appearance asks for a perimeter at least this thick. */
const MINIMUM_WIDTH_PX = 2

test.describe('Focus ring', () => {
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

  test('a keyboard-focused select is ringed at all, despite carrying a shadow utility', async ({
    page,
  }) => {
    const select = page.getByLabel('Document type')
    await focusByKeyboard(page, select)

    const ring = await paintedFocusRing(select)
    expect(
      ring.isFocusVisible,
      'the select did not reach :focus-visible, so nothing was measured'
    ).toBe(true)
    // The defect: `outline-style` is `none` and the width is 0. A shadow cannot be relied on
    // here, so the ring has to be an outline.
    expect(ring.style, `computed outline: ${ring.style} ${ring.widthPx}px`).not.toBe('none')
    expect(ring.widthPx).toBeGreaterThanOrEqual(MINIMUM_WIDTH_PX)
    // Held off the border so a ring and a focused border read as two things, not one.
    expect(ring.offsetPx).toBeGreaterThan(0)
  })

  test('the select ring clears the 3:1 the standard asks for', async ({ page }) => {
    const select = page.getByLabel('Document type')
    await focusByKeyboard(page, select)

    const ring = await paintedFocusRing(select)
    expect(
      ring.ratio,
      `ring ${ring.color} on ${ring.surface} measured ${ring.ratio.toFixed(2)}:1`
    ).toBeGreaterThanOrEqual(MINIMUM_RATIO)
  })

  test('the input wrapper carries the same ring, at the same contrast', async ({ page }) => {
    const input = page.getByLabel('File')
    await focusByKeyboard(page, input)

    // The visible box is the wrapper; the `<input>` itself is transparent and unringed by
    // design, so `focus-within` on the parent is what a sighted user actually sees.
    const wrapper = input.locator('xpath=..')
    const ring = await paintedFocusRing(wrapper)
    expect(ring.style, `computed outline: ${ring.style} ${ring.widthPx}px`).not.toBe('none')
    expect(ring.widthPx).toBeGreaterThanOrEqual(MINIMUM_WIDTH_PX)
    expect(
      ring.ratio,
      `ring ${ring.color} on ${ring.surface} measured ${ring.ratio.toFixed(2)}:1`
    ).toBeGreaterThanOrEqual(MINIMUM_RATIO)
  })
})
