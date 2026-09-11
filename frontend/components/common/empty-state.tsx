import Link from 'next/link'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Eyebrow } from '@/components/ui/eyebrow'

export interface EmptyStateAction {
  readonly href: string
  readonly label: string
}

export interface EmptyStateProps {
  /** What is absent, in the reader's words — not "no data". */
  readonly title: string
  /** Why it is absent and what happens once it is not. */
  readonly description: string
  /** The next step, in order. Rendered as an ordered list, so the order is real. */
  readonly steps?: readonly string[]
  /** The one thing to click to begin. */
  readonly action?: EmptyStateAction
  /** A lesser route out, e.g. back to the dashboard. */
  readonly secondaryAction?: EmptyStateAction
}

/**
 * The shell's empty state (story S4.1.2: "empty states explain the next step"), on the design
 * system's `Card`, `Eyebrow` and `Button` — the readme's rule that an empty state explains
 * why, then what to do.
 *
 * A screen with nothing on it is the first thing a new bidder sees, so it carries the
 * instructions rather than reporting an absence.
 */
export function EmptyState({
  title,
  description,
  steps,
  action,
  secondaryAction,
}: EmptyStateProps) {
  return (
    <Card title={title}>
      <p className="m-0 max-w-[720px] [font:var(--type-body)] text-text-secondary">
        {description}
      </p>

      {steps !== undefined && steps.length > 0 && (
        <div className="mt-4">
          <Eyebrow className="mb-2">What to do next</Eyebrow>
          <ol className="m-0 flex list-decimal flex-col gap-1.5 pl-5 text-text-secondary">
            {steps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
        </div>
      )}

      {(action !== undefined || secondaryAction !== undefined) && (
        <div className="mt-5 flex flex-wrap gap-2">
          {action !== undefined && (
            <Button asChild size="lg">
              <Link href={action.href}>{action.label}</Link>
            </Button>
          )}
          {secondaryAction !== undefined && (
            <Button asChild size="lg" variant="secondary">
              <Link href={secondaryAction.href}>{secondaryAction.label}</Link>
            </Button>
          )}
        </div>
      )}
    </Card>
  )
}
