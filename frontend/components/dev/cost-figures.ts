/**
 * How the cost report writes its numbers (story S4.6.2, over S5.2's `/dev/costs`).
 *
 * Kept beside the report rather than in `lib/format.ts`: these are the console's figures
 * and nothing else on the screens shows a dollar amount. `en-US` for the currency because
 * `en-GB` writes US dollars as "US$", and OpenRouter bills in dollars, not in a locale.
 *
 * **`unpriced_calls` is never dropped from a total.** A call OpenRouter returned no price
 * for is stored at zero (the column is `not null`), so a total with unpriced calls behind
 * it is a lower bound — and a lower bound shown as a number is wrong in the direction that
 * looks fine (ADR-0056). `describeUnpriced` is what every total is captioned with.
 */
import type { UsageTotals } from '@/lib/dev'

const USD = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
})

const COUNT = new Intl.NumberFormat('en-GB')

/** "$1.38", "$0.0042". Four places at most, because the column stores six and a report
 * that showed "$0.000000" would be claiming a precision nobody reads. */
export function formatUsd(amount: number): string {
  return USD.format(amount)
}

/** "114,000". */
export function formatCount(count: number): string {
  return COUNT.format(count)
}

/** The caption every cost total carries. */
export function describeUnpriced(unpricedCalls: number): string {
  if (unpricedCalls === 0) {
    return 'Every call priced'
  }
  const noun = unpricedCalls === 1 ? 'call' : 'calls'
  return `${formatCount(unpricedCalls)} unpriced ${noun} — a lower bound`
}

/** Whether a total must be read as a lower bound rather than as a number. */
export function isLowerBound(totals: UsageTotals): boolean {
  return totals.unpriced_calls > 0
}

/** "90,000 in / 12,000 out". */
export function formatTokens(totals: UsageTotals): string {
  return `${formatCount(totals.input_tokens)} in / ${formatCount(totals.output_tokens)} out`
}
