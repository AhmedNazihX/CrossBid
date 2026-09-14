'use client'

import { Eyebrow } from '@/components/ui/eyebrow'
import type { MatrixRow } from '@/lib/bids'
import type { Citation } from './citation'
import { EcertisCard } from './ecertis-card'
import { EvidenceList } from './evidence-list'
import { RowReviewControls, type RowReview } from './row-review-controls'
import { ROW_STATUS_WITHOUT_EVIDENCE } from './row-status'

export interface RowEvidenceProps {
  readonly row: MatrixRow
  readonly activeCitation: Citation | undefined
  readonly onCite: (citation: Citation) => void
  readonly isPhone?: boolean
  /** `false` where the caller already shows the sentence, as the phone card does. */
  readonly showRationale?: boolean
  /**
   * The reviewer's pending edits and the documents they may attach. Omitted while the bid is
   * not parked at its interrupt, which is what makes the block read-only again.
   */
  readonly review?: RowReview
}

/**
 * The "Evidence in your profile" half of an expanded row in `Main.dc.html`, reused inside
 * the phone card of `WorkspacePhone.dc.html`: the agent's sentence for the reviewer, the
 * passages it cited — each one a link into the source panel — and the eCertis card naming
 * the national document for the bidder's country.
 *
 * S4.5.2 adds the artboard's Confirm / Change status / Add evidence controls under the card,
 * but only the pending-edit state changes when they are used: everything above them is the
 * agent's own answer, and stays exactly as the run left it until the review is submitted.
 */
export function RowEvidence({
  row,
  activeCitation,
  onCite,
  isPhone = false,
  showRationale = true,
  review,
}: RowEvidenceProps) {
  const hasEvidence = row.evidence.length > 0
  return (
    <div className="flex min-w-0 flex-col gap-2.5">
      <Eyebrow>Evidence in your profile</Eyebrow>
      {showRationale && (
        <p className="m-0 text-base leading-[1.5] text-text-primary">{row.agent_rationale}</p>
      )}
      {hasEvidence ? (
        <EvidenceList
          evidence={row.evidence}
          activeCitation={activeCitation}
          onCite={onCite}
          isPhone={isPhone}
        />
      ) : (
        <p className="m-0 text-base leading-[1.5] text-text-secondary">
          {ROW_STATUS_WITHOUT_EVIDENCE[row.status]}
        </p>
      )}
      {row.ecertis_evidence !== null && row.ecertis_evidence !== undefined && (
        <EcertisCard evidence={row.ecertis_evidence} />
      )}
      {review !== undefined && (
        <RowReviewControls
          row={row}
          edits={review.edits}
          attachable={review.attachable}
          isPhone={isPhone}
        />
      )}
    </div>
  )
}
