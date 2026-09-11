import type * as React from 'react'
import { cn } from 'cn'

/**
 * The table shape of `Main.dc.html` and `Dashboard.dc.html` — a 1 px bordered, 12 px
 * rounded container; a 44 px sunken header row in 13 px medium secondary text; 14 px rows
 * separated by 1 px rules, no zebra; an optional 13 px muted footer line — over a semantic
 * `<table>`, so column headers are announced and rows are navigable. The container scrolls
 * sideways on a narrow screen so the page never does; it is positioned so that visually
 * hidden (`sr-only`, absolute) text inside a cell is clipped by it rather than widening the
 * page.
 */
export interface DataTableProps extends React.ComponentProps<'table'> {
  readonly caption?: React.ReactNode
  readonly footer?: React.ReactNode
  readonly containerClassName?: string
}

export function DataTable({
  caption,
  footer,
  containerClassName,
  className,
  children,
  ...rest
}: DataTableProps) {
  return (
    <div
      className={cn(
        'relative overflow-x-auto rounded-lg border border-border-default bg-surface-card',
        containerClassName
      )}
    >
      <table
        className={cn('w-full border-collapse text-base leading-[1.4]', className)}
        {...rest}
      >
        {caption !== undefined && <caption className="sr-only">{caption}</caption>}
        {children}
      </table>
      {footer !== undefined && (
        <div className="border-t border-border-default px-5 py-3 text-[13px] leading-none text-text-muted">
          {footer}
        </div>
      )}
    </div>
  )
}

export function Th({ className, children, ...rest }: React.ComponentProps<'th'>) {
  return (
    <th
      scope="col"
      className={cn(
        'h-11 border-b border-border-default bg-surface-sunken px-5 text-left text-[13px] font-medium leading-none text-text-secondary whitespace-nowrap',
        className
      )}
      {...rest}
    >
      {children}
    </th>
  )
}

export function Tr({ className, children, ...rest }: React.ComponentProps<'tr'>) {
  return (
    <tr className={cn('border-b border-border-default last:border-b-0', className)} {...rest}>
      {children}
    </tr>
  )
}

export function Td({ className, children, ...rest }: React.ComponentProps<'td'>) {
  return (
    <td className={cn('px-5 py-3.5 align-middle', className)} {...rest}>
      {children}
    </td>
  )
}
