import type * as React from 'react'
import { cn } from 'cn'

/**
 * Badge — `components/core/Badge.jsx`: a status chip with a 7 px dot, 11/12 px medium text,
 * the tone's 50-tint background and 700 text. Pill by default; `pill={false}` gives the
 * 6 px radius the dashboard's phase column uses. Tones are the status pairs only — orange
 * is never a status colour, and the verdict words live in `VerdictChip`.
 */
export type BadgeTone = 'success' | 'warning' | 'danger' | 'info' | 'neutral' | 'brand'
export type BadgeSize = 'sm' | 'md'

const TONE_CLASSES: Readonly<Record<BadgeTone, { chip: string; dot: string }>> = {
  success: { chip: 'bg-status-success-bg text-status-success-text', dot: 'bg-status-success' },
  warning: { chip: 'bg-status-warning-bg text-status-warning-text', dot: 'bg-status-warning' },
  danger: { chip: 'bg-status-danger-bg text-status-danger-text', dot: 'bg-status-danger' },
  info: { chip: 'bg-status-info-bg text-status-info-text', dot: 'bg-status-info' },
  neutral: { chip: 'bg-status-neutral-bg text-status-neutral-text', dot: 'bg-status-neutral' },
  brand: { chip: 'bg-stone-50 text-stone-700', dot: 'bg-blue-500' },
}

export interface BadgeProps extends React.ComponentProps<'span'> {
  readonly tone?: BadgeTone
  readonly size?: BadgeSize
  readonly dot?: boolean
  readonly pill?: boolean
}

export function Badge({
  tone = 'neutral',
  size = 'md',
  dot = true,
  pill = true,
  className,
  children,
  ...rest
}: BadgeProps) {
  const classes = TONE_CLASSES[tone]
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 font-medium leading-[1.2] whitespace-nowrap',
        size === 'sm' ? 'px-2 py-[3px] text-xs' : 'px-2.5 py-[5px] text-sm',
        pill ? 'rounded-[var(--radius-pill)]' : 'rounded-sm',
        classes.chip,
        className
      )}
      {...rest}
    >
      {dot && (
        <span
          aria-hidden="true"
          className={cn('size-[7px] shrink-0 rounded-full', classes.dot)}
        />
      )}
      {children}
    </span>
  )
}
