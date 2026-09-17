'use client'

import { useId } from 'react'
import { cn } from 'cn'

import { Field } from '@/components/ui/field'
import { Select } from '@/components/ui/select'
import type { MatrixRow, RowStatus } from '@/lib/bids'
import { MAX_REASON_CHARS } from './row-edit-rules'
import { ROW_STATUS_LABELS, ROW_STATUS_ORDER } from './row-status'
import type { RowEditsController } from './use-row-edits'

export interface RowStatusEditorProps {
  readonly row: MatrixRow
  readonly edits: RowEditsController
  readonly isPhone?: boolean
}

/** The empty option: the reviewer has not disagreed, so no `status` is sent for the row. */
const KEEP = ''

/**
 * The panel behind "Change status" in `Main.dc.html`: the four row words of the fixed
 * vocabulary (ADR-0013) and the reason that has to come with a change.
 *
 * The first option is the agent's own finding rather than a pre-selected status, because
 * "no change" and "changed to exactly what the agent said" are different submissions — the
 * second is an override with a reason attached, and the reviewer should have to mean it.
 *
 * The reason box is always open once the panel is, not revealed after a status is chosen:
 * the server refuses a status change with no reason, and a field that appears late reads as
 * a complication rather than as the condition it is.
 */
export function RowStatusEditor({ row, edits, isPhone = false }: RowStatusEditorProps) {
  const reasonId = useId()
  const edit = edits.editOf(row.id)
  const reason = edit?.override_reason ?? ''
  const blocker = edits.blockerOf(row.id)
  const isReasonMissing =
    edit?.status !== null && edit?.status !== undefined && reason.trim().length === 0

  return (
    <div className={cn('flex flex-col gap-3', !isPhone && 'max-w-[420px]')}>
      <Select
        label="Your finding"
        options={[
          { value: KEEP, label: `Agree — ${ROW_STATUS_LABELS[row.status].toLowerCase()}` },
          ...ROW_STATUS_ORDER.map((status) => ({
            value: status,
            label: ROW_STATUS_LABELS[status],
          })),
        ]}
        value={edit?.status ?? KEEP}
        onValueChange={(value) =>
          edits.setStatus(row.id, value === KEEP ? null : (value as RowStatus))
        }
        error={blocker !== undefined && !isReasonMissing ? blocker : undefined}
      />
      <Field
        id={reasonId}
        label="Why you disagree"
        hint="Recorded with the row, so the override can be explained later."
        error={isReasonMissing ? blocker : undefined}
        hintId={`${reasonId}-hint`}
      >
        <textarea
          id={reasonId}
          rows={3}
          value={reason}
          maxLength={MAX_REASON_CHARS}
          onChange={(event) => edits.setReason(row.id, event.target.value)}
          aria-invalid={isReasonMissing ? true : undefined}
          aria-describedby={`${reasonId}-hint`}
          placeholder="The Finanzamt certificate covers this — see page 2."
          className={cn(
            'w-full resize-y rounded-md border bg-surface-card px-3 py-2 text-base leading-[1.5] text-text-primary shadow-xs',
            'placeholder:text-text-placeholder focus-visible:border-border-focus focus-visible:shadow-[var(--shadow-focus)]',
            isReasonMissing ? 'border-status-danger' : 'border-border-default'
          )}
        />
      </Field>
    </div>
  )
}
