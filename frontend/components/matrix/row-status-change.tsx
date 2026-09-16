import { cn } from 'cn'

import type { MatrixRow, ReviewerStatus, RowStatus } from '@/lib/bids'
import { formatDateTime } from '@/lib/format'
import { ROW_STATUS_LABELS } from './row-status'
import { RowStatusBadge } from './row-status-badge'

export interface RowStatusChangeProps {
  readonly row: MatrixRow
  /** The reviewer's pending status, or `undefined` while the agent's still stands. */
  readonly pending: RowStatus | null | undefined
  /** The reviewer has settled this row as the agent left it — progress, not a change. */
  readonly isConfirmed?: boolean
  readonly className?: string
}

/**
 * What the reviewer did with a row, in their own words: the two dispositions a submitted
 * review can leave (`ReviewerStatus` minus `pending`, which is "nothing yet").
 */
const REVIEWER_STATUS_LABELS: Readonly<Record<Exclude<ReviewerStatus, 'pending'>, string>> = {
  confirmed: 'Confirmed by you',
  overridden: 'Overridden by you',
}

/**
 * The Evidence cell of `Main.dc.html`: the row's status badge, and under it, in muted text,
 * whatever the reviewer has done to it — pending or submitted.
 *
 * **While the bid is parked**, a row may carry an unconfirmed change: the status the
 * reviewer chose, and under it the one the agent gave. Keeping the agent's word on screen is
 * the story's first acceptance criterion, and it is not decoration — the reviewer is
 * overruling a cited finding, and the thing being overruled has to stay readable until they
 * press Confirm. Replacing the badge outright would make a pending judgement look like the
 * agent's own.
 *
 * **Once the review is submitted**, the row carries `reviewer_status`, `override_reason`
 * and `reviewed_at`, and this cell shows them — otherwise a finished bid would look exactly
 * as the agent left it, with no trace of which rows the reviewer overrode or why, which
 * undercuts S4.5.3's promise that the final state is the one shown. The line names the
 * disposition and the time; an override's reason follows on its own line, whole, because a
 * reviewer reading their own audit trail should not have to open the row to find it.
 *
 * **An override also names what it overruled, when the record has it.** The review node
 * (`agent/nodes/review.py::_reviewed`) writes the reviewer's status *into* `status` — the
 * scorer re-runs on that field — so the badge shows the reviewer's verdict, and the agent's
 * own survives only in `agent_status`, written once by the check loop and never rewritten by
 * a review. Where it is present and differs from `status`, the disposition line continues
 * "· agent said …" in the pending branch's own words, so a submitted override reads as the
 * settled form of a pending one rather than as a second vocabulary. Where it is `null` the
 * line stops at the time: rows written before migration 0009 never recorded it, and for an
 * already-overridden row copying `status` into it would have asserted the agent agreed when
 * the record says the opposite. Null means "not recorded", and the cell says nothing rather
 * than guess — which is the state every row of a bid finished before that migration is in.
 *
 * The three states are exclusive in practice — `pending` and `isConfirmed` come from the
 * review controls, which the workspace only mounts while the bid is `awaiting_review`, when
 * every row is still `reviewer_status: pending` — and exclusive in code regardless: a local
 * edit always wins over the stored disposition, so the screen never shows both.
 */
export function RowStatusChange({
  row,
  pending,
  isConfirmed = false,
  className,
}: RowStatusChangeProps) {
  const isChanged = pending !== null && pending !== undefined && pending !== row.status
  const hasLocalEdit = isChanged || isConfirmed
  const reviewed =
    hasLocalEdit || row.reviewer_status === 'pending' ? undefined : row.reviewer_status
  const reason = (row.override_reason ?? '').trim()
  const overruledFrom =
    reviewed === 'overridden' &&
    row.agent_status !== null &&
    row.agent_status !== undefined &&
    row.agent_status !== row.status
      ? row.agent_status
      : undefined
  return (
    <span className={cn('flex flex-col items-start gap-1', className)}>
      <RowStatusBadge status={isChanged ? pending : row.status} />
      {isChanged && (
        <span className="[font:var(--type-body-sm)] text-text-muted">
          Your change · agent said {ROW_STATUS_LABELS[row.status].toLowerCase()}
        </span>
      )}
      {!isChanged && isConfirmed && (
        <span className="[font:var(--type-body-sm)] text-text-muted">Confirmed by you</span>
      )}
      {reviewed !== undefined && (
        <span className="[font:var(--type-body-sm)] text-text-muted">
          {REVIEWER_STATUS_LABELS[reviewed]}
          {row.reviewed_at !== null && row.reviewed_at !== undefined && (
            <> · {formatDateTime(row.reviewed_at)}</>
          )}
          {overruledFrom !== undefined && (
            <> · agent said {ROW_STATUS_LABELS[overruledFrom].toLowerCase()}</>
          )}
        </span>
      )}
      {reviewed !== undefined && reason !== '' && (
        <span className="[font:var(--type-body-sm)] text-text-secondary whitespace-pre-line [overflow-wrap:anywhere]">
          <span className="font-medium text-text-primary">Your reason:</span> {reason}
        </span>
      )}
    </span>
  )
}
