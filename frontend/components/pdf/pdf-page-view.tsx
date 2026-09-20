'use client'

import { useEffect, useRef, useState } from 'react'
import { cn } from 'cn'

import { Icon } from '@/components/ui/icons'
import { locateQuote } from './quote-match'

/** The rendered page's width is the container's, capped so a wide drawer does not blur it. */
const MAX_RENDER_WIDTH = 1_400
/** Above this the canvas costs more memory than the sharpness is worth on a HiDPI screen. */
const MAX_DEVICE_SCALE = 2

export interface PdfPageViewProps {
  /** The short-lived signed URL. Read once per document; later rotations do not re-download. */
  readonly url: string
  /** Changes here, not in `url`, are what mean "a different file". */
  readonly documentId: string
  readonly documentName: string
  readonly page: number
  /** The cited sentence to mark on the page, when this page is being shown for a citation. */
  readonly quote?: string
  readonly className?: string
}

type Phase =
  | { readonly kind: 'loading' }
  | { readonly kind: 'ready' }
  | { readonly kind: 'failed'; readonly reason: string }

/** Whether the quote was looked for on the page now showing, and whether it was found. */
type Marked = 'none' | 'found' | 'missing'

/**
 * One page of a PDF, rendered by pdf.js, with the cited sentence marked on it (ADR-0105).
 *
 * **No artboard.** `Main.dc.html` draws the source as a browser-rendered frame, and ADR-0014
 * put a PDF library out of the tech stack *"until the native viewer proves insufficient"*. It
 * has: Chrome's PDFium honours only `page`, `zoom`, `view`, `nameddest` and `toolbar` in a URL
 * fragment and **ignores `search`**, so there is no way to mark a word inside an `<iframe>` we
 * do not control. Firefox's own pdf.js honours it, which makes the point rather than answering
 * it — a feature that works in one browser and silently does nothing in the other is not a
 * feature.
 *
 * **Three layers, in this order.** A `<canvas>` carries the real glyphs; pdf.js's `TextLayer`
 * puts transparent, selectable text over it in the right places; the highlight boxes sit
 * between them and blend with `multiply`, so they tint the sentence rather than cover it.
 *
 * **The text layer is not optional.** A bare canvas is a picture: nothing in it reaches a
 * screen reader, nothing can be selected, and the browser's own find-in-page goes blind. The
 * `<iframe>` this replaces had all three for free, so leaving the text layer out would have
 * been a straight accessibility regression traded for a highlight.
 *
 * **The bytes are fetched once and handed over as data, not as a URL.** The signed URL lives
 * at most ten minutes (`useSignedUrl` refreshes it thirty seconds early), so passing pdf.js a
 * URL would mean a fresh download on every rotation and a 403 in the middle of a render if one
 * were ever late. The fetch is keyed on the document, so a rotation changes nothing here.
 *
 * **Nothing fails silently.** If the worker will not start, the fetch is refused, or rendering
 * throws, the page falls back to the `<iframe>` with a line saying it is unmarked; if the quote
 * cannot be found, the page renders and says that instead. A highlight in the wrong place would
 * be worse than no highlight, so `locateQuote` never guesses.
 */
