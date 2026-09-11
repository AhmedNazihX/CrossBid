import type * as React from 'react'
import { cn } from 'cn'

/**
 * Card — `components/core/Card.jsx`: white, 1 px border, 12 px radius, `--shadow-xs`,
 * 24 px padding (20 px for the source panel), and an optional header row of a 20 px icon,
 * a 17 px semibold title and right-aligned actions. The title is a real heading so that
 * heading navigation reaches every card; pick the level with `headingLevel`.
 */
export interface CardProps extends Omit<React.ComponentProps<'section'>, 'title'> {
  readonly title?: React.ReactNode
  readonly headingLevel?: 'h2' | 'h3'
  readonly icon?: React.ReactNode
  readonly actions?: React.ReactNode
  readonly padding?: 24 | 20 | 16
}

const PADDING_CLASSES: Readonly<Record<NonNullable<CardProps['padding']>, string>> = {
  24: 'p-6',
  20: 'p-5',
  16: 'p-4',
}

export function Card({
  title,
  headingLevel: Heading = 'h2',
  icon,
  actions,
  padding = 24,
  className,
  children,
  ...rest
}: CardProps) {
  const hasHeader = title !== undefined || actions !== undefined
  return (
    <section
      className={cn(
        'rounded-lg border border-border-default bg-surface-card shadow-xs',
        PADDING_CLASSES[padding],
        className
      )}
      {...rest}
    >
      {hasHeader && (
        <div className={cn('flex items-center gap-2.5', children !== undefined && 'mb-4')}>
          {icon !== undefined && (
            <span className="inline-flex size-5 text-text-primary [&_svg]:size-5">{icon}</span>
          )}
          {title !== undefined && (
            <Heading className="m-0 flex-1 [font:var(--type-h4)] tracking-tight">
              {title}
            </Heading>
          )}
          {actions !== undefined && <div className="flex items-center gap-2">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  )
}
