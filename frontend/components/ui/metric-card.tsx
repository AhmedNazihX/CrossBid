import { cn } from 'cn'

/**
 * MetricCard — `components/app/MetricCard.jsx`: 14 px secondary label, 32 px semibold value
 * with tight tracking, and a 12 px footer of a coloured delta plus a muted period. The delta
 * takes a status text colour only — success, danger or muted.
 */
export interface MetricCardProps {
  readonly label: string
  readonly value: string | number
  readonly delta?: string
  readonly deltaTone?: 'success' | 'danger' | 'neutral'
  readonly period?: string
  readonly className?: string
}

const DELTA_CLASSES: Readonly<Record<NonNullable<MetricCardProps['deltaTone']>, string>> = {
  success: 'text-status-success-text',
  danger: 'text-status-danger-text',
  neutral: 'text-text-muted',
}

export function MetricCard({
  label,
  value,
  delta,
  deltaTone = 'success',
  period,
  className,
}: MetricCardProps) {
  return (
    <div
      className={cn(
        'rounded-lg border border-border-default bg-surface-card p-6 shadow-xs',
        className
      )}
    >
      <div className="[font:var(--type-body)] text-text-secondary">{label}</div>
      <div className="mt-2 text-3xl font-semibold leading-[1.1] tracking-tight">{value}</div>
      {(delta !== undefined || period !== undefined) && (
        <div className="mt-2.5 flex gap-2 [font:var(--type-body-sm)]">
          {delta !== undefined && (
            <span className={cn('font-medium', DELTA_CLASSES[deltaTone])}>{delta}</span>
          )}
          {period !== undefined && <span className="text-text-muted">{period}</span>}
        </div>
      )}
    </div>
  )
}
