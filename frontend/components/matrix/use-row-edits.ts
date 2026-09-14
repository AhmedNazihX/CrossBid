'use client'

import { useCallback, useMemo, useState } from 'react'

import type { MatrixRow, RowEdit, RowStatus } from '@/lib/bids'
import { blankEdit, describeBlocker, isEmptyEdit, normalisedEdit } from './row-edit-rules'

/**
 * The reviewer's pending changes to the matrix, held in the browser until they confirm
 * (story S4.5.2; the Confirm / Change status / Add evidence controls of `Main.dc.html`).
 *
 * Nothing here talks to the API. That is the point of the story's first acceptance
 * criterion: a reviewer works down thirty rows, changes their mind twice, and only then
 * presses Confirm — so a status change is a fact about this screen until the one
 * `POST /bids/{id}/review` that carries all of them. The agent's `MatrixRow` is never
 * touched, which is what lets every row keep showing what the agent said *and* what the
 * reviewer is about to say instead.
 *
 * The pending edits are `RowEdit` objects rather than some private shape, so the component
 * that owns Confirm can hand `edits` to a `ReviewSubmission` without a translation step in
 * between — `{ decision, override_reason, row_edits: [...controller.edits] }`.
 *
 * Every update returns new objects; the state map is replaced, never mutated.
 */

/** One pending edit the server would refuse, and the sentence it would refuse it with. */
export interface RowEditBlocker {
  readonly matrixRowId: string
  readonly message: string
}

export interface RowEditsController {
  /**
   * Every pending edit, in matrix order, reasons trimmed and the no-op edits dropped —
   * ready for `ReviewSubmission.row_edits`. Spread it: the generated schema's field is a
   * mutable array.
   */
  readonly edits: readonly RowEdit[]
  /** How many rows carry a pending edit. */
  readonly editedCount: number
  /**
   * Rows the reviewer has looked at and settled — confirmed as the agent left them, or
   * edited. Progress only: a row nobody touched is still recorded as confirmed when the
   * review is submitted, because the backend confirms every row the submission does not
   * edit. Nothing about `confirm` reaches the API.
   */
  readonly reviewedCount: number
  readonly rowCount: number
  /** Every pending edit the server would refuse. Empty means the review is safe to send. */
  readonly blockers: readonly RowEditBlocker[]
  readonly isSubmittable: boolean
  editOf(matrixRowId: string): RowEdit | undefined
  isConfirmed(matrixRowId: string): boolean
  /** The status the row would carry if the review were submitted now. */
  effectiveStatus(matrixRowId: string): RowStatus | undefined
  /** Why this row's pending edit would be refused, or `undefined` when it is fine. */
  blockerOf(matrixRowId: string): string | undefined
  /** The documents the row would carry: the agent's first, then the reviewer's. */
  attachmentsOf(matrixRowId: string): readonly string[]
  /** `null` puts the row back on the agent's finding. */
  setStatus(matrixRowId: string, status: RowStatus | null): void
  setReason(matrixRowId: string, text: string): void
  attach(matrixRowId: string, documentId: string): void
  detach(matrixRowId: string, documentId: string): void
  /** Marks the row settled as the agent left it, dropping any pending edit. */
  confirm(matrixRowId: string): void
  /** Drops this row's pending edit and its confirmation. */
  clear(matrixRowId: string): void
  /** Back to the agent's matrix everywhere — after a submission, or a discarded review. */
  reset(): void
}

interface RowEditsState {
  readonly pending: ReadonlyMap<string, RowEdit>
  readonly confirmed: ReadonlySet<string>
}

const EMPTY_STATE: RowEditsState = { pending: new Map(), confirmed: new Set() }

/**
 * @param rows the agent's matrix. It is read, never written: the rules need the row's own
 *   status, evidence and attachments to say whether an edit would leave it saveable.
 */
