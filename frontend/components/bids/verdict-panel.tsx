'use client'

import { useCallback, useMemo, useState } from 'react'
import { cn } from 'cn'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Icon } from '@/components/ui/icons'
import { Notice } from '@/components/ui/notice'
import { Tag } from '@/components/ui/tag'
import { VerdictChip } from '@/components/ui/verdict-chip'
import {
  isAwaitingReview,
  type BidResponse,
  type Decision,
  type RowEdit,
  type Verdict,
} from '@/lib/bids'
import { formatDateTime, plural } from '@/lib/format'
import { BID_STATUS_LABELS } from './bid-status'
import { useReviewSubmission, type ReviewState } from './use-review-submission'
import { VerdictDecisionForm } from './verdict-decision-form'
import { requirementLabels, VerdictGaps } from './verdict-gaps'
import { NOT_AWAITING_REVIEW } from './verdict-decisions'

/**
 * The review screen of `Verdict.dc.html` (story S4.5.3): what CrossBid recommends, what
 * would change it, and the decision that ends the run.
 *
 * This is the product's safety boundary made visible — the agent has stopped at its
 * interrupt and nothing proceeds until a person acts. So the panel is built around one
 * guarantee: the review is submitted once. Everything after that call is a reported outcome
 * rather than a form to try again, including the 409 that says somebody else got here
 * first — the honest answer to which is the bid's current state, not a retry that would
 * produce the same 409.
 *
 * The advisory verdict lives on the left with the gaps behind it, so the decision on the
 * right is never made against a bare chip.
 *
 * **The two columns are decided by the panel's own width, not the viewport's.** The artboard
 * draws `minmax(0, 1.4fr) minmax(0, 1fr)` on a full-width screen, and the first build wrote
 * that as `xl:grid-cols-…`. Then ADR-0060 moved the panel into the workspace's 400 px side
 * column, where `xl:` is *on* at a 1440 px viewport: measured live, two columns of 213 px and
 * 152 px inside a 385 px tab, "Pflichtanforderungen" broken mid-word, one word per line in
 * the decision card, and 450 px of content in a 385 px box, so the sticky column grew a
 * horizontal scrollbar. So the wrapper is a `@container` and the grid goes two-up at
 * `@3xl` (768 px of *panel*), which Tailwind 4 resolves natively. It stacks in the tab and
 * on the phone, and still splits as the artboard draws it wherever the panel is genuinely
 * wide — below `xl` the workspace renders it first and full-width, for one.
 */
export interface VerdictPanelProps {
  /** The bid as the workspace last polled it. `bid.verdict` is the agent's advisory verdict. */
  readonly bid: BidResponse
  /** The matrix's unsent edits, sent with the review in the same call. */
  readonly rowEdits: readonly RowEdit[]
  /**
   * How many of those edits the server would refuse, from the matrix's own mirrored rules.
   * The form blocks on it: without this the reviewer presses Confirm, the server answers
   * 422 naming a `matrix_row_id`, and they are shown an id they have never seen — which is
   * precisely what mirroring the rules in the matrix was for.
   */
  readonly blockedRowCount?: number
  /**
   * The bid as the server now has it: after a review lands, and after a 409 when the panel
   * re-reads the bid to show what is true. In both cases it supersedes the `bid` prop.
   */
  readonly onReviewed: (bid: BidResponse) => void
  /** Renders "Back to matrix" when given; the caller decides what that means. */
  readonly onBackToMatrix?: () => void
  readonly className?: string
}

