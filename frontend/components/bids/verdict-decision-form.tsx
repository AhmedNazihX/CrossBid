'use client'

import { useEffect, useId, useRef, useState } from 'react'
import { cn } from 'cn'

import { MAX_REASON_CHARS } from '@/components/matrix/row-edit-rules'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Field } from '@/components/ui/field'
import { Icon } from '@/components/ui/icons'
import { Notice } from '@/components/ui/notice'
import type { Decision } from '@/lib/bids'
import {
  DECISION_CHOICES,
  isOverride,
  OVERRIDE_NEEDS_A_REASON,
  REVIEWED_MATRIX_LABEL,
} from './verdict-decisions'

/**
 * The "Your decision" card of `Verdict.dc.html` (story S4.5.3): the four decisions, the
 * reason box, the acknowledgement, Confirm verdict and Back to matrix.
 *
 * Everything the API would refuse is refused here first and said in the same words, because
 * the alternative is a reviewer who learns that an override needs a reason only after
 * pressing the button that commits the bid. Nothing is silently disabled instead: a control
 * that cannot be pressed cannot explain itself, so Confirm stays live until the call is
 * actually in flight and a refusal names what is missing and puts the cursor there.
 *
 * **`isCompact` is the rail's shape (ADR-0106), and it hides nothing that is needed.** Drawn
 * whole the card is 670–720 px, which is four fifths of the 380 px rail's entire scroll
 * viewport, so the decision sat below everything. Confirming the agent is the common path and
 * needs two controls — the acknowledgement and the button — so those stay; the four radios and
 * the reason box move behind a disclosure. **The disclosure opens itself whenever a refusal
 * would otherwise point at something the reviewer cannot see**, which is the whole risk of
 * collapsing a form and is why `pendingFocus` exists: the field has to be rendered before it
 * can be focused, so the refusal sets the target and an effect moves focus once React has
 * drawn it. A bid the agent never scored starts expanded — there is nothing to confirm.
 */
export interface VerdictDecisionFormProps {
  /** The agent's advisory decision, or `undefined` when it never scored this bid. */
  readonly agentDecision: Decision | undefined
  /** Blocks every control: the call is in flight, or it has already settled. */
  readonly isLocked: boolean
  readonly isSubmitting: boolean
  /** What the API said when it refused the last attempt. */
  readonly submitError: string | undefined
  /**
   * How many of the reviewer's own row edits the server would refuse. Non-zero blocks the
   * submit — see `blockedByRows`. A count rather than the messages: each row already shows
   * its own sentence where the reviewer made the edit, and repeating them here would name
   * rows by an id they have never seen, which is the thing the server's 422 does badly.
   */
  readonly blockedRowCount: number
  readonly onSubmit: (decision: Decision, overrideReason: string | undefined) => void
  readonly onBackToMatrix?: () => void
  /** The rail's shape: the common path only, with the four choices behind a disclosure. */
  readonly isCompact?: boolean
}

const REASON_HINT =
  "Required when your decision differs from the agent's. Both stay visible on the tender."
const NO_DECISION_CHOSEN = 'Choose one of the four decisions before confirming.'
const NOT_ACKNOWLEDGED =
  'Confirm that you have reviewed the compliance matrix. A verdict is never confirmed automatically.'

/**
 * The reviewer has edited a row in a way the server refuses. Said here in rows rather than
 * in ids, because the row itself is already showing what is wrong with it — and because a
 * 422 naming a `matrix_row_id` is exactly the answer S4.5.2's mirrored rules exist to spare
 * them.
 */
function blockedByRows(count: number): string {
  const rows = count === 1 ? 'One row' : `${count} rows`
  const they = count === 1 ? 'it' : 'them'
  return `${rows} cannot be saved as you have left ${they}. Fix ${they} in the matrix above — each says what is missing — then confirm.`
}

