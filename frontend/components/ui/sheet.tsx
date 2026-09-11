'use client'

import * as React from 'react'
import { cn } from 'cn'
import { Dialog as SheetPrimitive } from 'radix-ui'

import { Icon } from './icons'

/**
 * The phone navigation drawer: a Radix dialog on the canvas colour, sliding in from the
 * right under the `--overlay-scrim` (40 % ink), 280 ms `--ease-out` — the system's dialog
 * motion. Radix supplies the focus trap, Escape, and the labelled dialog role; the close
 * control is a 44 px target.
 */
export const Sheet = SheetPrimitive.Root
export const SheetTrigger = SheetPrimitive.Trigger
export const SheetClose = SheetPrimitive.Close

export function SheetContent({
  className,
  children,
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Content>) {
  return (
    <SheetPrimitive.Portal>
      <SheetPrimitive.Overlay className="fixed inset-0 z-50 bg-[var(--overlay-scrim)]" />
      <SheetPrimitive.Content
        className={cn(
          'fixed inset-y-0 right-0 z-50 flex w-[300px] max-w-[calc(100%-44px)] flex-col overflow-y-auto border-l border-border-default bg-surface-canvas shadow-lg',
          'motion-safe:transition-transform motion-safe:[transition-duration:var(--duration-slow)] motion-safe:[transition-timing-function:var(--ease-out)]',
          'data-[state=closed]:translate-x-full data-[state=open]:translate-x-0',
          className
        )}
        {...props}
      >
        {children}
        <SheetPrimitive.Close
          className="absolute top-1.5 right-3 inline-flex size-11 items-center justify-center rounded-md text-text-primary hover:bg-surface-hover"
          aria-label="Close navigation"
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