export function VerdictPanel({
  bid,
  rowEdits,
  blockedRowCount = 0,
  onReviewed,
  onBackToMatrix,
  className,
}: VerdictPanelProps) {
  const { state, isLocked, submit } = useReviewSubmission(bid.id, onReviewed)
  const [submittedDecision, setSubmittedDecision] = useState<Decision | undefined>(undefined)
  const labels = useMemo(() => requirementLabels(bid.requirements), [bid.requirements])

  const handleSubmit = useCallback(
    (decision: Decision, overrideReason: string | undefined) => {
      setSubmittedDecision(decision)
      void submit({
        decision,
        override_reason: overrideReason ?? null,
        row_edits: [...rowEdits],
      })
    },
    [rowEdits, submit]
  )

  // Once the server has spoken its row is the truth, even when the answer was a refusal.
  const settledBid =
    state.phase === 'reviewed' || state.phase === 'conflict' ? state.bid : undefined
  const current = settledBid ?? bid
  const verdict = current.verdict ?? undefined

  return (
    <div className={cn('@container', className)}>
      <div className="grid items-start gap-5 @3xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        {/* Rendered from the first paint, empty, so that a screen reader is listening before
          the decision leaves the screen — a live region added with its text is not read. */}
        <p role="status" aria-live="polite" className="sr-only">
          {announce(state.phase)}
        </p>
        <div className="flex min-w-0 flex-col gap-5">
          <RecommendationCard bid={current} verdict={verdict} />
          {verdict !== undefined && <VerdictGaps gaps={verdict.gaps} labels={labels} />}
        </div>
        <div className="flex min-w-0 flex-col gap-5">
          {state.phase === 'reviewed' && (
            <RecordedCard
              bid={state.bid}
              decision={submittedDecision}
              onBackToMatrix={onBackToMatrix}
            />
          )}
          {state.phase === 'conflict' && (
            <ConflictCard bid={state.bid} onBackToMatrix={onBackToMatrix} />
          )}
          {(state.phase === 'editing' || state.phase === 'submitting') &&
            (isAwaitingReview(bid) ? (
              <VerdictDecisionForm
                agentDecision={verdict?.decision}
                isLocked={isLocked}
                isSubmitting={state.phase === 'submitting'}
                submitError={state.phase === 'editing' ? state.error : undefined}
                blockedRowCount={blockedRowCount}
                onSubmit={handleSubmit}
                onBackToMatrix={onBackToMatrix}
              />
            ) : (
              <NotParkedCard bid={bid} onBackToMatrix={onBackToMatrix} />
            ))}
        </div>
      </div>
    </div>
  )
}

/** One sentence for the live region, for the two moments the screen changes under the reader. */
function announce(phase: ReviewState['phase']): string {
  if (phase === 'submitting') {
    return 'Submitting your review…'
  }
  if (phase === 'reviewed') {
    return 'Your review was submitted. This bid has left the review interrupt.'
  }
  if (phase === 'conflict') {
    return NOT_AWAITING_REVIEW
  }
  return ''
}

/**
 * The agent's advisory verdict: the chip, the count behind it, and its reasoning. The chip
 * says so — `advisory` — because after a review this card stays on screen beside the
 * recorded decision, and two bare chips that may disagree would leave the reader to guess
 * which one a person actually chose.
 */
function RecommendationCard({
  bid,
  verdict,
}: {
  readonly bid: BidResponse
  readonly verdict: Verdict | undefined
}) {
  const stamp = formatDateTime(bid.updated_at ?? bid.created_at)
  return (
    <Card
      title="CrossBid recommends"
      icon={<Icon name="spark" size={20} />}
      actions={stamp === '—' ? undefined : <Tag mono>{stamp}</Tag>}
    >
      {verdict === undefined ? (
        <p className="m-0 text-text-secondary">
          The agent has not scored this bid, so there is no recommendation to confirm. Any
          decision you record below is your own.
        </p>
      ) : (
        <>
          <div className="mb-3.5 flex flex-wrap items-center gap-3.5">
            <VerdictChip verdict={verdict.decision} size="lg" advisory />
            <span className="[font:var(--type-body)] text-text-secondary">
              {countSentence(verdict)}
            </span>
          </div>
          <p className="m-0 [font:var(--type-body-lg)] [overflow-wrap:anywhere]">
            {verdict.rationale}
          </p>
        </>
      )}
      <Notice className="mt-4">
        Advisory only. CrossBid never submits and never asserts compliance without a source.
        This verdict does not move forward until you confirm it.
      </Notice>
    </Card>
  )
}

