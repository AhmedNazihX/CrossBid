/**
 * Placeholder contrast — finding L1 of the 2026-09-15 audit.
 *
 * `--text-placeholder` was `--cb-stone-400` (`#a8a29e`), which measures about 2.5:1 on the
 * white input box. WCAG 2.2 SC 1.4.3 asks 4.5:1 of text this size; the token missed even the
 * 3:1 that applies to no text at all. One `placeholder:text-text-placeholder` utility carries
 * it into every input in the product, so one token is the whole defect and one measurement
 * pins it — but it is measured per surface, because the ratio is against what is painted
 * behind it and the two inputs here sit on different grounds.
 *
 * It is measured in the browser rather than read out of the stylesheet for the reason M6 was:
 * a colour utility naming a token that does not exist emits no declaration at all under
 * Tailwind 4's `--color-*: initial`, and only the painted pixels know (ADR-0092, and B3
 * before it).
 *
 * **Not the sign-in form**, which is where the audit found it and the worst place for it —
 * the worked example a new bidder is asked to read and copy the shape of. The suite's server
 * runs `NEXT_PUBLIC_AUTH_MODE=dev`, where `/login` renders "this build does not sign people
 * in" and has no form at all (`components/auth/sign-in-card.tsx`). Both inputs below carry
 * the same token through the same utility.
 *
 * The API is `FakeApi` (see `support/fake-api.ts`): the real app, answers the test wrote.
 */
import { paintedPlaceholderContrast } from './support/contrast'
import { companyProfileFixture } from './support/fixtures'
import { expect, test } from './support/test'

/** WCAG 2.2 SC 1.4.3 Contrast (Minimum), for text below 18.66 px / not bold. */
const MINIMUM_RATIO = 4.5

test.describe('Placeholder contrast', () => {
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
  })

  test('the TED search box’s example keyword is legible against its box', async ({ page }) => {
    const keyword = page.getByLabel('Keyword')
    await expect(keyword).toHaveAttribute('placeholder', 'cyber security')

    const painted = await paintedPlaceholderContrast(keyword)
    // `getComputedStyle(el, '::placeholder')` falls back to the element's own style when it
    // reads nothing, and the element's own colour is ink at about 18:1 — a pass that would
    // mean the browser stopped resolving the pseudo, not that the placeholder is legible.
    expect(
      painted.placeholderColor,
      'the placeholder resolved to the same colour as a typed value, so nothing was measured'
    ).not.toBe(painted.valueColor)
    expect(
      painted.ratio,
      `placeholder ${painted.placeholderColor} on ${painted.surface} measured ${painted.ratio.toFixed(2)}:1`
    ).toBeGreaterThanOrEqual(MINIMUM_RATIO)
  })

  test('the notice number’s worked example is legible against its box', async ({ page }) => {
    await page.getByRole('button', { name: 'Enter it yourself' }).click()

    const noticeNumber = page.getByLabel('Notice number')
    await expect(noticeNumber).toHaveAttribute('placeholder', '618320-2026')

    const painted = await paintedPlaceholderContrast(noticeNumber)
    expect(
      painted.placeholderColor,
      'the placeholder resolved to the same colour as a typed value, so nothing was measured'
    ).not.toBe(painted.valueColor)
    expect(
      painted.ratio,
      `placeholder ${painted.placeholderColor} on ${painted.surface} measured ${painted.ratio.toFixed(2)}:1`
    ).toBeGreaterThanOrEqual(MINIMUM_RATIO)
  })
})
