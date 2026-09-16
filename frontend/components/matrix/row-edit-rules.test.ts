/**
 * `row-edit-rules.ts` — the review endpoint's 422 rules, restated in the browser (S4.5.2).
 *
 * **The originals are `backend/crossbid/models/review.py` (`RowEdit`, `MAX_COMMENT_CHARS`)
 * and `backend/crossbid/models/matrix.py` (`MatrixRow._supported_requires_evidence`), applied
 * by `_check_row_edit` in `backend/crossbid/routers/bids.py`. This module is a copy of them
 * and must not drift.** The copy exists so the form refuses before the network does; the
 * cost is that a rule changed on one side and not the other fails silently in the worst
 * direction — the form lets an edit through, the server refuses it after the reviewer has
 * pressed Confirm on a screen full of work, and names a `matrix_row_id` nobody has seen.
 *
 * So every assertion here is written against the backend's rule as it reads in Python, not
 * against what the TypeScript happens to do: the length bound is inclusive because Pydantic's
 * `max_length=4000` is; the length check wins over the missing-reason check because a field
 * that fails validation stops Pydantic's `after` model validators from running at all; a
 * `supported` row is saveable on evidence *or* an attachment because the invariant says
 * `not self.evidence and not self.attached_doc_ids`.
 *
 * One deliberate difference is pinned rather than papered over: the browser trims a reason
 * before it counts, while Python's `not "   "` is `False`. The two agree in practice only
 * because `normalisedEdit` turns whitespace into `null` before anything is sent, so the
 * test for that is the one that keeps the difference harmless.
 */
import { describe, expect, test } from 'vitest'

import type { MatrixRow, RowEdit } from '@/lib/bids'

import {
  MAX_REASON_CHARS,
  REASON_TOO_LONG,
  STATUS_CHANGE_NEEDS_A_REASON,
  SUPPORTED_NEEDS_EVIDENCE,
  blankEdit,
  describeBlocker,
  describeChange,
  hasReason,
  isEmptyEdit,
  normalisedEdit,
} from './row-edit-rules'

const ROW_ID = 'row-0001'
const DOC_ID = 'a2a1f4ce-3a6b-4c9e-9b6f-0c2f6d0e1a11'

function row(overrides: Partial<MatrixRow> = {}): MatrixRow {
  return {
    id: ROW_ID,
    requirement_id: 'req-0001',
    status: 'unsupported',
    evidence: [],
    agent_rationale: 'Kein Nachweis im Bestand gefunden.',
    agent_status: 'unsupported',
    reviewer_status: 'pending',
    attached_doc_ids: [],
    ...overrides,
  }
}

function cited(): MatrixRow {
  return row({
    status: 'supported',
    agent_status: 'supported',
    evidence: [
      {
        document_id: DOC_ID,
        document_name: 'Jahresabschluss_2025.pdf',
        page: 2,
        quote: '7,4 Mio. EUR',
      },
    ],
  })
}

function edit(overrides: Partial<RowEdit> = {}): RowEdit {
  return { ...blankEdit(ROW_ID), ...overrides }
}

describe('MAX_REASON_CHARS', () => {
  test('is MAX_COMMENT_CHARS from backend/crossbid/models/review.py', () => {
    // A number, not a rule: if the backend moves its bound, this is the line that fails.
    expect(MAX_REASON_CHARS).toBe(4000)
  })
})

describe('blankEdit and isEmptyEdit', () => {
  test('the blank edit changes nothing and is recognised as empty', () => {
    const blank = blankEdit(ROW_ID)
    expect(blank).toEqual({
      matrix_row_id: ROW_ID,
      status: null,
      override_reason: null,
      attached_doc_ids: [],
    })
    expect(isEmptyEdit(blank)).toBe(true)
  })

  test('a reason made only of whitespace is still an empty edit', () => {
    // `RowEdit._edit_must_do_something` would refuse the null this becomes on the wire.
    expect(isEmptyEdit(edit({ override_reason: '   \n\t' }))).toBe(true)
  })

  test.each<[string, Partial<RowEdit>]>([
    ['a status', { status: 'not_applicable' }],
    ['a reason', { override_reason: 'The clause does not apply to a service contract.' }],
    ['an attachment', { attached_doc_ids: [DOC_ID] }],
  ])('an edit that sets %s is not empty', (_what, overrides) => {
    expect(isEmptyEdit(edit(overrides))).toBe(false)
  })
})

describe('hasReason and normalisedEdit', () => {
  test('whitespace is not a reason', () => {
    expect(hasReason(edit({ override_reason: '  ' }))).toBe(false)
    expect(hasReason(edit({ override_reason: null }))).toBe(false)
    expect(hasReason(edit({ override_reason: ' Umsatz reicht aus. ' }))).toBe(true)
  })

  test('the edit on the wire carries a trimmed reason, and null rather than whitespace', () => {
    expect(
      normalisedEdit(edit({ override_reason: '  Umsatz reicht aus.  ' })).override_reason
    ).toBe('Umsatz reicht aus.')
    expect(normalisedEdit(edit({ override_reason: '   ' })).override_reason).toBeNull()
    expect(normalisedEdit(edit({ override_reason: undefined })).override_reason).toBeNull()
  })

  test('normalising returns a new edit and leaves the original untouched', () => {
    const original = edit({ override_reason: '  padded  ' })
    const normalised = normalisedEdit(original)
    expect(normalised).not.toBe(original)
    expect(original.override_reason).toBe('  padded  ')
  })
})

