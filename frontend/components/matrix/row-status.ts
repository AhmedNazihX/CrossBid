import type { BadgeTone } from '@/components/ui/badge'
import type { MatrixRow, RowStatus } from '@/lib/bids'

/**
 * The four row words of the fixed vocabulary (ADR-0013) and the badge tone each is shown
 * on, as the Evidence column of `Main.dc.html` and the phone cards of
 * `WorkspacePhone.dc.html` use them. Never Pass/Fail, never Approved: the label is the
 * whole vocabulary, and the tone only repeats what the label already says.
 */
export const ROW_STATUS_LABELS: Readonly<Record<RowStatus, string>> = {
  supported: 'Supported',
  partially_supported: 'Partially supported',
  unsupported: 'Unsupported',
  not_applicable: 'Not applicable',
}

export const ROW_STATUS_TONES: Readonly<Record<RowStatus, BadgeTone>> = {
  supported: 'success',
  partially_supported: 'warning',
  unsupported: 'danger',
  not_applicable: 'neutral',
}

/** Reading order of the summary strip: the good news, then what the reviewer must act on. */
export const ROW_STATUS_ORDER: readonly RowStatus[] = [
  'supported',
  'partially_supported',
  'unsupported',
  'not_applicable',
]

/**
 * One sentence per status, for the row that has no evidence to show. Only `supported` is
 * guaranteed to carry a citation, so the other three need to say why the list is empty
 * rather than leave a blank where a quote would be.
 */
export const ROW_STATUS_WITHOUT_EVIDENCE: Readonly<Record<RowStatus, string>> = {
  supported:
    'Marked supported on a document attached by a reviewer rather than on a quote from your files.',
  partially_supported:
    'Nothing in your documents settles this one — it is yours to decide, with the eCertis note below as the starting point.',
  unsupported: 'Nothing in your documents supports this requirement.',
  not_applicable: 'This requirement does not apply to your company, so nothing was cited.',
}

/** The row that answers a requirement, keyed by requirement id — the matrix as a lookup. */
export function indexRowsByRequirement(
  rows: readonly MatrixRow[]
): ReadonlyMap<string, MatrixRow> {
  return new Map(rows.map((row) => [row.requirement_id, row]))
}

export function countByStatus(rows: readonly MatrixRow[]): ReadonlyMap<RowStatus, number> {
  const counts = new Map<RowStatus, number>()
  for (const row of rows) {
    counts.set(row.status, (counts.get(row.status) ?? 0) + 1)
  }
  return counts
}
