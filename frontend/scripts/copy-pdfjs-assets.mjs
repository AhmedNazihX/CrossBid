/**
 * Copies the pdf.js runtime assets that `getDocument` fetches over HTTP into `public/pdfjs/`
 * (ADR-0105).
 *
 * `cMapUrl`, `standardFontDataUrl` and `wasmUrl` all default to **null**, and a document that
 * needs one of them does not fail — pdf.js emits a `warn()` and renders the page without the
 * thing it could not decode. That is exactly the silent failure this repo forbids, and it
 * lands on the pages that matter most here: a scanned tender page is an image, and JBIG2 and
 * JPEG 2000 images are decoded by the WASM the viewer would not have.
 *
 * Copied rather than committed, so the bytes track the installed version instead of drifting
 * from it; `public/pdfjs/` is gitignored. Run by the `prebuild` and `predev` npm lifecycle
 * hooks, which is what puts it in CI and in the Docker builder stage (`npm run build`) as well
 * as on a developer's machine.
 *
 * **`cmaps/` is deliberately not copied.** It is 1.6 MB of CJK character maps, and this
 * product reads EU tenders in Latin-script languages. Add it here if that ever changes.
 */
import { cp, mkdir } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { dirname, join } from 'node:path'

const require = createRequire(import.meta.url)
const pdfjsRoot = dirname(require.resolve('pdfjs-dist/package.json'))
const target = join(import.meta.dirname, '..', 'public', 'pdfjs')

const DIRECTORIES = ['wasm', 'standard_fonts']

await mkdir(target, { recursive: true })
for (const name of DIRECTORIES) {
  await cp(join(pdfjsRoot, name), join(target, name), { recursive: true })
}
console.log(`pdf.js assets copied to public/pdfjs/: ${DIRECTORIES.join(', ')}`)