describe('describeBlocker — RowEdit._changing_a_status_needs_a_reason', () => {
  test('a status change with no reason is refused with the sentence the server uses', () => {
    expect(describeBlocker(cited(), edit({ status: 'unsupported' }))).toBe(
      STATUS_CHANGE_NEEDS_A_REASON
    )
  })

  test('a status change whose reason is only whitespace is refused the same way', () => {
    expect(
      describeBlocker(cited(), edit({ status: 'unsupported', override_reason: ' ' }))
    ).toBe(STATUS_CHANGE_NEEDS_A_REASON)
  })

  test('a status change with a reason is accepted', () => {
    expect(
      describeBlocker(
        cited(),
        edit({ status: 'unsupported', override_reason: 'Der Umsatz ist unter der Schwelle.' })
      )
    ).toBeUndefined()
  })

  test('setting the status the row already has still needs a reason, as the server requires', () => {
    // Python checks `self.status is not None`, not "differs from the row" — so does this.
    expect(describeBlocker(cited(), edit({ status: 'supported' }))).toBe(
      STATUS_CHANGE_NEEDS_A_REASON
    )
  })

  test('a reason with no status change is a comment and needs nothing else', () => {
    expect(
      describeBlocker(row(), edit({ override_reason: 'Checked against the notice.' }))
    ).toBe(undefined)
  })
})

describe('describeBlocker — Field(max_length=MAX_COMMENT_CHARS)', () => {
  test('a reason of exactly the bound is accepted, because Pydantic max_length is inclusive', () => {
    const reason = 'x'.repeat(MAX_REASON_CHARS)
    expect(describeBlocker(row(), edit({ override_reason: reason }))).toBeUndefined()
  })

  test('one character over the bound is refused', () => {
    const reason = 'x'.repeat(MAX_REASON_CHARS + 1)
    expect(describeBlocker(row(), edit({ override_reason: reason }))).toBe(REASON_TOO_LONG)
  })

  test('the bound is measured after trimming, matching what is sent', () => {
    const reason = ` ${'x'.repeat(MAX_REASON_CHARS)} `
    expect(describeBlocker(row(), edit({ override_reason: reason }))).toBeUndefined()
  })

  test('an over-long reason on a status change reports the length, as the server would', () => {
    // A failed field stops Pydantic's `after` validators, so the server names only the length.
    const reason = 'x'.repeat(MAX_REASON_CHARS + 1)
    expect(
      describeBlocker(row(), edit({ status: 'not_applicable', override_reason: reason }))
    ).toBe(REASON_TOO_LONG)
  })

  test('the sentence names the bound with a thousands separator', () => {
    expect(REASON_TOO_LONG).toBe('A reason is at most 4,000 characters.')
  })
})

describe('describeBlocker — MatrixRow._supported_requires_evidence via _check_row_edit', () => {
  const marking = (overrides: Partial<RowEdit>): RowEdit =>
    edit({ status: 'supported', override_reason: 'Nachweis liegt vor.', ...overrides })

  test('marking a row supported with no quote and no attachment is refused', () => {
    expect(describeBlocker(row(), marking({}))).toBe(SUPPORTED_NEEDS_EVIDENCE)
  })

  test('an attachment on the edit is enough', () => {
    expect(describeBlocker(row(), marking({ attached_doc_ids: [DOC_ID] }))).toBeUndefined()
  })

  test('an attachment already on the row is enough', () => {
    expect(describeBlocker(row({ attached_doc_ids: [DOC_ID] }), marking({}))).toBeUndefined()
  })

  test('a quote already on the row is enough', () => {
    const withQuote = row({ evidence: cited().evidence })
    expect(describeBlocker(withQuote, marking({}))).toBeUndefined()
  })

  test('the rule applies to the status the row would end up with, not only to the edit', () => {
    // No status in the edit, so the row stays `supported` — and it still has its quote.
    expect(describeBlocker(cited(), edit({ attached_doc_ids: [DOC_ID] }))).toBeUndefined()
  })

  test.each(['partially_supported', 'unsupported', 'not_applicable'] as const)(
    'marking a row %s needs no evidence',
    (status) => {
      expect(describeBlocker(row(), marking({ status }))).toBeUndefined()
    }
  )
})

describe('describeChange', () => {
  test('is undefined when the edit sets no status', () => {
    expect(describeChange(cited(), undefined)).toBeUndefined()
    expect(describeChange(cited(), edit())).toBeUndefined()
  })

  test('is undefined when the edit sets the status the row already has', () => {
    expect(describeChange(cited(), edit({ status: 'supported' }))).toBeUndefined()
  })

  test('reads "before → after" in the design system words, keeping the agent original on screen', () => {
    expect(describeChange(cited(), edit({ status: 'partially_supported' }))).toBe(
      'Supported → Partially supported'
    )
    expect(describeChange(row(), edit({ status: 'not_applicable' }))).toBe(
      'Unsupported → Not applicable'
    )
  })
})
