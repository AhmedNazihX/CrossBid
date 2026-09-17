import { Notice } from '@/components/ui/notice'
import type { components } from '@/lib/api'

type BidDocument = components['schemas']['BidDocumentResponse']

/**
 * Says, on the bid, that Ask cannot read this pack — because nothing else does.
 *
 * A bid analysed before 2026-09-15 had its documents parsed and extracted from without a
 * searchable copy being kept, so the matrix is complete and every question asked of the tender
 * retrieves nothing (ADR-0098). *Problems flagged* reads 0 for such a bid, and reads it
 * correctly: nothing failed, the step did not exist. The only way to find out used to be to
 * ask the agent a question it could not answer, and read a refusal that blamed the documents.
 *
 * `role="status"` rather than `alert`: the bid is fine, the matrix is fine, and the reviewer is
 * not being interrupted — this is worth announcing to a screen reader when it appears, not
 * worth taking their attention away from what they were reading.
 */
export function UnsearchablePack({
  documents,
}: {
  readonly documents: readonly BidDocument[]
}) {
  const unsearchable = documents.filter((document) => !document.searchable)
  if (documents.length === 0 || unsearchable.length === 0) return null

  const all = unsearchable.length === documents.length
  return (
    <Notice
      role="status"
      title={all ? 'Ask cannot read this pack' : 'Ask cannot read all of this pack'}
      className="mb-6"
    >
      {all
        ? 'These documents were analysed before Crossbid kept a searchable copy of them, so a question about the tender has nothing to search. '
        : `${unsearchable.length} of ${documents.length} documents have no searchable copy, so a question about the tender searches only the rest. `}
      The requirements, the matrix and the verdict are unaffected — they were read from the
      documents directly. Re-indexing the bid restores Ask.
    </Notice>
  )
}
