'use client'

import { Eyebrow } from '@/components/ui/eyebrow'
import type { MatrixRow, Requirement } from '@/lib/bids'
import { formatLanguage } from '@/lib/format'
import type { Citation } from './citation'
import {
  CHECKABILITY_LABELS,
  describeThreshold,
  KIND_LABELS,
  STAGE_LABELS,
} from './requirement-labels'
import { RowEvidence } from './row-evidence'
import type { RowReview } from './row-review-controls'
import type { RowFeedbackController } from './use-row-feedback'

export interface RequirementDetailProps {
  readonly requirement: Requirement
  /** The matrix row answering this requirement, or `undefined` while the check is behind. */
  readonly row: MatrixRow | undefined
  readonly isChecking: boolean
  /** The bidder's thumbs on this bid (S4.6.3); shown under a row that has been checked. */
  readonly feedback: RowFeedbackController
  readonly activeCitation: Citation | undefined
  readonly onCite: (citation: Citation) => void
  /** Present once the bid is parked at its interrupt; absent keeps the panel read-only. */
  readonly review?: RowReview
}

/**
 * The expanded row of `Main.dc.html`: the tender's own words on the left with the typed
 * facts under them, and the check's answer on the right — the "Evidence in your profile"
 * block with its citations and the eCertis card.
 *
 * The right half is empty while the run has not reached this requirement, and says so: rows
 * arrive lane by lane, and a blank column would read as "nothing found" rather than "not
 * looked at yet".
 */
export function RequirementDetail({
  requirement,
  row,
  isChecking,
  feedback,
  activeCitation,
  onCite,
  review,
}: RequirementDetailProps) {
  return (
    <div className="grid gap-5 shell:grid-cols-2 shell:pl-[116px]">
      <div className="flex min-w-0 flex-col gap-4">
        <div>
          <Eyebrow className="mb-1.5">
            Source ({formatLanguage(requirement.source_lang)})
          </Eyebrow>
          <p className="m-0 mb-1.5 [font:var(--type-mono)] text-text-muted">
            {requirement.document_name}
            {/* A DUME row has no page; it cites the file and the criterion instead. */}
            {requirement.page === null || requirement.page === undefined
              ? ' · ESPD criterion'
              : ` p. ${requirement.page}`}
          </p>
          <blockquote
            lang={requirement.source_lang}
            className="m-0 text-base leading-[1.5] text-text-secondary italic"
          >
            &ldquo;{requirement.source_text}&rdquo;
          </blockquote>
        </div>
        <div>
          <Eyebrow className="mb-1.5">About this requirement</Eyebrow>
          <RequirementFacts requirement={requirement} hasEcertisCard={hasEcertisCard(row)} />
        </div>
      </div>
      {row === undefined ? (
        <div>
          <Eyebrow className="mb-1.5">Evidence in your profile</Eyebrow>
          <p className="m-0 text-base leading-[1.5] text-text-secondary">
            {isChecking
              ? 'The check has not reached this requirement yet. Its evidence appears here as soon as it does.'
              : 'This requirement was never checked, so there is no evidence to show.'}
          </p>
        </div>
      ) : (
        <RowEvidence
          row={row}
          feedback={feedback}
          activeCitation={activeCitation}
          onCite={onCite}
          review={review}
        />
      )}
    </div>
  )
}

function hasEcertisCard(row: MatrixRow | undefined): boolean {
  return row?.ecertis_evidence !== null && row?.ecertis_evidence !== undefined
}

/** The typed fields of the requirement as a definition list — never inferred, never prose. */
function RequirementFacts({
  requirement,
  hasEcertisCard: showsCard,
}: {
  readonly requirement: Requirement
  readonly hasEcertisCard: boolean
}) {
  const isMapped =
    requirement.ecertis_criterion_id !== null && requirement.ecertis_criterion_id !== undefined
  return (
    <dl className="m-0 grid grid-cols-[max-content_minmax(0,1fr)] gap-x-3 gap-y-1 text-base leading-[1.5]">
      <dt className="text-text-muted">Weight</dt>
      <dd className="m-0">{KIND_LABELS[requirement.kind]}</dd>
      <dt className="text-text-muted">Stage</dt>
      <dd className="m-0">{STAGE_LABELS[requirement.stage]}</dd>
      <dt className="text-text-muted">Evidence</dt>
      <dd className="m-0">{CHECKABILITY_LABELS[requirement.checkable]}</dd>
      {requirement.threshold !== null && requirement.threshold !== undefined && (
        <>
          <dt className="text-text-muted">Threshold</dt>
          <dd className="m-0">{describeThreshold(requirement.threshold)}</dd>
        </>
      )}
      {requirement.deadline !== null && requirement.deadline !== undefined && (
        <>
          <dt className="text-text-muted">Deadline</dt>
          <dd className="m-0">{requirement.deadline}</dd>
        </>
      )}
      {isMapped && !showsCard && (
        <>
          <dt className="text-text-muted">eCertis</dt>
          <dd className="m-0">
            Mapped to an ESPD criterion — the national evidence lands with the check
          </dd>
        </>
      )}
    </dl>
  )
}
