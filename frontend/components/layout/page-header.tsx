import type * as React from 'react'
import { cn } from 'cn'

/**
 * `Shell.jsx`'s `PageHeader`: the page's one `h1` at 30 px semibold, -0.03em tracking, with
 * right-aligned actions (a status badge, the primary button) and, below, an optional
 * plain-English line saying what the page is for. Keeps the `h1` per page at exactly one.
 */
export interface PageHeaderProps {
  readonly title: React.ReactNode
  readonly description?: React.ReactNode
  readonly actions?: React.ReactNode
  readonly className?: string
}

export function PageHeader({ title, description, actions, className }: PageHeaderProps) {
  return (
    <div className={cn('mb-6 flex flex-col gap-2', className)}>
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="m-0 min-w-0 flex-1 text-[30px] font-semibold leading-[1.1] tracking-[-0.03em] [overflow-wrap:anywhere]">
          {title}
        </h1>
        {actions !== undefined && (
          <div className="flex flex-wrap items-center gap-3">{actions}</div>
        )}
      </div>
      {description !== undefined && (
        <p className="m-0 max-w-[720px] [font:var(--type-body)] text-text-secondary">
          {description}
        </p>
      )}
    </div>
  )
}
