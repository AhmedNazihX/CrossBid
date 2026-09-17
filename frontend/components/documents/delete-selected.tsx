'use client'

import { useCallback, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Notice } from '@/components/ui/notice'
import { describeApiError } from '@/lib/api-client'
import { deleteDocument, type DocumentResponse } from '@/lib/documents'
import { plural } from '@/lib/format'

export interface DeleteSelectedProps {
  /** The documents currently ticked. Empty is the resting state and renders the count only. */
  readonly selected: readonly DocumentResponse[]
  /** Called with the documents the API confirmed gone — successes only, failures excluded. */
  readonly onDeleted: (deleted: readonly DocumentResponse[]) => void
}

interface Refusal {
  readonly name: string
  readonly reason: string
}

/**
 * Delete the ticked documents, from above the table rather than from inside a row.
 *
 * **Placed outside the table's scrolling box deliberately.** The first delete control this
 * repository had was the table's last column, and `DataTable` scrolls horizontally whenever
 * its content is wider than the window: at 1100 px the control sat 106 px past the right
 * edge, so a bidder who never dragged the table sideways had no way to reach it and no clue
 * it existed. A control that acts on a selection belongs where the selection is counted.
 *
 * Deleting is irreversible, so it is asked twice; and the count is in the question, because
 * "Delete?" reads the same whether it is about one file or eleven.
 *
 * Failures are reported per document rather than as one "something went wrong". The API
 * refuses a document a bid has claimed with a 409 and a sentence naming why, and a bulk
 * action that swallowed it would leave a row that silently refuses to go.
 */
export function DeleteSelected({ selected, onDeleted }: DeleteSelectedProps) {
  const [isConfirming, setIsConfirming] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [refusals, setRefusals] = useState<readonly Refusal[]>([])

  const remove = useCallback(async () => {
    setIsDeleting(true)
    setRefusals([])
    const deleted: DocumentResponse[] = []
    const refused: Refusal[] = []
    // One at a time: the list is short, the order is the one the bidder sees, and a burst of
    // parallel deletes against a rate-limited API turns a partial failure into a puzzle.
    for (const document of selected) {
      try {
        await deleteDocument(document.id)
        deleted.push(document)
      } catch (error) {
        refused.push({ name: document.name, reason: describeApiError(error) })
      }
    }
    setIsDeleting(false)
    setIsConfirming(false)
    setRefusals(refused)
    if (deleted.length > 0) {
      onDeleted(deleted)
    }
  }, [selected, onDeleted])

  const count = selected.length

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-3">
        <span className="[font:var(--type-body-sm)] text-text-secondary">
          {count === 0 ? 'No documents selected' : `${plural(count, 'document')} selected`}
        </span>
        {count > 0 && !isConfirming && (
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => setIsConfirming(true)}
          >
            Delete selected
          </Button>
        )}
        {count > 0 && isConfirming && (
          <>
            <span className="[font:var(--type-body-sm)] text-text-primary">
              Delete {plural(count, 'document')}? This cannot be undone.
            </span>
            <Button
              type="button"
              variant="danger"
              size="sm"
              disabled={isDeleting}
              onClick={() => void remove()}
            >
              {isDeleting ? 'Deleting…' : 'Delete'}
            </Button>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              disabled={isDeleting}
              onClick={() => setIsConfirming(false)}
            >
              Cancel
            </Button>
          </>
        )}
      </div>
      {refusals.length > 0 && (
        <Notice
          tone="danger"
          title={`${plural(refusals.length, 'document')} could not be deleted`}
        >
          <ul className="m-0 flex list-none flex-col gap-1 p-0">
            {refusals.map((refusal) => (
              <li key={refusal.name} className="[font:var(--type-body-sm)]">
                <strong className="font-medium">{refusal.name}</strong>: {refusal.reason}
              </li>
            ))}
          </ul>
        </Notice>
      )}
    </div>
  )
}
