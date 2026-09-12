import { Badge, type BadgeSize } from '@/components/ui/badge'
import type { RowStatus } from '@/lib/bids'
import { ROW_STATUS_LABELS, ROW_STATUS_TONES } from './row-status'

export interface RowStatusBadgeProps {
  readonly status: RowStatus
  readonly size?: BadgeSize
  readonly className?: string
}

/**
 * The status chip of the Evidence column in `Main.dc.html` and of the card header in
 * `WorkspacePhone.dc.html`: the design system's `Badge` carrying one of the four row words.
 * The word is always rendered beside the dot, so the status never rests on colour alone.
 */
export function RowStatusBadge({ status, size = 'sm', className }: RowStatusBadgeProps) {
  return (
    <Badge tone={ROW_STATUS_TONES[status]} size={size} className={className}>
      {ROW_STATUS_LABELS[status]}
    </Badge>
  )
}
