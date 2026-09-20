'use client'

import * as React from 'react'
import { cn } from 'cn'
import * as SheetPrimitive from '@radix-ui/react-dialog'

import { Icon } from './icons'

/**
 * A Radix dialog on the canvas colour, sliding in from the right under the
 * `--overlay-scrim` (40 % ink), 280 ms `--ease-out` — the system's dialog motion. Radix
 * supplies the focus trap, Escape, and the labelled dialog role; the close control is a
 * 44 px target.
 *
 * Two callers, two widths: the phone navigation drawer (280–300 px, the default) and the
 * workspace's source drawer, which frames a PDF and needs most of the window (ADR-0104).
 * The width and the close label are **props rather than something a caller overrides through
 * `className`**, because `cn` here is the `cn` package and not `tailwind-merge`: a second
 * width utility is appended, not substituted, and which of the two wins is left to stylesheet
 * order. Parameterising is the only way to say it once and mean it.
 */
export const Sheet = SheetPrimitive.Root
export const SheetTrigger = SheetPrimitive.Trigger
export const SheetClose = SheetPrimitive.Close

export interface SheetContentProps extends React.ComponentProps<typeof SheetPrimitive.Content> {
  /** The drawer's width, as one Tailwind utility. Defaults to the navigation drawer's 300 px. */
  readonly widthClass?: string
  /** The accessible name of the close control. */
  readonly closeLabel?: string
}

export function SheetContent({
  className,
  widthClass = 'w-[300px]',
  closeLabel = 'Close navigation',
  children,
  ...props
}: SheetContentProps) {
  return (
    <SheetPrimitive.Portal>
      <SheetPrimitive.Overlay className="fixed inset-0 z-50 bg-[var(--overlay-scrim)]" />
      <SheetPrimitive.Content
        className={cn(
          'fixed inset-y-0 right-0 z-50 flex max-w-[calc(100%-44px)] flex-col overflow-y-auto border-l border-border-default bg-surface-canvas shadow-lg',
          widthClass,
          'motion-safe:transition-transform motion-safe:[transition-duration:var(--duration-slow)] motion-safe:[transition-timing-function:var(--ease-out)]',
          'data-[state=closed]:translate-x-full data-[state=open]:translate-x-0',
          className
        )}
        {...props}
      >
        {children}
        <SheetPrimitive.Close
          className="absolute top-1.5 right-3 inline-flex size-11 items-center justify-center rounded-md text-text-primary hover:bg-surface-hover"
          aria-label={closeLabel}
        >
          <Icon name="x" size={20} />
        </SheetPrimitive.Close>
      </SheetPrimitive.Content>
    </SheetPrimitive.Portal>
  )
}

export function SheetTitle({
  className,
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Title>) {
  return (
    <SheetPrimitive.Title
      className={cn('m-0 text-lg font-semibold leading-[1.25] tracking-tight', className)}
      {...props}
    />
  )
}

export function SheetDescription({
  className,
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Description>) {
  return (
    <SheetPrimitive.Description
      className={cn('m-0 [font:var(--type-body-sm)] text-text-muted', className)}
      {...props}
    />
  )
}
