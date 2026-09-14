'use client'

import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Icon } from '@/components/ui/icons'
import { Notice } from '@/components/ui/notice'
import { Select } from '@/components/ui/select'
import type { MatrixRow } from '@/lib/bids'
import type { RowEditsController } from './use-row-edits'

/** A company document this row could be backed by: whatever the parent judges attachable. */
export interface AttachableDocument {
  readonly id: string
  readonly name: string
}

export interface RowAttachmentsProps {
  readonly row: MatrixRow
  readonly edits: RowEditsController
  readonly attachable: readonly AttachableDocument[]
  readonly isPhone?: boolean
}

const NO_CHOICE = ''

/**
 * The "Add evidence" panel behind that control in `Main.dc.html`: pick one of the company's
 * own documents and it is listed under the row until the review is confirmed.
 *
 * Attaching is a two-step choose-then-attach rather than attach-on-change. A native `<select>`
 * fires `change` on every arrow key, so attach-on-change would file a document the moment a
 * keyboard user moved past its name — the same interaction a mouse user would never trigger.
 *
 * A document already on the row from the agent's own run is listed but has no remove control:
 * this panel edits the reviewer's additions, and a review never deletes what was cited.
 */
export function RowAttachments({
  row,
  edits,
  attachable,
  isPhone = false,
}: RowAttachmentsProps) {
  const [choice, setChoice] = useState<string>(NO_CHOICE)
  const pending = edits.editOf(row.id)?.attached_doc_ids ?? []
  const attached = new Set(edits.attachmentsOf(row.id))
  const offered = attachable.filter((document) => !attached.has(document.id))
  const names = new Map(attachable.map((document) => [document.id, document.name]))

  return (
    <div className="flex flex-col gap-2.5">
      {attached.size > 0 && (
        <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
          {row.attached_doc_ids.map((id) => (
            <li key={id} className="[font:var(--type-body-sm)] text-text-secondary">
              {names.get(id) ?? id} · already on this row
            </li>
          ))}
          {pending.map((id) => (
            <li key={id} className="flex items-center gap-1.5">
              <Icon name="fileCheck" size={14} className="shrink-0 text-text-muted" />
              <span className="min-w-0 flex-1 [font:var(--type-body-sm)] text-text-primary">
                {names.get(id) ?? id}
              </span>
              <button
                type="button"
                onClick={() => edits.detach(row.id, id)}
                aria-label={`Remove ${names.get(id) ?? id} from this requirement`}
                className="-mx-1 inline-flex min-h-8 items-center gap-1 rounded-sm px-1 text-[13px] font-medium text-text-secondary hover:bg-surface-hover hover:underline"
              >
                <Icon name="x" size={12} />
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}

      {attachable.length === 0 ? (
        <Notice>
          None of your company documents are ready to attach yet. Upload the certificate under
          Documents, wait for it to finish processing, then come back to this row.
        </Notice>
      ) : offered.length === 0 ? (
        <p className="m-0 [font:var(--type-body-sm)] text-text-muted">
          Every company document you have is already on this row.
        </p>
      ) : (
        <div className="flex flex-wrap items-end gap-2">
          <Select
            label="Company document"
            hint="Attached when you confirm the review, not before."
            options={[
              { value: NO_CHOICE, label: 'Choose a document…' },
              ...offered.map((document) => ({ value: document.id, label: document.name })),
            ]}
            value={choice}
            onValueChange={setChoice}
            className="min-w-[200px] flex-1"
          />
          <Button
            variant="secondary"
            size={isPhone ? 'md' : 'sm'}
            icon={<Icon name="plus" size={16} />}
            disabled={choice === NO_CHOICE}
            onClick={() => {
              edits.attach(row.id, choice)
              setChoice(NO_CHOICE)
            }}
          >
            Attach document
          </Button>
        </div>
      )}
    </div>
  )
}
