import type * as React from 'react'
import { cn } from 'cn'

import { Icon } from './icons'

/**
 * Notice — the advisory box of `Verdict.dc.html`: 1 px border, 10 px radius, sunken
 * background, 13 px secondary text, a 16 px alert glyph. `tone="danger"` is the same box on
 * the danger tint for an error the bidder must act on, and announces itself.
 */
export interface NoticeProps extends React.ComponentProps<'div'> {
  readonly tone?: 'neutral' | 'danger'
  readonly title?: string
}

export function Notice({ tone = 'neutral', title, className, children, ...rest }: NoticeProps) {
  return (
    <div
      role={tone === 'danger' ? 'alert' : undefined}
      className={cn(
        'flex gap-2.5 rounded-[10px] border border-border-default px-3.5 py-3 text-[13px] leading-[1.5]',
        tone === 'danger'
          ? 'bg-status-danger-bg text-status-danger-text'
          : 'bg-surface-sunken text-text-secondary',
        className
      )}
      {...rest}
    >
      <Icon name="alert" size={16} className="mt-px" />
      <div className="min-w-0">
        {title !== undefined && <p className="m-0 font-medium">{title}</p>}
        {children}
      </div>
    </div>
  )
}
