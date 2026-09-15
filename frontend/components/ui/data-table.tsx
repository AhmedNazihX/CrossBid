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
 *
 * Headers do not wrap unless a column asks (`Th wrap`): most are one word over a column
 * sized for its cells, and a header that wrapped would be the tallest thing in the row for
 * nothing. See `ThProps.wrap` for the one case that needs the opt-out.
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

export interface ThProps extends React.ComponentProps<'th'> {
  /**
   * Lets the header text wrap onto a second line. The default is `nowrap`, and the one
   * header that needs the exception is the one longer than its column can ever be:
   * "Requirement (explained in DE)" sits over the column that takes whatever width the
   * fixed ones leave, and measured live at 1440 px that was 194 px of text in a 165 px cell,
   * drawn straight across "Source". A `className` cannot express this — `cn` does not merge
   * conflicting utilities, so `whitespace-normal` next to `whitespace-nowrap` is settled by
   * stylesheet order — hence a prop that leaves `nowrap` off rather than a class that fights
   * it. The 44 px height is a minimum in a table cell, so a wrapped header grows and the
   * single-line ones beside it stretch to match.
   */
  readonly wrap?: boolean
}

export function Th({ wrap = false, className, children, ...rest }: ThProps) {
  return (
    <th
      scope="col"
      className={cn(
        'h-11 border-b border-border-default bg-surface-sunken px-5 text-left text-[13px] font-medium text-text-secondary',
        wrap ? 'py-2.5 leading-[1.3]' : 'leading-none whitespace-nowrap',
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
