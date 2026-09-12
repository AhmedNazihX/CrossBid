import type { MatrixRow } from '@/lib/bids'
import type { SourceDocument } from '@/components/pdf/source-panel'

/**
 * Every document a citation on this screen can open: the tender pack first, then the
 * bidder's own files the check cited.
 *
 * The check searches two corpora — the tender pack and the company's documents — so an
 * evidence citation may name a file that is not part of the bid. Those files are added here
 * with an unknown page count, which the source panel renders as `p. N / ?`, rather than
 * being dropped and leaving a citation that goes nowhere.
 */
export function citableDocuments(
  tenderDocuments: readonly SourceDocument[],
  rows: readonly MatrixRow[]
): readonly SourceDocument[] {
  const known = new Set(tenderDocuments.map((document) => document.id))
  const extra = new Map<string, SourceDocument>()
  for (const row of rows) {
    for (const evidence of row.evidence) {
      if (known.has(evidence.document_id) || extra.has(evidence.document_id)) {
        continue
      }
      extra.set(evidence.document_id, {
        id: evidence.document_id,
        name: evidence.document_name,
        pages: 0,
        unread_pages: [],
      })
    }
  }
  return [...tenderDocuments, ...extra.values()]
}
