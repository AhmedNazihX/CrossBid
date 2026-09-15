'use client'

import Link from 'next/link'

import { Card } from '@/components/ui/card'
import { DataTable, Td, Th, Tr } from '@/components/ui/data-table'
import { MetricCard } from '@/components/ui/metric-card'
import { Notice } from '@/components/ui/notice'
import type { DevCosts } from '@/lib/dev'
import { formatDateTime } from '@/lib/format'

import {
  describeUnpriced,
  formatCount,
  formatTokens,
  formatUsd,
  isLowerBound,
} from './cost-figures'

export interface CostReportProps {
  readonly costs: DevCosts | undefined
  readonly error: string | undefined
  readonly isLoading: boolean
}

/**
 * Where the money went: one total, then the same rows per node and per bid (S5.2's report,
 * shown by S4.6.2).
 *
 * **`unpriced_calls` sits beside every total** — on the metric card as its caption and as a
 * column of both tables — because a total with unpriced calls behind it is a lower bound,
 * and a lower bound printed as a number is wrong in the direction nobody audits
 * (ADR-0056). The metric card's caption turns red the moment the count is not zero.
 *
 * The figures are the company's own: the route is tenant-scoped, so a developer sees the
 * runs of the company they are signed in as, not everyone's. Embeddings are not in these
 * numbers, and the footer says so rather than letting the total pass for the whole bill.
 */
export function CostReport({ costs, error, isLoading }: CostReportProps) {
  if (isLoading) {
    return (
      <p className="m-0 [font:var(--type-body)] text-text-muted" role="status">
        Adding up the runs…
      </p>
    )
  }
  if (error !== undefined) {
    return (
      <Notice tone="danger" title="The cost report could not be loaded.">
        <p className="m-0">{error}</p>
      </Notice>
    )
  }
  if (costs === undefined) {
    return null
  }
  const { total } = costs
  const lowerBound = isLowerBound(total)
  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 sm:grid-cols-3">
        <MetricCard
          label={
            lowerBound ? 'Spent on chat completions (at least)' : 'Spent on chat completions'
          }
          value={formatUsd(total.cost_usd)}
          delta={describeUnpriced(total.unpriced_calls)}
          deltaTone={lowerBound ? 'danger' : 'neutral'}
        />
        <MetricCard
          label="Model calls"
          value={formatCount(total.calls)}
          delta={formatTokens(total)}
          deltaTone="neutral"
          period="tokens"
        />
        <MetricCard
          label="Bids with a recorded call"
          value={formatCount(costs.by_bid.length)}
          delta={costs.by_bid.length === 0 ? 'Nothing has run yet' : undefined}
          deltaTone="neutral"
        />
      </div>

      <Card title="Per node" headingLevel="h3" padding={16}>
        <DataTable
          caption="Tokens and cost per graph node and model, dearest first"
          footer="A node appears twice when a call fell back to the other vendor mid-run. Embeddings are bought from the same provider but are not counted here."
        >
          <thead>
            <tr>
              <Th>Node</Th>
              <Th>Model</Th>
              <Th>Provider</Th>
              <Th className="text-right">Calls</Th>
              <Th className="text-right">Tokens</Th>
              <Th className="text-right">Cost</Th>
              <Th className="text-right">Unpriced</Th>
            </tr>
          </thead>
          <tbody>
            {costs.by_node.length === 0 && (
              <Tr>
                <Td colSpan={7} className="text-text-muted">
                  No model call has been recorded for this company yet.
                </Td>
              </Tr>
            )}
            {costs.by_node.map((line) => (
              <Tr key={`${line.node}:${line.provider}:${line.model}`}>
                <Td className="[font:var(--type-mono)]">{line.node}</Td>
                <Td className="[font:var(--type-mono)]">{line.model}</Td>
                <Td>{line.provider}</Td>
                <Td className="text-right tabular-nums">{formatCount(line.calls)}</Td>
                <Td className="text-right tabular-nums whitespace-nowrap">
                  {formatTokens(line)}
                </Td>
                <Td className="text-right tabular-nums">{formatUsd(line.cost_usd)}</Td>
                <Td className="text-right tabular-nums">
                  <UnpricedCell count={line.unpriced_calls} />
                </Td>
              </Tr>
            ))}
          </tbody>
        </DataTable>
      </Card>

      <Card title="Per bid" headingLevel="h3" padding={16}>
        <DataTable
          caption="Tokens and cost per bid, most recently active first"
          footer="The newest 50 runs. A bid whose id is empty is spend that belongs to no run."
        >
          <thead>
            <tr>
              <Th>Bid</Th>
              <Th>Last call</Th>
              <Th className="text-right">Calls</Th>
              <Th className="text-right">Tokens</Th>
              <Th className="text-right">Cost</Th>
              <Th className="text-right">Unpriced</Th>
            </tr>
          </thead>
          <tbody>
            {costs.by_bid.length === 0 && (
              <Tr>
                <Td colSpan={6} className="text-text-muted">
                  No bid has spent anything yet.
                </Td>
              </Tr>
            )}
            {costs.by_bid.map((run) => (
              <Tr key={run.bid_id ?? 'no-bid'}>
                <Td className="[font:var(--type-mono)]">
                  {run.bid_id === null || run.bid_id === undefined ? (
                    <span className="text-text-muted">No bid</span>
                  ) : (
                    <Link href={`/bids/${encodeURIComponent(run.bid_id)}`}>{run.bid_id}</Link>
                  )}
                </Td>
                <Td className="whitespace-nowrap">{formatDateTime(run.last_call_at)}</Td>
                <Td className="text-right tabular-nums">{formatCount(run.calls)}</Td>
                <Td className="text-right tabular-nums whitespace-nowrap">
                  {formatTokens(run)}
                </Td>
                <Td className="text-right tabular-nums">{formatUsd(run.cost_usd)}</Td>
                <Td className="text-right tabular-nums">
                  <UnpricedCell count={run.unpriced_calls} />
                </Td>
              </Tr>
            ))}
          </tbody>
        </DataTable>
      </Card>
    </div>
  )
}

/** Zero in muted text; anything else in the danger colour, because it changes the row's
 * cost from a number into a lower bound. */
function UnpricedCell({ count }: { readonly count: number }) {
  return count === 0 ? (
    <span className="text-text-muted">0</span>
  ) : (
    <span className="font-medium text-status-danger-text">{formatCount(count)}</span>
  )
}
