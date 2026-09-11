'use client'

import { useId, type ComponentProps } from 'react'
import { cn } from 'cn'

import { Field } from './field'
import { Icon } from './icons'

/**
 * Select — `components/forms/Select.jsx`: the 40 px bordered trigger with medium 14 px
 * text, `--shadow-xs` and the chevrons-up-down glyph, over the browser's own `<select>`
 * so that keyboard and screen-reader behaviour come for free. Options are the caller's.
 */
export interface SelectOption<V extends string> {
  readonly value: V
  readonly label: string
}

export interface SelectProps<V extends string> extends Omit<
  ComponentProps<'select'>,
  'value' | 'onChange' | 'children'
> {
  readonly label: string
  readonly hint?: string
  readonly error?: string
  readonly options: readonly SelectOption<V>[]
  readonly value: V
  readonly onValueChange: (value: V) => void
}

export function Select<V extends string>({
  label,
  hint,
  error,
  options,
  value,
  onValueChange,
  id,
  className,
  ...rest
}: SelectProps<V>) {
  const generatedId = useId()
  const selectId = id ?? generatedId
  const hintId = `${selectId}-hint`
  const values = new Set<string>(options.map((option) => option.value))
  return (
    <Field
      id={selectId}
      label={label}
      hint={hint}
      error={error}
      hintId={hintId}
      className={className}
    >
      <span className="relative flex">
        <select
          id={selectId}
          value={value}
          onChange={(event) => {
            if (values.has(event.target.value)) {
              onValueChange(event.target.value as V)
            }
          }}
          aria-invalid={error === undefined ? undefined : true}
          aria-describedby={hint !== undefined || error !== undefined ? hintId : undefined}
          className={cn(
            'h-10 w-full min-w-[120px] appearance-none rounded-md border bg-surface-card pr-9 pl-3 text-base font-medium leading-none text-text-primary shadow-xs',
            'focus-visible:border-border-focus disabled:cursor-not-allowed disabled:opacity-50',
            error === undefined ? 'border-border-default' : 'border-status-danger'
          )}
          {...rest}
        >
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <Icon
          name="chevronsUpDown"
          size={14}
          strokeWidth={2}
          className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-text-muted"
        />
      </span>
    </Field>
  )
}
