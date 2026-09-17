import * as React from 'react'
import { cn } from 'cn'
import * as Slot from '@radix-ui/react-slot'

/**
 * Button — `components/core/Button.jsx`: five variants, three heights (32/40/48 px),
 * 8 px radius, medium weight, 16 px icon slots, 50 % opacity when disabled. Hover darkens
 * one step; the focus ring is the sheet's own, drawn by `:focus-visible` in `globals.css` and
 * inherited rather than declared here (ADR-0092). `asChild` lets a Next `Link`
 * carry the styling, so a navigation action is still an anchor.
 */
export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'inverse' | 'danger'
export type ButtonSize = 'sm' | 'md' | 'lg'

const VARIANT_CLASSES: Readonly<Record<ButtonVariant, string>> = {
  primary:
    'border-transparent bg-surface-brand text-text-inverse not-disabled:hover:bg-blue-600',
  secondary:
    'border-border-default bg-surface-card text-text-primary shadow-xs not-disabled:hover:bg-surface-hover',
  ghost:
    'border-transparent bg-transparent text-text-primary not-disabled:hover:bg-surface-hover',
  inverse:
    'border-transparent bg-surface-inverse text-text-inverse not-disabled:hover:bg-stone-800',
  danger:
    'border-transparent bg-status-danger text-text-inverse not-disabled:hover:bg-status-danger-text',
}

const SIZE_CLASSES: Readonly<Record<ButtonSize, string>> = {
  sm: 'h-8 gap-1.5 px-3 text-[13px]',
  md: 'h-10 gap-2 px-4 text-base',
  lg: 'h-12 gap-2 px-5 text-[length:var(--text-md)]',
}

export interface ButtonProps extends React.ComponentProps<'button'> {
  readonly variant?: ButtonVariant
  readonly size?: ButtonSize
  /** 16 px glyph before the label. */
  readonly icon?: React.ReactNode
  /** 16 px glyph after the label. */
  readonly iconRight?: React.ReactNode
  readonly fullWidth?: boolean
  /** Render the child element (e.g. a `Link`) with the button's classes instead of a `<button>`. */
  readonly asChild?: boolean
}

export function Button({
  variant = 'primary',
  size = 'md',
  icon,
  iconRight,
  fullWidth = false,
  asChild = false,
  className,
  children,
  type,
  ...rest
}: ButtonProps) {
  const classes = cn(
    'inline-flex shrink-0 items-center justify-center rounded-md border font-medium leading-none whitespace-nowrap',
    'transition-colors [transition-duration:var(--duration-fast)] [transition-timing-function:var(--ease-standard)]',
    'disabled:cursor-not-allowed disabled:opacity-50 aria-disabled:cursor-not-allowed aria-disabled:opacity-50',
    VARIANT_CLASSES[variant],
    SIZE_CLASSES[size],
    fullWidth && 'flex w-full',
    className
  )

  if (asChild) {
    return (
      <Slot.Root className={classes} {...rest}>
        {children}
      </Slot.Root>
    )
  }

  return (
    <button type={type ?? 'button'} className={classes} {...rest}>
      {icon !== undefined && <IconSlot>{icon}</IconSlot>}
      {children}
      {iconRight !== undefined && <IconSlot>{iconRight}</IconSlot>}
    </button>
  )
}

function IconSlot({ children }: { readonly children: React.ReactNode }) {
  return <span className="inline-flex size-4 [&_svg]:size-4">{children}</span>
}
