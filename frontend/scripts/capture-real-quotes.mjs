/**
 * Captures the real citation-matching corpus that `quote-match.test.ts` measures against
 * (ADR-0105).
 *
 * For every requirement in the three saved live extractions, it reads the page pdf.js reads
 * and stores that page's text items beside the quote the extractor produced. The result is a
 * JSON file, so the unit suite measures the matcher against **three real tender packs** in
 * milliseconds, with no PDFs, no pdf.js and no network — and a change that quietly costs
 * citations fails on the next push instead of in a bidder's browser.
 *
 * Only the pages that are actually cited are kept, deduplicated. Run manually after changing
 * the fixtures; CI never regenerates it:
 *
 *     node scripts/capture-real-quotes.mjs
 */
import { readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'

const ROOT = path.resolve(import.meta.dirname, '../../backend/tests/fixtures')
const OUT = path.resolve(import.meta.dirname, '../components/pdf/__fixtures__/real-quotes.json')

const pdfjs = await import('pdfjs-dist/legacy/build/pdf.mjs')

/** Every page of one PDF, as the array of text-item strings pdf.js reports. */
async function readPages(file) {
  const pdf = await pdfjs.getDocument({ data: new Uint8Array(await readFile(file)) }).promise
  const pages = []
  for (let n = 1; n <= pdf.numPages; n += 1) {
    const content = await (await pdf.getPage(n)).getTextContent()
    pages.push(content.items.map((item) => ('str' in item ? item.str : '')))
  }
  await pdf.cleanup()
  return pages
}

async function resolveDocument(lang, name) {
  for (const candidate of [
    path.join(ROOT, 'tenders', lang, name),
    path.join(ROOT, 'tenders', lang, 'documents', name),
  ]) {
    try {
      await readFile(candidate)
      return candidate
    } catch {
      /* try the next place */
    }
  }
  return undefined
}

const pages = []
const index = new Map()
const cases = []

for (const lang of ['de', 'fr', 'en']) {
  const extraction = JSON.parse(
    await readFile(path.join(ROOT, `extractions/${lang}.live.json`), 'utf8')
  )
  const documents = new Map()
  for (const requirement of extraction.requirements) {
    if (requirement.page === null) continue
    const file = await resolveDocument(lang, requirement.document_name)
    if (file === undefined) continue
    if (!documents.has(file)) documents.set(file, await readPages(file))
    const items = documents.get(file)[requirement.page - 1]
    if (items === undefined) continue
    const key = `${requirement.document_name}#${requirement.page}`
    if (!index.has(key)) {
      index.set(key, pages.length)
      pages.push(items)
    }
    cases.push({
      lang,
      document: requirement.document_name,
      page: requirement.page,
      pageIndex: index.get(key),
      quote: requirement.source_text,
    })
  }
}

await writeFile(
  OUT,
  `${JSON.stringify({ capturedWith: `pdfjs-dist ${pdfjs.version}`, pages, cases }, null, 0)}\n`
)
console.log(`wrote ${OUT}: ${cases.length} citations over ${pages.length} pages`)
