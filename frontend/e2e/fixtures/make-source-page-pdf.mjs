/**
 * Writes `source-page.pdf`, the one-page PDF the browser tests render (ADR-0105).
 *
 * Hand-built rather than drawn with a library, and deliberately dull: **uncompressed** (no
 * FlateDecode in the way of a reader), **base-14 Helvetica** (not embedded, so pdf.js
 * substitutes a system font and the test needs no `public/pdfjs/standard_fonts`), and
 * WinAnsi-encoded so the German umlaut is one byte. The result is ~1 KB and every byte of it
 * is legible in a diff.
 *
 * The cited sentence is **split across two lines**, which is the point: it is the case a real
 * tender always presents and the one a naive matcher fails. The second line is a distractor
 * that must never be highlighted.
 *
 * Regenerate with `node e2e/fixtures/make-source-page-pdf.mjs`. The output is committed; this
 * script is never run by CI.
 */
import { writeFile } from 'node:fs/promises'
import { join } from 'node:path'

/** Kept in step with `awaitingReviewBidFixture().requirements[0].source_text`. */
const CITED_LINE_ONE = 'Der Bieter hat einen Mindestjahresumsatz von 2 Mio. EUR in den'
const CITED_LINE_TWO = 'letzten drei Gesch\\344ftsjahren nachzuweisen.'
const DISTRACTOR = 'Diese Zeile ist nicht zitiert und darf nicht markiert werden.'

const content = `BT
/F1 12 Tf
60 760 Td
(${CITED_LINE_ONE}) Tj
0 -18 Td
(${CITED_LINE_TWO}) Tj
ET
BT
/F1 12 Tf
60 700 Td
(${DISTRACTOR}) Tj
ET
`

const objects = [
  '<< /Type /Catalog /Pages 2 0 R >>',
  '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
  '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] ' +
    '/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>',
  `<< /Length ${Buffer.byteLength(content, 'latin1')} >>\nstream\n${content}endstream`,
  '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>',
]

let pdf = '%PDF-1.4\n'
const offsets = []
objects.forEach((body, index) => {
  offsets.push(Buffer.byteLength(pdf, 'latin1'))
  pdf += `${index + 1} 0 obj\n${body}\nendobj\n`
})

const xrefAt = Buffer.byteLength(pdf, 'latin1')
pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`
for (const offset of offsets) {
  pdf += `${String(offset).padStart(10, '0')} 00000 n \n`
}
pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefAt}\n%%EOF\n`

const out = join(import.meta.dirname, 'source-page.pdf')
await writeFile(out, Buffer.from(pdf, 'latin1'))
console.log(`wrote ${out} (${Buffer.byteLength(pdf, 'latin1')} bytes)`)
