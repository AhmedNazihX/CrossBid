import { cn } from 'cn'

import type { MatrixRow, RowStatus } from '@/lib/bids'
import { countByStatus, ROW_STATUS_LABELS } from './row-status'

export interface MatrixSummaryProps {
  readonly rows: readonly MatrixRow[]
  readonly requirementCount: number
  /** `true` while the run is still checking, so the counts are a running total. */
  readonly isChecking: boolean
  readonly className?: string
}

const COUNT_CLASSES: Readonly<Record<RowStatus, string>> = {
  supported: 'text-text-primary',
  partially_supported: 'text-status-warning-text',
  unsupported: 'text-status-danger-text',
  not_applicable: 'text-text-muted',
}

/**
 * The one-line matrix tally of `WorkspacePhone.dc.html` ("24 / 31 supported · 3 unsupported ·
 * 4 partial"), used at both widths above the matrix.
 *
 * Rows arrive lane by lane while the status is `checking`, so the line leads with how many of
 * the requirements have been checked at all and says so in words — a tally that silently
 * counted 18 of 31 rows as the whole answer would read like a finished matrix.
 * `not_applicable` is listed only when some row carries it, so the common case stays short.
 */
export function MatrixSummary({
  rows,
  requirementCount,
  isChecking,
  className,
}: MatrixSummaryProps) {
  const counts = countByStatus(rows)
  const supported = counts.get('supported') ?? 0
  const listed: readonly RowStatus[] = [
    'partially_supported',
    'unsupported',
    ...((counts.get('not_applicable') ?? 0) > 0 ? (['not_applicable'] as const) : []),
  ]
  return (
    <p className={cn('m-0 text-[13px] leading-[1.5]', className)}>
      <b className="font-semibold">{supported}</b>
      <span className="text-text-muted">
        {' '}
        / {requirementCount} {ROW_STATUS_LABELS.supported.toLowerCase()}
      </span>
      {listed.map((status) => (
        <span key={status}>
          <span className="text-text-muted"> · </span>
          <span className={COUNT_CLASSES[status]}>
            {counts.get(status) ?? 0} {ROW_STATUS_LABELS[status].toLowerCase()}
          </span>
        </span>
      ))}
      {isChecking && (
        <span className="text-text-muted">
          {' '}
          · {rows.length} of {requirementCount} checked so far
        </span>
      )}
    </p>
  )
}
