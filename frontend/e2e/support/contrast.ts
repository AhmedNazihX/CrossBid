/**
 * The contrast a control is actually painted with, read from computed styles (WCAG 2.x).
 *
 * Why this exists: the workspace's "Review verdict" control shipped as white text on a
 * transparent ground, 1.02:1. The class named `bg-accent-default`, a colour the `@theme`
 * block never declares; under Tailwind 4's `--color-*: initial` an unknown colour utility
 * emits *no declaration at all* rather than an error, so `tsc`, ESLint and the build were
 * all green. Only the painted pixels knew. So this reads what the browser resolved — the
 * element's own `background-color`, every ancestor's behind it, and its `color` — and
 * composites them the way the screen does.
 *
 * Chrome serialises computed colours as `rgb()` / `rgba()` whatever the stylesheet wrote,
 * hex tokens included, so that is the one syntax parsed here.
 */
import type { Locator } from '@playwright/test'

export interface Rgba {
  readonly r: number
  readonly g: number
  readonly b: number
  /** 0 (transparent) to 1 (opaque). */
  readonly a: number
}

const OPAQUE_WHITE: Rgba = { r: 255, g: 255, b: 255, a: 1 }
const CSS_COLOR =
  /^rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)(?:\s*[,/]\s*([\d.]+%?))?\s*\)$/

function parseAlpha(raw: string): number {
  return raw.endsWith('%') ? Number(raw.slice(0, -1)) / 100 : Number(raw)
}

export function parseCssColor(value: string): Rgba {
  const match = value.match(CSS_COLOR)
  if (match === null) {
    throw new Error(`Cannot read the computed colour "${value}"; expected rgb() or rgba()`)
  }
  const alpha: string | undefined = match[4]
  return {
    r: Number(match[1]),
    g: Number(match[2]),
    b: Number(match[3]),
    a: alpha === undefined ? 1 : parseAlpha(alpha),
  }
}

/** `top` painted over `under` (source-over). */
export function composite(top: Rgba, under: Rgba): Rgba {
  const a = top.a + under.a * (1 - top.a)
  if (a === 0) return { r: 0, g: 0, b: 0, a: 0 }
  const channel = (t: number, u: number) => (t * top.a + u * under.a * (1 - top.a)) / a
  return {
    r: channel(top.r, under.r),
    g: channel(top.g, under.g),
    b: channel(top.b, under.b),
    a,
  }
}

function linearise(channel: number): number {
  const c = channel / 255
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
}

export function relativeLuminance({ r, g, b }: Rgba): number {
  return 0.2126 * linearise(r) + 0.7152 * linearise(g) + 0.0722 * linearise(b)
}

export function contrastRatio(first: Rgba, second: Rgba): number {
  const lighter = Math.max(relativeLuminance(first), relativeLuminance(second))
  const darker = Math.min(relativeLuminance(first), relativeLuminance(second))
  return (lighter + 0.05) / (darker + 0.05)
}

export interface PaintedContrast {
  /** Text against the background the eye sees behind it, ancestors composited in. */
  readonly ratio: number
  /** The element's *own* background alpha: 0 is the shipped defect, 1 is a painted control. */
  readonly ownBackgroundAlpha: number
  readonly color: string
  readonly ownBackground: string
}

export async function paintedContrast(locator: Locator): Promise<PaintedContrast> {
  const painted = await locator.evaluate((element) => {
    const layers = (node: Element | null): readonly string[] =>
      node === null
        ? []
        : [getComputedStyle(node).backgroundColor, ...layers(node.parentElement)]
    return { color: getComputedStyle(element).color, backgrounds: layers(element) }
  })
  const backgrounds = painted.backgrounds.map(parseCssColor)
  const own = backgrounds[0] ?? OPAQUE_WHITE
  // The root paints over the viewport's white; each descendant paints over what is beneath.
  const effective = backgrounds.reduceRight((under, top) => composite(top, under), OPAQUE_WHITE)
  const text = composite(parseCssColor(painted.color), effective)
  return {
    ratio: contrastRatio(text, effective),
    ownBackgroundAlpha: own.a,
    color: painted.color,
    ownBackground: painted.backgrounds[0] ?? 'none',
  }
}