export function useRowEdits(rows: readonly MatrixRow[]): RowEditsController {
  const [state, setState] = useState<RowEditsState>(EMPTY_STATE)

  const rowsById = useMemo(() => new Map(rows.map((row) => [row.id, row])), [rows])

  /** One row's edit replaced by `change` — a new map, and the row no longer just confirmed. */
  const amend = useCallback((matrixRowId: string, change: (edit: RowEdit) => RowEdit) => {
    setState((current) => {
      const next = change(current.pending.get(matrixRowId) ?? blankEdit(matrixRowId))
      const pending = new Map(current.pending)
      if (isEmptyEdit(next)) {
        pending.delete(matrixRowId)
      } else {
        pending.set(matrixRowId, next)
      }
      const confirmed = new Set(current.confirmed)
      confirmed.delete(matrixRowId)
      return { pending, confirmed }
    })
  }, [])

  const setStatus = useCallback(
    (matrixRowId: string, status: RowStatus | null) => {
      amend(matrixRowId, (edit) => ({ ...edit, status }))
    },
    [amend]
  )

  const setReason = useCallback(
    (matrixRowId: string, text: string) => {
      amend(matrixRowId, (edit) => ({ ...edit, override_reason: text }))
    },
    [amend]
  )

  const attach = useCallback(
    (matrixRowId: string, documentId: string) => {
      amend(matrixRowId, (edit) =>
        edit.attached_doc_ids.includes(documentId)
          ? edit
          : { ...edit, attached_doc_ids: [...edit.attached_doc_ids, documentId] }
      )
    },
    [amend]
  )

  const detach = useCallback(
    (matrixRowId: string, documentId: string) => {
      amend(matrixRowId, (edit) => ({
        ...edit,
        attached_doc_ids: edit.attached_doc_ids.filter((id) => id !== documentId),
      }))
    },
    [amend]
  )

  const confirm = useCallback((matrixRowId: string) => {
    setState((current) => {
      const pending = new Map(current.pending)
      pending.delete(matrixRowId)
      return { pending, confirmed: new Set(current.confirmed).add(matrixRowId) }
    })
  }, [])

  const clear = useCallback((matrixRowId: string) => {
    setState((current) => {
      const pending = new Map(current.pending)
      pending.delete(matrixRowId)
      const confirmed = new Set(current.confirmed)
      confirmed.delete(matrixRowId)
      return { pending, confirmed }
    })
  }, [])

  const reset = useCallback(() => setState(EMPTY_STATE), [])

  const edits = useMemo(
    () =>
      rows
        .map((row) => state.pending.get(row.id))
        .filter((edit): edit is RowEdit => edit !== undefined)
        .map(normalisedEdit),
    [rows, state.pending]
  )

  const blockers = useMemo(
    () =>
      edits
        .map((edit) => {
          const row = rowsById.get(edit.matrix_row_id)
          const message = row === undefined ? undefined : describeBlocker(row, edit)
          return message === undefined
            ? undefined
            : { matrixRowId: edit.matrix_row_id, message }
        })
        .filter((blocker): blocker is RowEditBlocker => blocker !== undefined),
    [edits, rowsById]
  )

  return useMemo(() => {
    const blockersById = new Map(blockers.map((blocker) => [blocker.matrixRowId, blocker]))
    return {
      edits,
      editedCount: edits.length,
      reviewedCount: edits.length + state.confirmed.size,
      rowCount: rows.length,
      blockers,
      isSubmittable: blockers.length === 0,
      editOf: (matrixRowId) => state.pending.get(matrixRowId),
      isConfirmed: (matrixRowId) => state.confirmed.has(matrixRowId),
      effectiveStatus: (matrixRowId) =>
        state.pending.get(matrixRowId)?.status ?? rowsById.get(matrixRowId)?.status,
      blockerOf: (matrixRowId) => blockersById.get(matrixRowId)?.message,
      attachmentsOf: (matrixRowId) => [
        ...(rowsById.get(matrixRowId)?.attached_doc_ids ?? []),
        ...(state.pending.get(matrixRowId)?.attached_doc_ids ?? []),
      ],
      setStatus,
      setReason,
      attach,
      detach,
      confirm,
      clear,
      reset,
    }
  }, [
    blockers,
    edits,
    rows.length,
    rowsById,
    state,
    setStatus,
    setReason,
    attach,
    detach,
    confirm,
    clear,
    reset,
  ])
}
