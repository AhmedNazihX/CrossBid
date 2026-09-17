import type { ComponentProps, ReactNode } from 'react'
import { cn } from 'cn'

/**
 * Checkbox — `components/forms/Checkbox.jsx`: an 18 px box with a 4 px radius, ink fill and
 * a white 3-stroke check when on; medium label with an optional muted description. The
 * native input stays in the tree (visually hidden) so the box is a real, focusable control.
 */
export interface CheckboxProps extends Omit<ComponentProps<'input'>, 'type'> {
  readonly label: ReactNode
  readonly description?: ReactNode
}

export function Checkbox({ label, description, className, ...rest }: CheckboxProps) {
  return (
    <label
      className={cn(
        'flex cursor-pointer items-start gap-2.5 [font:var(--type-body)] has-[input:disabled]:cursor-not-allowed has-[input:disabled]:opacity-50',
        className
      )}
    >
      <input type="checkbox" className="peer sr-only" {...rest} />
      <span
        aria-hidden="true"
        className={cn(
          'mt-px inline-flex size-[18px] shrink-0 items-center justify-center rounded-xs border border-border-strong bg-surface-card transition-colors [transition-duration:var(--duration-fast)]',
          'peer-checked:border-blue-500 peer-checked:bg-blue-500 peer-focus-visible:shadow-[var(--shadow-focus)] peer-focus-visible:focus-ring peer-checked:[&>svg]:opacity-100'
        )}
      >
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="#fff"
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="opacity-0"
        >
          <path d="M20 6 9 17l-5-5" />
        </svg>
      </span>
      <span className="min-w-0">
        <span className="block leading-5 font-medium [overflow-wrap:anywhere]">{label}</span>
        {description !== undefined && (
          <span className="block [font:var(--type-body-sm)] text-text-muted [overflow-wrap:anywhere]">
            {description}
          </span>
        )}
      </span>
    </label>
  )
}
