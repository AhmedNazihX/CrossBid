'use client'

import { useId, type ComponentProps } from 'react'
import { cn } from 'cn'

import { Field } from './field'

/**
 * Input — `components/forms/Input.jsx`: a 40 px white box with a 1 px border and
 * `--shadow-xs`, 14 px text, 12 px hint; the border turns ink and the box gains the focus
 * ring while typing, red with `error`. The label is a real `<label>` and the hint or error
 * is wired through `aria-describedby`.
 *
 * `trailing` is this app's own, and the kit's `Input.d.ts` has no equivalent: it draws a
 * leading `icon` and nothing on the right. It exists for the sign-in form's show/hide
 * password control (L2, ADR-0095), which has to sit *inside* the box to read as part of the
 * field. Composing it outside would have meant a second copy of the box's border, height and
 * focus treatment, and two copies drift.
 */
export interface InputProps extends Omit<ComponentProps<'input'>, 'size'> {
  readonly label: string
  readonly hint?: string
  readonly error?: string
  readonly icon?: React.ReactNode
  /** A control drawn inside the box, after the text. Not in the kit; see the note above. */
  readonly trailing?: React.ReactNode
}

export function Input({
  label,
  hint,
  error,
  icon,
  trailing,
  id,
  className,
  ...rest
}: InputProps) {
  const generatedId = useId()
  const inputId = id ?? generatedId
  const hintId = `${inputId}-hint`
  const hasMessage = hint !== undefined || error !== undefined
  return (
    <Field
      id={inputId}
      label={label}
      hint={hint}
      error={error}
      hintId={hintId}
      className={className}
    >
      <span
        className={cn(
          'flex h-10 items-center gap-2 rounded-md border bg-surface-card px-3 shadow-xs transition-shadow [transition-duration:var(--duration-fast)]',
          'focus-within:border-border-focus focus-within:shadow-[var(--shadow-focus)] focus-within:focus-ring',
          error === undefined ? 'border-border-default' : 'border-status-danger',
          rest.disabled === true && 'opacity-50'
        )}
      >
        {icon !== undefined && (
          <span className="inline-flex size-4 text-text-muted [&_svg]:size-4">{icon}</span>
        )}
        <input
          id={inputId}
          aria-invalid={error === undefined ? undefined : true}
          aria-describedby={hasMessage ? hintId : undefined}
          className={cn(
            'w-0 min-w-0 flex-1 bg-transparent text-base leading-none text-text-primary outline-none placeholder:text-text-placeholder focus-visible:shadow-none',
            'file:mr-2 file:rounded-sm file:border-0 file:bg-surface-sunken file:px-2 file:py-1 file:text-sm file:font-medium file:text-text-secondary'
          )}
          {...rest}
        />
        {trailing}
      </span>
    </Field>
  )
}
