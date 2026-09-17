/**
 * The focus ring a control is actually painted with, read from computed styles (WCAG 2.2).
 *
 * Why this exists, and why it is not `contrast.ts`: that helper composites an element's own
 * background to judge *text* on it. A focus ring is not on the element — it is drawn
 * `outline-offset` outside the border box, so the colour it must stand out from is the
 * surface *behind* the control, and the thing to measure is whether the ring exists at all.
 *
 * Both halves of finding M6 are invisible to `tsc`, ESLint and the build:
 *
 * - **It can be silently removed.** A ring drawn as `box-shadow` from a rule in
 *   `@layer base` loses to any `shadow-*` utility, because Tailwind's utilities layer comes
 *   after base and the cascade decides by layer before specificity. `<select>` carries
 *   `shadow-xs`; it therefore had no ring at all, and nothing anywhere reported it.
 * - **It can be too faint.** The design system's `--shadow-focus` is ink at 20 %, which
 *   composites to about 1.55:1 against the canvas. SC 1.4.11 asks for 3:1.
 *
 * So this reads `outline-*` as the browser resolved it, composites the surface underneath,
 * and returns both the geometry and the ratio. Chrome serialises computed colours as
 * `rgb()` / `rgba()` whatever the stylesheet wrote, which is what `parseCssColor` parses.
 */
import type { Locator, Page } from '@playwright/test'

import { composite, contrastRatio, parseCssColor, type Rgba } from './contrast'

const OPAQUE_WHITE: Rgba = { r: 255, g: 255, b: 255, a: 1 }

/**
 * The ratio of a ring that is not painted. Chrome keeps resolving `outline-color` and
 * `outline-width` while `outline-style` is `none` — the sheet's own `outline: none` computes
 * to `none` at 3 px in the UA's colour — so a naive reading of those two properties reports a
 * healthy ratio for a control with no ring on it whatsoever. That is not a hypothetical: the
 * first version of this spec passed against the defect it was written for, which is ADR-0063
 * a second time. Nothing against nothing is 1:1, and 1:1 fails every threshold.
 */
const NO_RING_RATIO = 1

export interface PaintedFocusRing {
  /** `none` is the shipped defect: the control has no outline to see. */
  readonly style: string
  readonly widthPx: number
  readonly offsetPx: number
  /**
   * The ring composited over the surface behind the control, against that surface — or
   * `NO_RING_RATIO` when `style`/`widthPx` say nothing is drawn.
   */
  readonly ratio: number
  readonly color: string
  readonly surface: string
  /** What the browser itself says about `:focus-visible`, so a test cannot measure a control that was never focused. */
  readonly isFocusVisible: boolean
}

/**
 * Focus `target` the way a keyboard user does, and wait until the paint has settled.
 *
 * Two traps, both of which produced a wrong reading here before they were understood:
 *
 * - `:focus-visible` follows the user's last input modality, so a Playwright `click()` — a
 *   real mouse press — gives `:focus` and no ring, which is correct behaviour and useless
 *   here. One `Tab` puts the page in keyboard modality; focusing after that matches
 *   `:focus-visible`.
 * - The controls carry `transition-shadow` at `--duration-fast`, and `getComputedStyle`
 *   during a transition returns the *interpolated* value. Reading immediately after focus
 *   therefore reports the unfocused shadow and makes a working ring look absent. Waiting on
 *   `getAnimations()` is exact, where a fixed sleep would be a guess.
 */
export async function focusByKeyboard(page: Page, target: Locator): Promise<void> {
  await page.keyboard.press('Tab')
  await target.focus()
  await settle(target)
}

/** Resolve once every transition and animation on `locator` and its parent has finished. */
async function settle(locator: Locator): Promise<void> {
  await locator.evaluate(async (element) => {
    const running = [element, element.parentElement].flatMap((node) =>
      node === null ? [] : node.getAnimations()
    )
    await Promise.all(running.map((animation) => animation.finished.catch(() => undefined)))
  })
}

export async function paintedFocusRing(locator: Locator): Promise<PaintedFocusRing> {
  const painted = await locator.evaluate((element) => {
    const style = getComputedStyle(element)
    const behind = (node: Element | null): readonly string[] =>
      node === null
        ? []
        : [getComputedStyle(node).backgroundColor, ...behind(node.parentElement)]
    return {
      style: style.outlineStyle,
      width: style.outlineWidth,
      offset: style.outlineOffset,
      color: style.outlineColor,
      // The element's own background is deliberately skipped: the ring is drawn outside it.
      surfaces: behind(element.parentElement),
      isFocusVisible: element.matches(':focus-visible'),
    }
  })
  const surface = painted.surfaces
    .map(parseCssColor)
    .reduceRight((under, top) => composite(top, under), OPAQUE_WHITE)
  const widthPx = Number.parseFloat(painted.width)
  const isDrawn = painted.style !== 'none' && painted.style !== 'hidden' && widthPx > 0
  const ring = composite(parseCssColor(painted.color), surface)
  return {
    style: painted.style,
    widthPx,
    offsetPx: Number.parseFloat(painted.offset),
    ratio: isDrawn ? contrastRatio(ring, surface) : NO_RING_RATIO,
    color: isDrawn ? painted.color : 'none',
    surface: painted.surfaces[0] ?? 'none',
    isFocusVisible: painted.isFocusVisible,
  }
}
