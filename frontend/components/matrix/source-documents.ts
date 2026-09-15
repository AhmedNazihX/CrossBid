import type { MatrixRow } from '@/lib/bids'
import type { SourceDocument } from '@/components/pdf/source-panel'

/** The address a citation carries — the shape both `Evidence` and a chat `Citation` share. */
export interface CitedDocument {
  readonly document_id: string
  readonly document_name: string
}

/**
 * Every document a citation on this screen can open: the tender pack first, then the
 * bidder's own files the check — or an answer — cited.
 *
 * The check searches two corpora — the tender pack and the company's documents — so an
 * evidence citation may name a file that is not part of the bid. Those files are added here
 * with an unknown page count, which the source panel renders as `p. N / ?`, rather than
 * being dropped and leaving a citation that goes nowhere. A chat answer (S4.6.1) searches
 * the same two corpora with the same tools, so its citations are folded in the same way:
 * without this, a company document cited only in an answer would light up as a link and
 * open nothing.
 */
export function citableDocuments(
  tenderDocuments: readonly SourceDocument[],
  rows: readonly MatrixRow[],
  alsoCited: readonly CitedDocument[] = []
): readonly SourceDocument[] {
  const known = new Set(tenderDocuments.map((document) => document.id))
  const extra = new Map<string, SourceDocument>()
  const cited = [...rows.flatMap((row) => row.evidence), ...alsoCited]
  for (const item of cited) {
    if (known.has(item.document_id) || extra.has(item.document_id)) {
      continue
    }
    extra.set(item.document_id, {
      id: item.document_id,
      name: item.document_name,
      pages: 0,
      unread_pages: [],
    })
  }
  return [...tenderDocuments, ...extra.values()]
}
