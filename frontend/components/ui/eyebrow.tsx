import type * as React from 'react'
import { cn } from 'cn'

/**
 * Eyebrow — the small caps label of the shell and the matrix (`Shell.jsx`'s `Eye`, the
 * "Source (FR)" heading of an expanded row): 12 px medium, 0.06em tracking, muted,
 * uppercase — the one place ALL-CAPS is allowed.
 */
export function Eyebrow({ className, children, ...rest }: React.ComponentProps<'div'>) {
  return (
    <div
      className={cn(
        'text-sm font-medium uppercase leading-none tracking-wide text-text-muted',
        className
      )}
      {...rest}
    >
      {children}
    </div>
  )
}
