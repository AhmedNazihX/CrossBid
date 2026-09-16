/**
 * `VerdictDecisionForm` — the one reason box that could reach the server too long (S4.5.3,
 * audit finding M18).
 *
 * Its two siblings — the row status editor and the row feedback comment — cap their
 * textareas at the server's `MAX_COMMENT_CHARS`, so the browser never sends a reason the
 * server refuses. This box had no cap. The 422 that came back carried pydantic's list, and
 * the notice under the button rendered that list as JSON (`lib/api-client.test.ts` pins the
 * other half). Per ADR-0064 both sides hold the fact, so the server's number wins and the
 * browser mirrors it rather than choosing its own.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { MAX_REASON_CHARS } from '@/components/matrix/row-edit-rules'

import { VerdictDecisionForm } from './verdict-decision-form'

function renderForm() {
  render(
    <VerdictDecisionForm
      agentDecision="go"
      isLocked={false}
      isSubmitting={false}
      submitError={undefined}
      blockedRowCount={0}
      onSubmit={vi.fn()}
    />
  )
}

describe('VerdictDecisionForm — the override reason', () => {
  test('is capped at the server’s MAX_COMMENT_CHARS, like its siblings', () => {
    renderForm()

    const reason = screen.getByLabelText(/Reason for overriding/)

    expect(reason).toHaveAttribute('maxlength', String(MAX_REASON_CHARS))
    expect(MAX_REASON_CHARS).toBe(4000)
  })
})