export function VerdictDecisionForm({
  agentDecision,
  isLocked,
  isSubmitting,
  submitError,
  blockedRowCount,
  onSubmit,
  onBackToMatrix,
  isCompact = false,
}: VerdictDecisionFormProps) {
  // Seeded once, which is sound because the agent's verdict cannot change while the bid is
  // parked: confirming is the common path, so the agent's own decision starts selected.
  const [decision, setDecision] = useState<Decision | undefined>(agentDecision)
  const [reason, setReason] = useState('')
  const [hasReviewed, setHasReviewed] = useState(false)
  const [reasonError, setReasonError] = useState<string | undefined>(undefined)
  const [formError, setFormError] = useState<string | undefined>(undefined)
  // A bid the agent never scored has nothing to confirm, so the choices cannot start hidden.
  const [isChoicesOpen, setChoicesOpen] = useState(agentDecision === undefined)
  const [pendingFocus, setPendingFocus] = useState<'choice' | 'reason' | undefined>(undefined)

  const groupName = useId()
  const choicesId = useId()
  const reasonId = useId()
  const reasonHintId = `${reasonId}-hint`
  const firstChoiceRef = useRef<HTMLInputElement>(null)
  const reasonRef = useRef<HTMLTextAreaElement>(null)
  const acknowledgeRef = useRef<HTMLInputElement>(null)

  const isReasonRequired = isOverride(agentDecision, decision)
  const message = formError ?? submitError
  const areChoicesShown = !isCompact || isChoicesOpen
  const chosen = DECISION_CHOICES.find((choice) => choice.value === decision)

  // Focus after the disclosure has opened, not before: a refusal that points at a field React
  // has not drawn yet lands on nothing, which is exactly the failure collapsing a form invites.
  useEffect(() => {
    if (pendingFocus === undefined) {
      return
    }
    const target = pendingFocus === 'reason' ? reasonRef.current : firstChoiceRef.current
    target?.focus()
    setPendingFocus(undefined)
  }, [pendingFocus])

  function handleChoose(next: Decision) {
    setDecision(next)
    setFormError(undefined)
    if (!isOverride(agentDecision, next)) {
      setReasonError(undefined)
    }
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (isLocked) {
      return
    }
    if (decision === undefined) {
      setFormError(NO_DECISION_CHOSEN)
      setChoicesOpen(true)
      setPendingFocus('choice')
      return
    }
    const trimmed = reason.trim()
    if (isOverride(agentDecision, decision) && trimmed.length === 0) {
      setFormError(undefined)
      setReasonError(OVERRIDE_NEEDS_A_REASON)
      setChoicesOpen(true)
      setPendingFocus('reason')
      return
    }
    if (!hasReviewed) {
      setFormError(NOT_ACKNOWLEDGED)
      acknowledgeRef.current?.focus()
      return
    }
    // Last, because it is about the matrix rather than this form: a reviewer who has not
    // chosen a decision should be told that first.
    if (blockedRowCount > 0) {
      setFormError(blockedByRows(blockedRowCount))
      return
    }
    setFormError(undefined)
    setReasonError(undefined)
    onSubmit(decision, trimmed.length === 0 ? undefined : trimmed)
  }

  return (
    <Card
      title="Your decision"
      headingLevel="h2"
      icon={<Icon name="shield" size={20} />}
      padding={isCompact ? 20 : 24}
    >
      <form onSubmit={handleSubmit} aria-busy={isSubmitting} noValidate>
        {isCompact && (
          // A real disclosure: the control names what it reveals, says whether it is open, and
          // points at the region, so a screen reader is told the same thing the chevron says.
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="-ml-3 mb-1"
            aria-expanded={isChoicesOpen}
            aria-controls={choicesId}
            disabled={isLocked}
            onClick={() => setChoicesOpen((open) => !open)}
            iconRight={<Icon name={isChoicesOpen ? 'chev' : 'chevR'} size={16} />}
          >
            {isChoicesOpen ? 'Keep CrossBid’s recommendation' : 'Record a different decision'}
          </Button>
        )}
        <div id={choicesId} hidden={!areChoicesShown}>
          <fieldset className="m-0 min-w-0 border-0 p-0">
            <legend className="sr-only">Your decision on this tender</legend>
            <div className="flex flex-col gap-3">
              {DECISION_CHOICES.map((choice, index) => (
                <label
                  key={choice.value}
                  className="flex cursor-pointer items-start gap-2.5 [font:var(--type-body)] has-[input:disabled]:cursor-not-allowed has-[input:disabled]:opacity-50"
                >
                  <input
                    ref={index === 0 ? firstChoiceRef : undefined}
                    type="radio"
                    name={groupName}
                    value={choice.value}
                    checked={decision === choice.value}
                    disabled={isLocked}
                    onChange={() => handleChoose(choice.value)}
                    className="peer sr-only"
                  />
                  <span
                    aria-hidden="true"
                    className="mt-px inline-flex size-[18px] shrink-0 rounded-full border border-border-strong bg-surface-card transition-[border-width] [transition-duration:var(--duration-fast)] peer-checked:border-[5px] peer-checked:border-blue-500 peer-focus-visible:shadow-[var(--shadow-focus)] peer-focus-visible:focus-ring"
                  />
                  <span className="min-w-0">
                    <span className="block leading-5 font-medium [overflow-wrap:anywhere]">
                      {choice.label}
                      {choice.value === agentDecision && (
                        <span className="font-normal text-text-muted">
                          {' '}
                          · CrossBid&rsquo;s recommendation
                        </span>
                      )}
                    </span>
                    <span className="block [font:var(--type-body-sm)] text-text-muted [overflow-wrap:anywhere]">
                      {choice.description}
                    </span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>

          <Field
            id={reasonId}
            label={`Reason for overriding ${isReasonRequired ? '(required)' : '(optional)'}`}
            hint={REASON_HINT}
            error={reasonError}
            hintId={reasonHintId}
            className="mt-3.5"
          >
            <textarea
              ref={reasonRef}
              id={reasonId}
              name="override_reason"
              rows={4}
              value={reason}
              // The server's `MAX_COMMENT_CHARS`, mirrored as the row editor and the feedback
              // comment already do (ADR-0064: both sides hold the fact, so the server's number
              // wins). Without it this was the one box that could send a reason the server
              // refused, and the 422 came back as a pydantic list (audit M18).
              maxLength={MAX_REASON_CHARS}
              disabled={isLocked}
              required={isReasonRequired}
              aria-describedby={reasonHintId}
              aria-invalid={reasonError === undefined ? undefined : true}
              onChange={(event) => {
                setReason(event.target.value)
                setReasonError(undefined)
              }}
              placeholder="What the agent could not see, and why you are deciding otherwise."
              className={cn(
                'min-h-[84px] w-full rounded-md border bg-surface-card px-3 py-2.5 [font:var(--type-body)] text-text-primary shadow-xs transition-shadow [transition-duration:var(--duration-fast)] placeholder:text-text-placeholder focus:border-border-focus focus:shadow-[var(--shadow-focus)] disabled:opacity-50',
                reasonError === undefined ? 'border-border-default' : 'border-status-danger'
              )}
            />
          </Field>
        </div>

        <div className="my-[18px] h-px bg-border-default" />

        <Checkbox
          ref={acknowledgeRef}
          name="reviewed_matrix"
          label={REVIEWED_MATRIX_LABEL}
          description="Required. Verdicts are never confirmed automatically."
          checked={hasReviewed}
          disabled={isLocked}
          onChange={(event) => {
            setHasReviewed(event.target.checked)
            setFormError(undefined)
          }}
        />

        {message !== undefined && (
          <Notice tone="danger" title="This review was not submitted" className="mt-[18px]">
            {message}
          </Notice>
        )}

        <div className="mt-[18px] flex gap-2">
          <Button
            type="submit"
            disabled={isLocked}
            icon={<Icon name="shield" size={16} />}
            className="flex-1"
          >
            {isSubmitting
              ? 'Confirming…'
              : isCompact && chosen !== undefined
                ? `Confirm · ${chosen.label}`
                : 'Confirm verdict'}
          </Button>
          {onBackToMatrix !== undefined && (
            <Button type="button" variant="secondary" onClick={onBackToMatrix}>
              Back to matrix
            </Button>
          )}
        </div>
      </form>
    </Card>
  )
}
