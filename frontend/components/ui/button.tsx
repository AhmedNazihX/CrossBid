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
/** `circle` is the square-sided icon-only button — the Ask box's send control (ADR-0107). */
export type ButtonShape = 'default' | 'circle'

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

/**
 * The circular shape's sizes, which **replace** the ones above rather than being layered over
 * them. `cn` here is the `cn` package and not `tailwind-merge`, so a caller passing
 * `rounded-full size-9` through `className` would get `px-3` and `rounded-md` emitted as well
 * and leave the winner to stylesheet order — the same trap `SheetContent`'s `widthClass` was
 * given a prop for (ADR-0105).
 */
const CIRCLE_SIZE_CLASSES: Readonly<Record<ButtonSize, string>> = {
  sm: 'size-8',
  md: 'size-10',
  lg: 'size-12',
}

export interface ButtonProps extends React.ComponentProps<'button'> {
  readonly variant?: ButtonVariant
  readonly size?: ButtonSize
  /** `circle` drops the label padding for an icon-only control; give it an `aria-label`. */
  readonly shape?: ButtonShape
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
  shape = 'default',
  icon,
  iconRight,
  fullWidth = false,
  asChild = false,
  className,
  children,
  type,
  ...rest
}: ButtonProps) {
  const isCircle = shape === 'circle'
  const classes = cn(
    'inline-flex shrink-0 items-center justify-center border font-medium leading-none whitespace-nowrap',
    isCircle ? 'rounded-full' : 'rounded-md',
    'transition-colors [transition-duration:var(--duration-fast)] [transition-timing-function:var(--ease-standard)]',
    'disabled:cursor-not-allowed disabled:opacity-50 aria-disabled:cursor-not-allowed aria-disabled:opacity-50',
    VARIANT_CLASSES[variant],
    isCircle ? CIRCLE_SIZE_CLASSES[size] : SIZE_CLASSES[size],
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
