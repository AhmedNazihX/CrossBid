import type { Locator } from '@playwright/test'

/** A box in CSS pixels, relative to the canvas's own top-left corner. */
export interface InkBand {
  readonly left: number
  readonly top: number
  readonly right: number
  readonly bottom: number
}

/**
 * The bounding boxes of the bands of ink actually painted on a canvas, top to bottom.
 *
 * This exists because a highlight drawn over pdf.js's text layer **inherits that layer's
 * geometry**: if the text layer is misaligned with the page the canvas painted, the highlight
 * is misaligned with it by exactly the same amount, and every assertion that compares the
 * highlight to the text layer still passes. The glyphs on the canvas are the only independent
 * witness to where the words really are, so a test that the highlight is in the *right* place
 * — rather than merely present — has to read them.
 *
 * Rows are grouped into bands by blank scanlines, which on a three-line fixture is exactly one
 * band per line. `getImageData` is safe here: pdf.js paints the canvas directly, so it is not
 * tainted by a cross-origin image.
 */
export async function inkBands(canvas: Locator, maxBands = 8): Promise<readonly InkBand[]> {
  return canvas.evaluate((element, limit) => {
    const node = element as HTMLCanvasElement
    const context = node.getContext('2d')
    if (context === null) return []
    const { width, height } = node
    // The canvas is painted at devicePixelRatio; every result is converted back to CSS px so
    // it can be compared with a `boundingBox()`.
    const scale = node.clientWidth === 0 ? 1 : width / node.clientWidth
    const { data } = context.getImageData(0, 0, width, height)
    const isInk = (x: number, y: number): boolean => {
      const at = (y * width + x) * 4
      const alpha = data[at + 3] ?? 0
      if (alpha === 0) return false
      // Anything meaningfully darker than the white page counts as a glyph.
      return ((data[at] ?? 255) + (data[at + 1] ?? 255) + (data[at + 2] ?? 255)) / 3 < 160
    }

    const bands: { left: number; top: number; right: number; bottom: number }[] = []
    let open: { left: number; top: number; right: number; bottom: number } | undefined
    for (let y = 0; y < height; y += 1) {
      let first = -1
      let last = -1
      for (let x = 0; x < width; x += 1) {
        if (!isInk(x, y)) continue
        if (first === -1) first = x
        last = x
      }
      if (first === -1) {
        if (open !== undefined) {
          bands.push(open)
          open = undefined
          if (bands.length >= limit) break
        }
        continue
      }
      open =
        open === undefined
          ? { left: first, top: y, right: last, bottom: y }
          : {
              left: Math.min(open.left, first),
              top: open.top,
              right: Math.max(open.right, last),
              bottom: y,
            }
    }
    if (open !== undefined && bands.length < limit) bands.push(open)
    return bands.map((band) => ({
      left: band.left / scale,
      top: band.top / scale,
      right: band.right / scale,
      bottom: band.bottom / scale,
    }))
  }, maxBands)
}
