'use client'

import { useState } from 'react'
import { cn } from 'cn'

import { Button } from '@/components/ui/button'
import { Field } from '@/components/ui/field'
import { Icon } from '@/components/ui/icons'
import type { MatrixRow } from '@/lib/bids'
import { MAX_COMMENT_CHARS, THUMB_DOWN, THUMB_UP, type Rating } from '@/lib/feedback'
import type { RowFeedbackController } from './use-row-feedback'

export interface RowFeedbackProps {
  readonly row: MatrixRow
  readonly feedback: RowFeedbackController
  readonly isPhone?: boolean
}

/**
 * "Was this check right?" — the thumbs and the correction under one matrix row (S4.6.3).
 *
 * There is no artboard for this one: the canvas of ADR-0014 draws the screens that existed
 * when it was confirmed, and none of them carries a rating. So, like
 * `components/auth/sign-in-card.tsx`, it is assembled from the primitives the artboards
 * already fixed — `Button` in its secondary and ghost weights, the `Field` label and hint
 * column, the review panel's own textarea — and invents no spacing, colour or type of its
 * own. It sits at the foot of the evidence block, under the reviewer's controls, because it
 * is about the answer above it and never about the tender.
 *
 * **The thumb is filed on the click.** The story's criterion is that a rating is stored, so
 * it does not wait behind a Save the bidder might never press. The comment box only appears
 * afterwards: a correction with no verdict attached is a note to nobody, and asking for
 * prose before the one-click answer would cost most ratings the story exists to collect.
 *
 * **Saving a comment re-files the same thumb**, which is why the button says "Save comment"
 * rather than "Send": the API appends, the latest answer is the one that shows, and the
 * bidder's earlier words are still in the record. Nothing here changes the matrix, the
 * verdict or the review — a rating is kept, never acted on (feedback-driven learning is cut
 * from the course build).
 */
export function RowFeedback({ row, feedback, isPhone = false }: RowFeedbackProps) {
  const [draft, setDraft] = useState<string | undefined>(undefined)
  const rating = feedback.ratingOf(row.id)
  const stored = feedback.commentOf(row.id)
  const error = feedback.errorOf(row.id)
  const isSending = feedback.isSending(row.id)
  const size = isPhone ? 'md' : 'sm'
  const comment = draft ?? stored ?? ''
  const isCommentSaved = comment.trim() !== '' && comment === stored

  async function rate(next: Rating) {
    await feedback.rate(row.id, next)
  }

  async function saveComment() {
    if (rating === undefined) {
      return
    }
    await feedback.rate(row.id, rating, comment)
  }

  return (
    <div className="flex flex-col gap-2 border-t border-border-default pt-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="[font:var(--type-body-sm)] text-text-secondary">
          Was this check right?
        </span>
        <ThumbButton
          name="thumbUp"
          label="Yes"
          isChosen={rating === THUMB_UP}
          isSending={isSending}
          size={size}
          onRate={() => void rate(THUMB_UP)}
        />
        <ThumbButton
          name="thumbDown"
          label="No"
          isChosen={rating === THUMB_DOWN}
          isSending={isSending}
          size={size}
          onRate={() => void rate(THUMB_DOWN)}
        />
        {rating !== undefined && error === undefined && !isSending && (
          <span className="[font:var(--type-body-sm)] text-text-muted">
            Kept with this row.
          </span>
        )}
      </div>

      {error !== undefined && (
        <p role="status" className="m-0 [font:var(--type-body-sm)] text-status-danger-text">
          Your rating was not saved: {error}
        </p>
      )}

      {rating !== undefined && (
        <div className={cn('flex flex-col gap-2', !isPhone && 'max-w-[420px]')}>
          <Field
            id={`${row.id}-feedback-comment`}
            label="What should it have said?"
            hint="Optional. Kept with the rating for whoever improves the agent next."
            hintId={`${row.id}-feedback-comment-hint`}
          >
            <textarea
              id={`${row.id}-feedback-comment`}
              rows={2}
              value={comment}
              maxLength={MAX_COMMENT_CHARS}
              onChange={(event) => setDraft(event.target.value)}
              aria-describedby={`${row.id}-feedback-comment-hint`}
              placeholder="The ISO 27001 certificate covers this scope."
              className="w-full resize-y rounded-md border border-border-default bg-surface-card px-3 py-2 text-base leading-[1.5] text-text-primary shadow-xs outline-none placeholder:text-text-placeholder focus-visible:border-border-focus focus-visible:shadow-[var(--shadow-focus)]"
            />
          </Field>
          <Button
            variant="secondary"
            size={size}
            className="self-start"
            disabled={isSending || comment.trim() === '' || isCommentSaved}
            onClick={() => void saveComment()}
          >
            {isCommentSaved ? 'Comment saved' : 'Save comment'}
          </Button>
        </div>
      )}
    </div>
  )
}

/**
 * One thumb. `aria-pressed` rather than a disabled button for the chosen one: it stays
 * operable for a screen reader, and pressing it again is a no-op the controller absorbs
 * rather than a second identical row in the log.
 */
function ThumbButton({
  name,
  label,
  isChosen,
  isSending,
  size,
  onRate,
}: {
  readonly name: 'thumbUp' | 'thumbDown'
  readonly label: string
  readonly isChosen: boolean
  readonly isSending: boolean
  readonly size: 'sm' | 'md'
  readonly onRate: () => void
}) {
  return (
    <Button
      variant={isChosen ? 'secondary' : 'ghost'}
      size={size}
      icon={<Icon name={name} size={16} />}
      aria-pressed={isChosen}
      disabled={isSending}
      onClick={onRate}
      className={cn(isChosen && 'border-border-focus')}
    >
      {label}
    </Button>
  )
}
