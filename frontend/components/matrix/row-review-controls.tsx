'use client'

import { useId, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Icon } from '@/components/ui/icons'
import { Notice } from '@/components/ui/notice'
import type { MatrixRow } from '@/lib/bids'
import type { AttachableDocument } from './row-attachments'
import { RowAttachments } from './row-attachments'
import { describeChange } from './row-edit-rules'
import { RowStatusEditor } from './row-status-editor'
import type { RowEditsController } from './use-row-edits'

/** Everything a row needs to be reviewable. Absent while the run is still checking. */
export interface RowReview {
  readonly edits: RowEditsController
  /** The company documents a reviewer may attach — the parent decides which are ready. */
  readonly attachable: readonly AttachableDocument[]
}

export interface RowReviewControlsProps extends RowReview {
  readonly row: MatrixRow
  readonly isPhone?: boolean
}

type OpenPanel = 'status' | 'evidence' | undefined

/**
 * The row of controls under the evidence block in `Main.dc.html`: Confirm, Change status,
 * Add evidence — in that order, in the artboard's secondary / secondary / ghost weights.
 *
 * Nothing here submits. Both panels write into the pending edit `useRowEdits` holds, and the
 * line above the buttons says what is pending and offers to undo it, so the reviewer can see
 * the shape of their review before the one Confirm that sends it. The agent's own finding
 * stays in the evidence block above, unchanged, the whole time.
 */
export function RowReviewControls({
  row,
  edits,
  attachable,
  isPhone = false,
}: RowReviewControlsProps) {
  const edit = edits.editOf(row.id)
  const [panel, setPanel] = useState<OpenPanel>(undefined)
  const panelId = useId()
  const size = isPhone ? 'md' : 'sm'
  const blocker = edits.blockerOf(row.id)
  const change = describeChange(row, edit)
  const attachedCount = edit?.attached_doc_ids.length ?? 0
  const isConfirmed = edits.isConfirmed(row.id)

  const toggle = (next: Exclude<OpenPanel, undefined>) =>
    setPanel((current) => (current === next ? undefined : next))

  return (
    <div className="flex flex-col gap-2.5 border-t border-border-default pt-3">
      {edit !== undefined && (
        <PendingSummary
          change={change}
          attachedCount={attachedCount}
          hasReason={(edit.override_reason ?? '').trim().length > 0}
          onUndo={() => {
            edits.clear(row.id)
            setPanel(undefined)
          }}
        />
      )}

      <div className="flex flex-wrap gap-2">
        <Button
          variant={isConfirmed ? 'primary' : 'secondary'}
          size={size}
          icon={<Icon name="check" size={16} />}
          aria-pressed={isConfirmed}
          onClick={() => (isConfirmed ? edits.clear(row.id) : edits.confirm(row.id))}
        >
          {isConfirmed ? 'Confirmed' : 'Confirm'}
        </Button>
        <Button
          variant="secondary"
          size={size}
          iconRight={
            <Icon
              name="chev"
              size={16}
              className={panel === 'status' ? 'rotate-180 transition-transform' : undefined}
            />
          }
          aria-expanded={panel === 'status'}
          aria-controls={panelId}
          onClick={() => toggle('status')}
        >
          Change status
        </Button>
        <Button
          variant="ghost"
          size={size}
          icon={<Icon name="upload" size={16} />}
          aria-expanded={panel === 'evidence'}
          aria-controls={panelId}
          onClick={() => toggle('evidence')}
        >
          Add evidence
        </Button>
      </div>

      {blocker !== undefined && panel !== 'status' && (
        <Notice tone="danger" title="This change cannot be saved yet">
          <p className="m-0">{blocker}</p>
        </Notice>
      )}

      <div id={panelId} hidden={panel === undefined} className="pt-0.5">
        {panel === 'status' && <RowStatusEditor row={row} edits={edits} isPhone={isPhone} />}
        {panel === 'evidence' && (
          <RowAttachments row={row} edits={edits} attachable={attachable} isPhone={isPhone} />
        )}
      </div>
    </div>
  )
}

/** What is waiting on Confirm for this row, in one sentence, with the way back. */
function PendingSummary({
  change,
  attachedCount,
  hasReason,
  onUndo,
}: {
  readonly change: string | undefined
  readonly attachedCount: number
  readonly hasReason: boolean
  readonly onUndo: () => void
}) {
  const parts = [
    change,
    attachedCount === 1 ? '1 document attached' : undefined,
    attachedCount > 1 ? `${attachedCount} documents attached` : undefined,
    change === undefined && hasReason ? 'Reason noted' : undefined,
  ].filter((part): part is string => part !== undefined)

  return (
    <p className="m-0 flex flex-wrap items-center gap-x-2 gap-y-1 [font:var(--type-body-sm)] text-text-secondary">
      <span className="font-medium text-text-primary">Not saved yet:</span>
      <span>{parts.join(' · ')}</span>
      <button
        type="button"
        onClick={onUndo}
        className="-mx-1 inline-flex min-h-8 items-center rounded-sm px-1 font-medium text-text-link hover:bg-surface-hover hover:underline"
      >
        Undo
      </button>
    </p>
  )
}
