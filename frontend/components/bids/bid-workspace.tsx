'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'

import { Breadcrumb } from '@/components/layout/breadcrumb'
import { LAST_BID_STORAGE_KEY } from '@/components/layout/nav-items'
import { PageHeader } from '@/components/layout/page-header'
import { Button } from '@/components/ui/button'
import { Notice } from '@/components/ui/notice'
import { API_BASE_URL, describeApiError } from '@/lib/api-client'
import { getBid, type BidResponse } from '@/lib/bids'
import { DesktopWorkspace } from './desktop-workspace'
import { PhoneWorkspace } from './phone-workspace'
import { useWorkspaceState } from './workspace-state'

type LoadState =
  | { readonly phase: 'loading' }
  | { readonly phase: 'failed'; readonly message: string }
  | { readonly phase: 'loaded'; readonly bid: BidResponse }

/**
 * How long the first `GET /bids/{id}` may take before the screen stops waiting.
 *
 * A failed request has always landed in the `failed` card below; a request that *never
 * settled* had no exit, and "Loading the bid…" stayed for as long as the tab was open
 * (reproduced 2026-09-16 against a stub that never answered). Twenty seconds is an order
 * of magnitude over the read's normal latency, cold pooler included, and short enough that
 * a bidder is told something before they reach for the reload button themselves. The e2e
 * suite waits this long for the card, so `e2e/bid-workspace-failures.spec.ts` repeats the
 * figure and must change with it.
 */
export const BID_LOAD_DEADLINE_MS = 20_000

/**
 * The bid workspace (story S4.5.1, Increment 1) — `Main.dc.html` on the desktop,
 * `WorkspacePhone.dc.html` below 900 px.
 *
 * Loads `GET /bids/{id}` once, then hands the row to `LiveWorkspace`, which polls it every
 * two seconds until the run reaches the interrupt, completes or fails, lists requirements
 * as soon as they exist, and pairs the list with the source panel.
 *
 * **The desktop gives each of the three its own place (ADR-0104).** "Ask the tender" sits
 * above the matrix in the left column, the verdict has a sticky right rail to itself, and the
 * source page opens as a drawer over both. This replaced ADR-0060's single tabbed 400 px
 * column, which had put Source, Ask and Verdict in competition for one space — itself a fix
 * for something worse, a stacked column with the verdict rendered *after* the whole matrix:
 * measured on the FR bid at 1440×900 the page was 23 204 px tall, "Ask the tender" began at
 * y=1 351 and the verdict at y=13 876, the product's one output fifteen screens down. What
 * ADR-0060 bought is kept: the decision is a line under the header, the verdict is on screen
 * in every state of the page, and a citation in an answer or a row opens the source on the
 * page it cites. On the phone the tabs are as they were: Matrix / Source / Verdict / Ask, a
 * tap away. Chat state lives in `useBidChat` here rather than in the panel, so a breakpoint
 * change or a tab switch does not lose the exchanges made so far.
 *
 * **Both layouts carry the same `DecisionLine` under the header.** ADR-0060's point was
 * that the decision is above the fold; the first build gave that line to the desktop only,
 * and a live audit of the phone DOM at 390×844 found no element anywhere that named the
 * decision — a bidder on a phone saw the notice number, the title, a document count and
 * four tabs, and had to find the Verdict tab to learn what CrossBid concluded. This is a
 * recorded deviation from `WorkspacePhone.dc.html` (ADR-0014), whose header stops at the
 * buyer line: the artboard predates ADR-0060, and the reason that moved the decision up on
 * the desktop is stronger on a screen a fifth the size.
 */
export function BidWorkspace({ bidId }: { readonly bidId: string }) {
  const [state, setState] = useState<LoadState>({ phase: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    // Two controllers, because the two aborts mean opposite things: an unmount (or a new
    // attempt) must set no state, and the deadline must set `failed`.
    const controller = new AbortController()
    const deadline = new AbortController()
    const timer = setTimeout(() => deadline.abort(), BID_LOAD_DEADLINE_MS)
    setState({ phase: 'loading' })
    getBid(bidId, AbortSignal.any([controller.signal, deadline.signal]))
      .then((bid) => setState({ phase: 'loaded', bid }))
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return
        setState({
          phase: 'failed',
          message: deadline.signal.aborted ? describeLoadDeadline() : describeApiError(cause),
        })
      })
      .finally(() => clearTimeout(timer))
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [bidId, attempt])

  useEffect(() => {
    try {
      window.sessionStorage.setItem(LAST_BID_STORAGE_KEY, bidId)
    } catch {
      // Storage may be unavailable; Compliance then falls back to the tender list.
    }
  }, [bidId])

  if (state.phase === 'loading') {
    return (
      <>
        <Breadcrumb items={[{ label: 'Tenders', href: '/bids' }, { label: 'Loading…' }]} />
        <p role="status" className="m-0 text-text-muted">
          Loading the bid…
        </p>
      </>
    )
  }
  if (state.phase === 'failed') {
    return (
      <>
        <Breadcrumb items={[{ label: 'Tenders', href: '/bids' }, { label: 'Bid' }]} />
        <PageHeader title="This bid could not be opened" />
        <Notice tone="danger" title="The bid could not be loaded">
          {state.message}
        </Notice>
        <div className="mt-4 flex gap-2">
          <Button variant="secondary" onClick={() => setAttempt((n) => n + 1)}>
            Try again
          </Button>
          <Button asChild variant="ghost">
            <Link href="/bids">Back to tenders</Link>
          </Button>
        </div>
      </>
    )
  }
  return <LiveWorkspace initial={state.bid} />
}

function describeLoadDeadline(): string {
  return (
    `The API at ${API_BASE_URL} did not answer within ${BID_LOAD_DEADLINE_MS / 1000} seconds. ` +
    'It may be starting up or unreachable.'
  )
}

function LiveWorkspace({ initial }: { readonly initial: BidResponse }) {
  const state = useWorkspaceState(initial)

  // Neither layout may be drawn before the media query has answered: picking one and
  // correcting it would mount the wrong tree, lose the chat, and flash. The live region is
  // rendered meanwhile so a screen reader is not silent while the run is already moving.
  if (state.isDesktop === undefined) {
    return (
      <p role="status" aria-live="polite" className="sr-only">
        {state.announcement}
      </p>
    )
  }
  return state.isDesktop ? <DesktopWorkspace state={state} /> : <PhoneWorkspace state={state} />
}
