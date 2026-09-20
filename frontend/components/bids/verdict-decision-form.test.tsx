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
import userEvent from '@testing-library/user-event'
import { describe, expect, test, vi } from 'vitest'

import { MAX_REASON_CHARS } from '@/components/matrix/row-edit-rules'

import { VerdictDecisionForm } from './verdict-decision-form'
import type { Decision } from '@/lib/bids'

interface Options {
  /** `null` means the agent never scored this bid — passing `undefined` would take the default. */
  readonly agentDecision?: Decision | null
  readonly blockedRowCount?: number
  readonly isCompact?: boolean
}

function renderForm({
  agentDecision = 'go',
  blockedRowCount = 0,
  isCompact = false,
}: Options = {}) {
  const onSubmit = vi.fn()
  render(
    <VerdictDecisionForm
      agentDecision={agentDecision ?? undefined}
      isLocked={false}
      isSubmitting={false}
      submitError={undefined}
      blockedRowCount={blockedRowCount}
      onSubmit={onSubmit}
      isCompact={isCompact}
    />
  )
  return { onSubmit }
}

/**
 * The text of the refusal notice, not merely "the sentence is somewhere on screen".
 *
 * The acknowledgement's own description and the refusal for skipping it share the words
 * "never confirmed automatically" by design, so a bare `getByText` matches both and would pass
 * whether or not the form refused anything.
 */
function refusal(): string {
  return screen.getByText('This review was not submitted').parentElement?.textContent ?? ''
}

/** The disclosure's region is `hidden` when collapsed, which is what a reader is told too. */
function isChoicesHidden(): boolean {
  const radio = screen.getByRole('radio', { name: /^Go/, hidden: true })
  return radio.closest('[hidden]') !== null
}

describe('VerdictDecisionForm — the override reason', () => {
  test('is capped at the server’s MAX_COMMENT_CHARS, like its siblings', () => {
    renderForm()

    const reason = screen.getByLabelText(/Reason for overriding/)

    expect(reason).toHaveAttribute('maxlength', String(MAX_REASON_CHARS))
    expect(MAX_REASON_CHARS).toBe(4000)
  })
})

/**
 * The gates, which had no test at all until ADR-0106 collapsed the form into the rail.
 *
 * Every one of these was covered only by ADR-0028's manual walk through a live FR bid. That
 * was tolerable while the form was one flat card; it is not once a disclosure can hide the
 * field a refusal points at, which is the failure mode collapsing a form invites and the
 * reason these were written before the layout changed under them.
 */
describe('VerdictDecisionForm — the gates', () => {
  test('refuses an override with no reason, and puts the cursor in the box', async () => {
    const user = userEvent.setup()
    const { onSubmit } = renderForm({ agentDecision: 'go' })

    await user.click(screen.getByRole('radio', { name: /^No-go/ }))
    await user.click(screen.getByLabelText(/I have reviewed/))
    await user.click(screen.getByRole('button', { name: /^Confirm/ }))

    expect(onSubmit).not.toHaveBeenCalled()
    const reason = screen.getByLabelText(/Reason for overriding/)
    expect(reason).toHaveFocus()
    expect(reason).toHaveAttribute('aria-invalid', 'true')
  })

  test('refuses a decision that was never acknowledged', async () => {
    const user = userEvent.setup()
    const { onSubmit } = renderForm({ agentDecision: 'go' })

    await user.click(screen.getByRole('button', { name: /^Confirm/ }))

    expect(onSubmit).not.toHaveBeenCalled()
    expect(refusal()).toMatch(/never confirmed automatically/i)
  })

  test('confirms the agent’s own decision with no reason at all', async () => {
    const user = userEvent.setup()
    const { onSubmit } = renderForm({ agentDecision: 'conditional' })

    await user.click(screen.getByLabelText(/I have reviewed/))
    await user.click(screen.getByRole('button', { name: /^Confirm/ }))

    expect(onSubmit).toHaveBeenCalledWith('conditional', undefined)
  })

  test('refuses blocked rows last — after the decision and the acknowledgement', async () => {
    // ADR-0028's recorded defect: a reviewer who has chosen nothing must be told that first,
    // not sent to the matrix for rows they have not looked at yet.
    const user = userEvent.setup()
    const { onSubmit } = renderForm({ agentDecision: 'go', blockedRowCount: 2 })

    await user.click(screen.getByRole('button', { name: /^Confirm/ }))
    expect(refusal()).toMatch(/never confirmed automatically/i)

    await user.click(screen.getByLabelText(/I have reviewed/))
    await user.click(screen.getByRole('button', { name: /^Confirm/ }))

    expect(onSubmit).not.toHaveBeenCalled()
    expect(refusal()).toMatch(/2 rows/)
  })

  test('Confirm is never disabled while the form is still editable', () => {
    renderForm()

    expect(screen.getByRole('button', { name: /^Confirm/ })).toBeEnabled()
  })
})

/** The rail's shape (ADR-0106): the common path only, with everything else one click away. */
describe('VerdictDecisionForm — compact', () => {
  test('shows the acknowledgement and Confirm, and hides the choices', () => {
    renderForm({ isCompact: true, agentDecision: 'conditional' })

    expect(screen.getByLabelText(/I have reviewed/)).toBeVisible()
    // The button names the decision it will record, because the radio that used to say so is
    // behind the disclosure.
    expect(screen.getByRole('button', { name: /Confirm · Conditional/ })).toBeVisible()
    expect(isChoicesHidden()).toBe(true)
  })

  test('the disclosure reveals the four choices', async () => {
    const user = userEvent.setup()
    renderForm({ isCompact: true, agentDecision: 'conditional' })

    await user.click(screen.getByRole('button', { name: /Record a different decision/ }))

    expect(isChoicesHidden()).toBe(false)
    expect(screen.getAllByRole('radio')).toHaveLength(4)
  })

  test('a refusal that points inside the disclosure opens it first', async () => {
    // The whole risk of collapsing this form: a reason that is "required" behind a panel the
    // reviewer cannot see is a dead end. Measured red by removing `setChoicesOpen(true)` from
    // the override branch of `handleSubmit` — the notice appears and the box stays hidden.
    const user = userEvent.setup()
    renderForm({ isCompact: true, agentDecision: 'go' })

    await user.click(screen.getByRole('button', { name: /Record a different decision/ }))
    await user.click(screen.getByRole('radio', { name: /^No-go/ }))
    await user.click(screen.getByRole('button', { name: /Keep CrossBid/ }))
    expect(isChoicesHidden()).toBe(true)

    await user.click(screen.getByLabelText(/I have reviewed/))
    await user.click(screen.getByRole('button', { name: /^Confirm/ }))

    expect(isChoicesHidden()).toBe(false)
    expect(screen.getByLabelText(/Reason for overriding/)).toHaveFocus()
  })

  test('a bid the agent never scored starts open — there is nothing to confirm', () => {
    renderForm({ isCompact: true, agentDecision: null })

    expect(isChoicesHidden()).toBe(false)
  })
})
