import type * as React from 'react'
import { cn } from 'cn'

/**
 * Tag — `components/core/Tag.jsx`: a bordered, sunken label for facts that are not statuses
 * (buyer, language pair, page count). `mono` sets the citation face for notice numbers and
 * requirement ids.
 */
export interface TagProps extends React.ComponentProps<'span'> {
  readonly mono?: boolean
}

export function Tag({ mono = false, className, children, ...rest }: TagProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-sm border border-border-default bg-surface-sunken px-2 py-1 text-text-secondary',
        mono ? '[font:var(--type-mono)]' : 'text-sm font-medium leading-[1.2]',
        className
      )}
      {...rest}
    >
      {children}
    </span>
  )
}