function countSentence(verdict: Verdict): string {
  const supported = `${verdict.mandatory_supported} of ${plural(verdict.mandatory_total, 'mandatory requirement')} supported.`
  if (verdict.partially_supported_rows === 0) {
    return supported
  }
  return `${supported} ${plural(verdict.partially_supported_rows, 'row')} the documents do not settle.`
}

/** After the review: what was recorded, and that there is nothing left to press. */
function RecordedCard({
  bid,
  decision,
  onBackToMatrix,
}: {
  readonly bid: BidResponse
  readonly decision: Decision | undefined
  readonly onBackToMatrix?: () => void
}) {
  const status = BID_STATUS_LABELS[bid.status]
  return (
    <Card
      title="Your decision is recorded"
      icon={<Icon name="check" size={20} />}
      actions={<Badge tone={status.tone}>{status.label}</Badge>}
    >
      <p className="m-0 mb-3.5 flex flex-wrap items-center gap-3">
        {decision !== undefined && <VerdictChip verdict={decision} size="lg" confirmed />}
        <span className="text-text-secondary">
          Submitted with {plural(bid.matrix_rows.length, 'matrix row')}.
        </span>
      </p>
      <Notice>
        A review is submitted once. This bid has left the interrupt, so there is nothing further
        to confirm here.
      </Notice>
      {onBackToMatrix !== undefined && (
        <Button variant="secondary" onClick={onBackToMatrix} className="mt-[18px]">
          Back to matrix
        </Button>
      )}
    </Card>
  )
}

/**
 * The 409. Deliberately offers no way to send the review again: the API answers this when
 * the bid is not parked, so a second attempt can only be refused the same way. What it shows
 * instead is where the bid actually is.
 */
function ConflictCard({
  bid,
  onBackToMatrix,
}: {
  readonly bid: BidResponse | undefined
  readonly onBackToMatrix?: () => void
}) {
  const status = bid === undefined ? undefined : BID_STATUS_LABELS[bid.status]
  return (
    <Card
      title="This review was not submitted"
      icon={<Icon name="alert" size={20} />}
      actions={
        status === undefined ? undefined : <Badge tone={status.tone}>{status.label}</Badge>
      }
    >
      <Notice tone="danger" title="The bid had already moved on">
        {NOT_AWAITING_REVIEW}
      </Notice>
      <p className="m-0 mt-3.5 text-text-secondary">
        {bid === undefined
          ? 'The bid could not be re-read either, so what it says now is unknown. Reload the page to see it.'
          : `It now reads ${BID_STATUS_LABELS[bid.status].label.toLowerCase()}. Nothing you entered here was applied.`}
      </p>
      {onBackToMatrix !== undefined && (
        <Button variant="secondary" onClick={onBackToMatrix} className="mt-[18px]">
          Back to matrix
        </Button>
      )}
    </Card>
  )
}

/** The bid is not at its interrupt, so there is no review to submit — and why. */
function NotParkedCard({
  bid,
  onBackToMatrix,
}: {
  readonly bid: BidResponse
  readonly onBackToMatrix?: () => void
}) {
  const status = BID_STATUS_LABELS[bid.status]
  return (
    <Card
      title="Your decision"
      icon={<Icon name="shield" size={20} />}
      actions={<Badge tone={status.tone}>{status.label}</Badge>}
    >
      <Notice tone={bid.status === 'failed' ? 'danger' : 'neutral'} title={status.label}>
        {describeUnavailable(bid)}
      </Notice>
      {onBackToMatrix !== undefined && (
        <Button variant="secondary" onClick={onBackToMatrix} className="mt-[18px]">
          Back to matrix
        </Button>
      )}
    </Card>
  )
}

function describeUnavailable(bid: BidResponse): string {
  if (bid.status === 'failed') {
    return (
      bid.failure_reason ??
      'The run stopped before it reached a verdict, so there is nothing to confirm.'
    )
  }
  if (bid.status === 'complete') {
    return 'This bid has been reviewed already. A review is submitted once, and its decision stands.'
  }
  return (
    BID_STATUS_LABELS[bid.status].hint ??
    'The run has not reached its review interrupt yet. The decision opens when it does.'
  )
}
