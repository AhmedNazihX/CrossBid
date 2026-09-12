'use client'

import { Eyebrow } from '@/components/ui/eyebrow'
import type { MatrixRow } from '@/lib/bids'
import type { Citation } from './citation'
import { EcertisCard } from './ecertis-card'
import { EvidenceList } from './evidence-list'
import { ROW_STATUS_WITHOUT_EVIDENCE } from './row-status'

export interface RowEvidenceProps {
  readonly row: MatrixRow
  readonly activeCitation: Citation | undefined
  readonly onCite: (citation: Citation) => void
  readonly isPhone?: boolean
  /** `false` where the caller already shows the sentence, as the phone card does. */
  readonly showRationale?: boolean
}

/**
 * The "Evidence in your profile" half of an expanded row in `Main.dc.html`, reused inside
 * the phone card of `WorkspacePhone.dc.html`: the agent's sentence for the reviewer, the
 * passages it cited — each one a link into the source panel — and the eCertis card naming
 * the national document for the bidder's country.
 *
 * Read-only in S4.5.1. Confirm / Change status / Add evidence are the artboard's next row of
 * controls and belong to S4.5.2; nothing here mutates anything.
 */
export function RowEvidence({
  row,
  activeCitation,
  onCite,
  isPhone = false,
  showRationale = true,
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
    </div>
  )
}
