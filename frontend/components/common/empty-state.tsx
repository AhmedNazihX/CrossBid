import Link from 'next/link'

import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'

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
 * The shell's empty state (story S4.1.2: "empty states explain the next step").
 *
 * A screen with nothing on it is the first thing a new bidder sees, so it has to
 * carry the instructions rather than report an absence. Stock shadcn/ui `Card`
 * and `Button` only — no bespoke visual language, which stays gated behind
 * S4.0.1's design confirmation.
 */
export function EmptyState({
  title,
  description,
  steps,
  action,
  secondaryAction,
}: EmptyStateProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          {/* A real heading, so heading-by-heading navigation reaches it: stock
              `CardTitle` renders a `div`, and Tailwind's preflight strips the
              `h2` defaults, so this changes semantics only. */}
          <h2>{title}</h2>
        </CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>

      {steps !== undefined && steps.length > 0 && (
        <CardContent>
          <p className="text-muted-foreground mb-2 text-xs font-medium uppercase">
            What to do next
          </p>
          <ol className="text-muted-foreground list-decimal space-y-1.5 pl-5">
            {steps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
        </CardContent>
      )}

      {(action !== undefined || secondaryAction !== undefined) && (
        <CardFooter className="flex-wrap gap-2">
          {action !== undefined && (
            <Button asChild size="lg">
              <Link href={action.href}>{action.label}</Link>
            </Button>
          )}
          {secondaryAction !== undefined && (
            <Button asChild size="lg" variant="outline">
              <Link href={secondaryAction.href}>{secondaryAction.label}</Link>
            </Button>
          )}
        </CardFooter>
      )}
    </Card>
  )
}
