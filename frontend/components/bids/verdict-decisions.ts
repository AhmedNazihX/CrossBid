import type { Decision } from '@/lib/bids'

/**
 * The vocabulary of `Verdict.dc.html`'s "Your decision", and the two sentences the API
 * writes when it refuses a review (story S4.5.3).
 *
 * The four words are fixed (ADR-0013) and are the same ones the agent's own chip carries, so
 * confirming and overriding read as the same kind of statement. The refusal sentences are
 * quoted from `routers/bids.py` rather than rewritten: the screen must not describe a
 * failure in words the API would contradict if the same call were made again.
 */
export interface DecisionChoice {
  readonly value: Decision
  readonly label: string
  /** What choosing it commits the bidder to. */
  readonly description: string
}

/** The artboard's order: what proceeds first, what holds last. */
export const DECISION_CHOICES: readonly DecisionChoice[] = [
  {
    value: 'go',
    label: 'Go',
    description: 'Proceed to the bid. Only when every unsupported row is resolved.',
  },
  {
    value: 'conditional',
    label: 'Conditional',
    description:
      'Proceed while the missing evidence is collected. Recorded against the tender with your reason.',
  },
  {
    value: 'no_go',
    label: 'No-go',
    description: 'Do not bid. The tender is archived; reasons are kept for reporting.',
  },
  {
    value: 'insufficient_evidence',
    label: 'Insufficient evidence',
    description: 'Hold — request documents from your team before deciding.',
  },
]

/**
 * Whether this decision overrides the agent rather than confirming it, which is the one
 * thing that makes a reason mandatory.
 *
 * Mirrors `_check_review` in `routers/bids.py`, including its quiet case: a bid the agent
 * never scored has no decision to differ from, so nothing is required and the reviewer's
 * word stands alone.
 */
export function isOverride(
  agentDecision: Decision | undefined,
  decision: Decision | undefined
): boolean {
  return agentDecision !== undefined && decision !== undefined && decision !== agentDecision
}

/**
 * `OVERRIDE_NEEDS_A_REASON_DETAIL` without its trailing field name — the reviewer sees a
 * labelled box, not `override_reason`. The form raises this before the call, so the 422 that
 * carries the server's own wording is the belt to this braces.
 */
export const OVERRIDE_NEEDS_A_REASON =
  "Your decision differs from the agent's, so a reason is required."

/** `NOT_AWAITING_REVIEW_DETAIL`, verbatim: the answer to a 409. */
export const NOT_AWAITING_REVIEW =
  'This bid is not waiting for a review. It has either been reviewed already or has not ' +
  'finished running.'

/** The acknowledgement of the artboard — a verdict is never confirmed by default. */
export const REVIEWED_MATRIX_LABEL = 'I have reviewed the compliance matrix'