export function PdfPageView({
  url,
  documentId,
  documentName,
  page,
  quote,
  className,
}: PdfPageViewProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const textLayerRef = useRef<HTMLDivElement | null>(null)
  const highlightRef = useRef<HTMLDivElement | null>(null)
  // The loaded document, kept across page changes so paging never re-downloads or re-parses.
  const documentRef = useRef<PdfDocument | undefined>(undefined)
  const [phase, setPhase] = useState<Phase>({ kind: 'loading' })
  const [marked, setMarked] = useState<Marked>('none')
  // Bumped when the document is ready, to run the render effect without putting a pdf.js
  // object into React state (it is mutable, and comparing it on every render is meaningless).
  const [loadedAt, setLoadedAt] = useState(0)

  // The URL is read when the document is first fetched and deliberately not a dependency:
  // `useSignedUrl` hands out a new string every ten minutes for the very same bytes.
  const urlRef = useRef(url)
  urlRef.current = url

  useEffect(() => {
    let isStale = false
    const controller = new AbortController()
    setPhase({ kind: 'loading' })
    documentRef.current = undefined

    void (async () => {
      try {
        const pdfjs = await import('pdfjs-dist')
        // A same-origin `_next/static` asset, which is what `worker-src 'self'` allows.
        pdfjs.GlobalWorkerOptions.workerSrc = new URL(
          'pdfjs-dist/build/pdf.worker.min.mjs',
          import.meta.url
        ).toString()

        const response = await fetch(urlRef.current, { signal: controller.signal })
        if (!response.ok) {
          throw new Error(`the document answered ${response.status}`)
        }
        const bytes = new Uint8Array(await response.arrayBuffer())
        if (isStale) return

        const task = pdfjs.getDocument({
          data: bytes,
          // Both default to null, and a document that needs one renders without it after a
          // console warning rather than failing — so a scanned page would quietly lose its
          // image. `scripts/copy-pdfjs-assets.mjs` puts these where the URLs point.
          wasmUrl: '/pdfjs/wasm/',
          standardFontDataUrl: '/pdfjs/standard_fonts/',
        })
        const pdf = await task.promise
        if (isStale) {
          void task.destroy()
          return
        }
        documentRef.current = { task, pdf, pdfjs }
        setLoadedAt(Date.now())
        setPhase({ kind: 'ready' })
      } catch (cause: unknown) {
        if (isStale || controller.signal.aborted) return
        setPhase({ kind: 'failed', reason: describe(cause) })
      }
    })()

    return () => {
      isStale = true
      controller.abort()
      const held = documentRef.current
      documentRef.current = undefined
      // `destroy` is the loading task's, not the proxy's: it tears down the worker port too.
      if (held !== undefined) void held.task.destroy()
    }
  }, [documentId])

  useEffect(() => {
    const held = documentRef.current
    const canvas = canvasRef.current
    const container = containerRef.current
    if (held === undefined || canvas === null || container === null || phase.kind !== 'ready') {
      return
    }
    let isStale = false
    let task: { cancel: () => void } | undefined
    let layer: { cancel: () => void } | undefined

    void (async () => {
      try {
        const pdfPage = await held.pdf.getPage(clampPage(page, held.pdf.numPages))
        if (isStale) return

        const unscaled = pdfPage.getViewport({ scale: 1 })
        const width = Math.min(container.clientWidth || unscaled.width, MAX_RENDER_WIDTH)
        const scale = width / unscaled.width
        const viewport = pdfPage.getViewport({ scale })
        const device = Math.min(window.devicePixelRatio || 1, MAX_DEVICE_SCALE)

        canvas.width = Math.floor(viewport.width * device)
        canvas.height = Math.floor(viewport.height * device)
        canvas.style.width = `${Math.floor(viewport.width)}px`
        canvas.style.height = `${Math.floor(viewport.height)}px`
        const context = canvas.getContext('2d')
        if (context === null) {
          throw new Error('this browser gave no 2d canvas context')
        }
        context.setTransform(device, 0, 0, device, 0, 0)
        context.clearRect(0, 0, viewport.width, viewport.height)

        const render = pdfPage.render({ canvas, canvasContext: context, viewport })
        task = render
        await render.promise
        if (isStale) return

        const textHost = textLayerRef.current
        const highlightHost = highlightRef.current
        if (textHost === null || highlightHost === null) return
        for (const host of [textHost, highlightHost]) {
          host.replaceChildren()
          host.style.width = `${Math.floor(viewport.width)}px`
          host.style.height = `${Math.floor(viewport.height)}px`
        }
        // `TextLayer` positions every span through CSS and reads this one variable to do it;
        // without it each span computes `font-size: calc(NaN)` and the whole layer piles up
        // in the top-left corner. The matching rules are the vendored block in `globals.css`.
        textHost.style.setProperty('--total-scale-factor', String(scale))

        // `streamTextContent()`, never `getTextContent()`. The convenience wrapper is
        // `for await (const value of readableStream)`, and **async iteration of a
        // `ReadableStream` is missing from Safari before 18.4** — it throws
        // `undefined is not a function`, which is what a bidder reported from the real
        // product on 2026-09-20. `TextLayer` reads the stream with `getReader()`, which every
        // browser has, so handing it the stream directly is both the fix and one pass fewer.
        const textLayer = new held.pdfjs.TextLayer({
          textContentSource: pdfPage.streamTextContent(),
          container: textHost,
          viewport,
        })
        layer = textLayer
        await textLayer.render()
        if (isStale) return

        setMarked(
          paintHighlights(textLayer, highlightHost, quote)
            ? 'found'
            : quote === undefined
              ? 'none'
              : 'missing'
        )
      } catch (cause: unknown) {
        // A cancelled render is the expected outcome of paging quickly; it is not a failure.
        if (isStale || isCancellation(cause)) return
        setPhase({ kind: 'failed', reason: describe(cause) })
      }
    })()

    return () => {
      isStale = true
      task?.cancel()
      layer?.cancel()
    }
  }, [loadedAt, page, quote, phase.kind])

  if (phase.kind === 'failed') {
    // The browser's own viewer still works; only the marking is lost, and the note says so
    // rather than leaving a reader to wonder why this page looks different from the last.
    return (
      <div className={cn('flex flex-col gap-2', className)}>
        <p className="m-0 flex items-start gap-2 [font:var(--type-body-sm)] text-text-muted">
          <Icon name="alert" size={14} />
          <span>
            This page is shown by the browser, without the citation marked on it: {phase.reason}
          </span>
        </p>
        <iframe
          key={`${documentId}:${page}`}
          src={`${url}#page=${page}`}
          title={`${documentName}, page ${page}`}
          className="block h-[calc(100dvh-320px)] min-h-[380px] w-full border border-border-default bg-surface-card shadow-sm"
        />
      </div>
    )
  }

  return (
    <div className={cn('flex flex-col gap-2', className)}>
      {marked === 'missing' && (
        <p className="m-0 flex items-start gap-2 [font:var(--type-body-sm)] text-text-muted">
          <Icon name="alert" size={14} />
          <span>
            The cited words were not found on page {page}, so nothing is marked. The quote is
            under the requirement in the matrix.
          </span>
        </p>
      )}
      <div
        ref={containerRef}
        className="relative w-full overflow-auto"
        aria-busy={phase.kind === 'loading'}
      >
        <div className="relative mx-auto w-fit">
          <canvas ref={canvasRef} className="block bg-surface-card shadow-sm" />
          {/* Between the glyphs and the selectable text: `multiply` tints the sentence
              instead of hiding it, which is how pdf.js marks its own find results. */}
          <div
            ref={highlightRef}
            aria-hidden="true"
            className="pointer-events-none absolute top-0 left-0 mix-blend-multiply"
          />
          <div ref={textLayerRef} className="textLayer" />
        </div>
        {phase.kind === 'loading' && (
          <p role="status" className="m-0 py-10 text-center text-text-muted">
            Opening {documentName}…
          </p>
        )}
      </div>
    </div>
  )
}

