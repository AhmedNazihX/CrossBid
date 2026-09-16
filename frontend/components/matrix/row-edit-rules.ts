import type { MatrixRow, RowEdit } from '@/lib/bids'
import { ROW_STATUS_LABELS } from './row-status'

/**
 * The three rules the review endpoint enforces, restated in the reviewer's own words so the
 * form refuses before the network does (story S4.5.2).
 *
 * Restating a server rule in a client is a duplication, and it is the right one here: a 422
 * arrives after the reviewer has already pressed Confirm on a screen full of work, and names
 * a `matrix_row_id` they have never seen. The server stays the authority — these sentences
 * are deliberately the same ones `backend/crossbid/models/review.py` and
 * `backend/crossbid/routers/bids.py` answer with, so the two never contradict each other, and
 * whichever one the reviewer meets reads the same.
 */

/** `MAX_COMMENT_CHARS` in `backend/crossbid/models/review.py`. */
export const MAX_REASON_CHARS = 4000

/** `RowEdit._changing_a_status_needs_a_reason`. */
export const STATUS_CHANGE_NEEDS_A_REASON =
  "Changing a row's status requires a reason, so the disagreement is recorded."

/** `_check_row_edit` — the rule `MatrixRow` itself carries, not a second definition of it. */
export const SUPPORTED_NEEDS_EVIDENCE =
  'A supported row needs an evidence quote or an attached document.'

export const REASON_TOO_LONG = `A reason is at most ${MAX_REASON_CHARS.toLocaleString('en-GB')} characters.`

/** The blank edit a row starts from: it changes nothing and is never submitted. */
export function blankEdit(matrixRowId: string): RowEdit {
  return {
    matrix_row_id: matrixRowId,
    status: null,
    override_reason: null,
    attached_doc_ids: [],
  }
}

/**
 * `RowEdit._edit_must_do_something`: an edit that sets no status, gives no reason and
 * attaches nothing is refused by the server, so it is dropped here instead — the reviewer who
 * opened a panel and closed it again has not asked for anything.
 */
export function isEmptyEdit(edit: RowEdit): boolean {
  return (
    (edit.status === null || edit.status === undefined) &&
    !hasReason(edit) &&
    edit.attached_doc_ids.length === 0
  )
}

export function hasReason(edit: RowEdit): boolean {
  return (edit.override_reason ?? '').trim().length > 0
}

/**
 * The edit as it would be sent: the reason trimmed and blank rather than whitespace, and a
 * status that merely restates the row's own dropped. The server cannot make that second call
 * — `RowEdit` carries no row — so it would demand a reason for a change nobody made, and
 * `describeChange` would rightly show none. Restating is not changing; nothing is sent.
 */
export function normalisedEdit(row: MatrixRow, edit: RowEdit): RowEdit {
  const reason = (edit.override_reason ?? '').trim()
  const status = edit.status === row.status ? null : edit.status
  return { ...edit, status, override_reason: reason.length > 0 ? reason : null }
}

/**
 * The sentence the server would answer with for this edit, or `undefined` when it would take
 * it. Mirrors `_check_row_edit`, which re-validates the row as the edit would leave it rather
 * than restating the rule — so this asks the same question: with this status and these
 * attachments, is the row still saveable?
 *
 * It judges the edit as `normalisedEdit` would send it, not as typed, so it and
 * `describeChange` cannot disagree: a reviewer is never blocked on a change the screen does
 * not show.
 */
export function describeBlocker(row: MatrixRow, edit: RowEdit): string | undefined {
  const sent = normalisedEdit(row, edit)
  const reason = sent.override_reason ?? ''
  if (reason.length > MAX_REASON_CHARS) {
    return REASON_TOO_LONG
  }
  if (sent.status !== null && sent.status !== undefined && reason.length === 0) {
    return STATUS_CHANGE_NEEDS_A_REASON
  }
  const status = sent.status ?? row.status
  const attachments = row.attached_doc_ids.length + edit.attached_doc_ids.length
  if (status === 'supported' && row.evidence.length === 0 && attachments === 0) {
    return SUPPORTED_NEEDS_EVIDENCE
  }
  return undefined
}

/** "Supported → Unsupported", for the line that keeps the agent's original on screen. */
export function describeChange(row: MatrixRow, edit: RowEdit | undefined): string | undefined {
  const status = edit?.status
  if (status === null || status === undefined || status === row.status) {
    return undefined
  }
  return `${ROW_STATUS_LABELS[row.status]} → ${ROW_STATUS_LABELS[status]}`
}
