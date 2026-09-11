import { Fragment } from 'react'
import Link from 'next/link'
import { cn } from 'cn'

/**
 * The breadcrumb line above the page header in `Main.dc.html` and `NewBid.dc.html`:
 * 13 px muted, items separated by a slash, the current item last and unlinked; `mono`
 * sets the citation face for a notice number.
 */
export interface BreadcrumbItem {
  readonly label: string
  readonly href?: string
  readonly mono?: boolean
}

export function Breadcrumb({ items }: { readonly items: readonly BreadcrumbItem[] }) {
  return (
    <nav aria-label="Breadcrumb" className="mb-3">
      <ol className="m-0 flex list-none flex-wrap items-center gap-2 p-0 text-[13px] leading-none text-text-muted">
        {items.map((item, index) => {
          const isLast = index === items.length - 1
          return (
            <Fragment key={`${item.label}-${index}`}>
              {index > 0 && <li aria-hidden="true">/</li>}
              <li className={cn(item.mono === true && 'font-mono')}>
                {item.href !== undefined && !isLast ? (
                  <Link href={item.href} className="text-text-muted hover:text-text-primary">
                    {item.label}
                  </Link>
                ) : (
                  <span aria-current={isLast ? 'page' : undefined}>{item.label}</span>
                )}
              </li>
            </Fragment>
          )
        })}
      </ol>
    </nav>
  )
}
