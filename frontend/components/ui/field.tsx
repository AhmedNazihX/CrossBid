import type * as React from 'react'
import { cn } from 'cn'

/**
 * The label / control / hint column that `Input.jsx` and `Select.jsx` share: 6 px gap,
 * 13 px medium label, 12 px hint in muted or danger text. Shared here so that a form control
 * never invents its own spacing. `hintId` is what the control lists in `aria-describedby`.
 */
export interface FieldProps {
  readonly id: string
  readonly label: string
  readonly hint?: string
  readonly error?: string
  readonly hintId: string
  readonly className?: string
  readonly children: React.ReactNode
}

export function Field({ id, label, hint, error, hintId, className, children }: FieldProps) {
  const message = error ?? hint
  return (
    <div className={cn('flex min-w-0 flex-col gap-1.5 [font:var(--type-body)]', className)}>
      <label htmlFor={id} className="text-[13px] font-medium leading-none text-text-primary">
        {label}
      </label>
      {children}
      {message !== undefined && (
        <p
          id={hintId}
          className={cn(
            'm-0 [font:var(--type-body-sm)]',
            error === undefined ? 'text-text-muted' : 'text-status-danger-text'
          )}
        >
          {message}
        </p>
      )}
    </div>
  )
}
