import type * as React from 'react'
import { cn } from 'cn'

/**
 * The marketing rhythm of `Sections.jsx` (`Wrap`, `Eyebrow`, `H2`, `Lead`), as used by every
 * section of `Landing.dc.html`: a centred 1160 px column with 24 px side padding; an orange
 * 12 px uppercase eyebrow with 0.08em tracking (the one orange per region); a 40 px semibold
 * title at -0.03em that scales down to 28 px on the phone; and a 17 px / 1.6 lead capped at
 * 560 px. The app's `Eyebrow` is the muted 0.06em label of the shell — a different thing.
 */
export function Wrap({ className, children, ...rest }: React.ComponentProps<'div'>) {
  return (
    <div
      className={cn('mx-auto w-full max-w-[var(--marketing-max)] px-6', className)}
      {...rest}
    >
      {children}
    </div>
  )
}

export function MarketingEyebrow({ className, children, ...rest }: React.ComponentProps<'p'>) {
  return (
    <p
      className={cn(
        'mb-3.5 text-sm font-medium uppercase leading-none tracking-[0.08em] text-text-accent',
        className
      )}
      {...rest}
    >
      {children}
    </p>
  )
}

export function SectionTitle({ className, children, ...rest }: React.ComponentProps<'h2'>) {
  return (
    <h2
      className={cn(
        'text-balance text-[length:clamp(28px,5vw,40px)] font-semibold leading-[1.1] tracking-[-0.03em]',
        className
      )}
      {...rest}
    >
      {children}
    </h2>
  )
}

export interface LeadProps extends React.ComponentProps<'p'> {
  readonly center?: boolean
}

export function Lead({ center = false, className, children, ...rest }: LeadProps) {
  return (
    <p
      className={cn(
        'mt-4 max-w-[560px] text-pretty text-lg leading-[1.6] text-text-secondary',
        center && 'mx-auto',
        className
      )}
      {...rest}
    >
      {children}
    </p>
  )
}