type Pdfjs = typeof import('pdfjs-dist')

interface PdfDocument {
  readonly task: ReturnType<Pdfjs['getDocument']>
  readonly pdf: Awaited<ReturnType<Pdfjs['getDocument']>['promise']>
  readonly pdfjs: Pdfjs
}

/**
 * Draws a box over every run of the page that the quote covers, and says whether it found any.
 *
 * The geometry is the browser's: a `Range` over the matched characters of the text layer's own
 * spans, asked for its client rects. Computing it by hand from each item's transform is the
 * alternative, and it is both more code and wrong on the first rotated page.
 */
function paintHighlights(
  textLayer: { readonly textDivs: HTMLElement[]; readonly textContentItemsStr: string[] },
  host: HTMLElement,
  quote: string | undefined
): boolean {
  if (quote === undefined || quote === '') {
    return false
  }
  const spans = locateQuote(textLayer.textContentItemsStr, quote)
  if (spans.length === 0) {
    return false
  }
  const origin = host.getBoundingClientRect()
  let painted = 0
  for (const span of spans) {
    const div = textLayer.textDivs[span.itemIndex]
    const node = div?.firstChild
    if (div === undefined || node === null || node === undefined) continue
    const length = node.textContent?.length ?? 0
    const range = document.createRange()
    try {
      range.setStart(node, Math.min(span.start, length))
      range.setEnd(node, Math.min(span.end, length))
    } catch {
      // A text layer that does not line up with the items it reported is not worth a throw.
      continue
    }
    for (const rect of Array.from(range.getClientRects())) {
      if (rect.width === 0 || rect.height === 0) continue
      const box = document.createElement('div')
      // The browser suite asserts on these: a canvas cannot be queried by role, and a pixel
      // diff would not say whether the box landed on the right sentence.
      box.dataset.testid = 'pdf-highlight'
      box.style.position = 'absolute'
      box.style.left = `${rect.left - origin.left}px`
      box.style.top = `${rect.top - origin.top}px`
      box.style.width = `${rect.width}px`
      box.style.height = `${rect.height}px`
      box.style.backgroundColor = 'var(--surface-accent-soft)'
      box.style.borderRadius = '2px'
      host.append(box)
      painted += 1
    }
  }
  return painted > 0
}

function clampPage(page: number, total: number): number {
  const floor = Math.max(1, Math.trunc(page))
  return total > 0 ? Math.min(floor, total) : floor
}

function isCancellation(cause: unknown): boolean {
  const name = cause instanceof Error ? cause.name : ''
  return (
    name === 'RenderingCancelledException' || name === 'AbortException' || name === 'AbortError'
  )
}

function describe(cause: unknown): string {
  return cause instanceof Error ? cause.message : 'the page could not be rendered'
}
