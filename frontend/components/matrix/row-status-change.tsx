import { cn } from 'cn'

import type { MatrixRow, RowStatus } from '@/lib/bids'
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
 * The Evidence cell of `Main.dc.html` while a row carries an unconfirmed change: the status
 * the reviewer chose, and under it, in muted text, the one the agent gave.
 *
 * Keeping the agent's word on screen is the story's first acceptance criterion, and it is
 * not decoration — the reviewer is overruling a cited finding, and the thing being overruled
 * has to stay readable until they press Confirm. Replacing the badge outright would make a
 * pending judgement look like the agent's own.
 */
export function RowStatusChange({
  row,
  pending,
  isConfirmed = false,
  className,
}: RowStatusChangeProps) {
  const isChanged = pending !== null && pending !== undefined && pending !== row.status
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
    </span>
  )
}
