'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import Link from 'next/link'

import { Breadcrumb } from '@/components/layout/breadcrumb'
import { LAST_BID_STORAGE_KEY } from '@/components/layout/nav-items'
import { PageHeader } from '@/components/layout/page-header'
import { RequirementCards } from '@/components/matrix/requirement-cards'
import { RequirementList } from '@/components/matrix/requirement-list'
import type { Citation } from '@/components/matrix/citation'
import { SourcePanel, type SourceSelection } from '@/components/pdf/source-panel'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/ui/icons'
import { MetricCard } from '@/components/ui/metric-card'
import { Notice } from '@/components/ui/notice'
import { Tabs } from '@/components/ui/tabs'
import { Tag } from '@/components/ui/tag'
import { describeApiError } from '@/lib/api-client'
import { getBid, isBidSettled, type BidResponse } from '@/lib/bids'
import { formatLanguage, formatLanguagePair, plural } from '@/lib/format'
import { SHELL_MEDIA_QUERY, useMediaQuery } from '@/lib/use-media-query'
import { usePolling } from '@/lib/use-polling'
import { BID_STATUS_LABELS } from './bid-status'

type LoadState =
  | { readonly phase: 'loading' }
  | { readonly phase: 'failed'; readonly message: string }
  | { readonly phase: 'loaded'; readonly bid: BidResponse }

/**
 * The bid workspace (story S4.5.1, Increment 1) — `Main.dc.html` on the desktop,
 * `WorkspacePhone.dc.html` below 900 px.
 *
 * Loads `GET /bids/{id}` once, then hands the row to `LiveWorkspace`, which polls it every
 * two seconds until the run reaches the interrupt, completes or fails, lists requirements
 * as soon as they exist, and pairs the list with the source panel.
 */
export function BidWorkspace({ bidId }: { readonly bidId: string }) {
  const [state, setState] = useState<LoadState>({ phase: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    setState({ phase: 'loading' })
    getBid(bidId, controller.signal)
      .then((bid) => setState({ phase: 'loaded', bid }))
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) {
          setState({ phase: 'failed', message: describeApiError(cause) })
        }
      })
    return () => controller.abort()
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

type PhoneTab = 'matrix' | 'source' | 'verdict'

const PHONE_TABS: readonly { value: PhoneTab; label: string }[] = [
  { value: 'matrix', label: 'Matrix' },
  { value: 'source', label: 'Source' },
  { value: 'verdict', label: 'Verdict' },
]

function LiveWorkspace({ initial }: { readonly initial: BidResponse }) {
  const fetchLatest = useCallback(
    (signal: AbortSignal) => getBid(initial.id, signal),
    [initial.id]
  )
  const { value: bid, error: pollError } = usePolling({
    initialValue: initial,
    fetchLatest,
    isSettled: isBidSettled,
  })
  const isDesktop = useMediaQuery(SHELL_MEDIA_QUERY)
  const [selection, setSelection] = useState<SourceSelection | undefined>(undefined)
  const [activeCitation, setActiveCitation] = useState<Citation | undefined>(undefined)
  const [phoneTab, setPhoneTab] = useState<PhoneTab>('matrix')
  const announcement = useStatusAnnouncement(bid)

  const status = BID_STATUS_LABELS[bid.status]
  const isRunning = !isBidSettled(bid)
  const totalPages = bid.documents.reduce((sum, d) => sum + d.pages, 0)
  const unreadPages = bid.documents.reduce((sum, d) => sum + d.unread_pages.length, 0)

  const handleCite = useCallback(
    (citation: Citation) => {
      const document = bid.documents.find((d) => d.name === citation.documentName)
      setActiveCitation(citation)
      if (document !== undefined) {
        setSelection({ documentId: document.id, page: citation.page })
      }
      setPhoneTab('source')
    },
    [bid.documents]
  )

  const handleSelect = useCallback((next: SourceSelection) => {
    setSelection(next)
    setActiveCitation(undefined)
  }, [])

  const emptyMessage = describeEmptyList(bid)
  const reviewNote = 'The verdict follows the evidence check, which lands in Increment 2.'
  const reviewButton = (
    <Button
      disabled
      aria-describedby="review-verdict-note"
      icon={<Icon name="shield" size={16} />}
    >
      Review verdict
    </Button>
  )

  const liveRegion = (
    <p role="status" aria-live="polite" className="sr-only">
      {announcement}
    </p>
  )

  if (isDesktop === undefined) {
    return liveRegion
  }

  if (!isDesktop) {
    return (
      <div className="-mx-4 -my-5 flex min-h-[calc(100vh-56px)] flex-col">
        <div className="flex flex-col gap-2.5 px-4 pt-3.5">
          <div className="flex items-center justify-between gap-2">
            <span className="[font:var(--type-mono)] text-text-muted">
              {bid.notice_number ?? '—'} ·{' '}
              {formatLanguagePair(bid.source_language, bid.bidder_language)}
            </span>
            <Badge tone={status.tone} size="sm">
              {status.label}
            </Badge>
          </div>
          <h1 className="m-0 text-lg font-semibold leading-[1.3] tracking-[-0.02em] [overflow-wrap:anywhere]">
            {bid.title}
          </h1>
          <p className="m-0 [font:var(--type-body-sm)] text-text-secondary">
            {plural(bid.documents.length, 'document')} · {plural(totalPages, 'page')}
            {isRunning && status.hint !== undefined ? ` · ${status.hint}` : ''}
          </p>
          {bid.status === 'failed' && bid.failure_reason !== null && (
            <Notice tone="danger" title="The run stopped">
              {bid.failure_reason}
            </Notice>
          )}
          <Tabs
            items={PHONE_TABS}
            value={phoneTab}
            onChange={setPhoneTab}
            size="lg"
            fullWidth
            aria-label="Workspace sections"
            panelId={(value) => `phone-panel-${value}`}
          />
          <p className="m-0 text-[13px] leading-none">
            <b className="font-semibold">{bid.requirements.length}</b>
            <span className="text-text-muted"> requirements extracted</span>
            {unreadPages > 0 && (
              <span className="text-text-muted"> · {plural(unreadPages, 'page')} unread</span>
            )}
          </p>
        </div>
        {liveRegion}
        <div className="flex flex-1 flex-col gap-2.5 px-4 py-3">
          <div id="phone-panel-matrix" role="tabpanel" hidden={phoneTab !== 'matrix'}>
            <RequirementCards
              requirements={bid.requirements}
              activeCitation={activeCitation}
              onCite={handleCite}
              emptyMessage={emptyMessage}
            />
          </div>
          <div id="phone-panel-source" role="tabpanel" hidden={phoneTab !== 'source'}>
            {phoneTab === 'source' && (
              <SourcePanel
                documents={bid.documents}
                selection={selection}
                onSelect={handleSelect}
                variant="phone"
              />
            )}
          </div>
          <div id="phone-panel-verdict" role="tabpanel" hidden={phoneTab !== 'verdict'}>
            <Notice title="No verdict yet">{reviewNote}</Notice>
          </div>
          {pollError !== undefined && (
            <p className="m-0 [font:var(--type-body-sm)] text-text-muted">
              Could not refresh: {describeApiError(pollError)}
            </p>
          )}
        </div>
        <div className="sticky bottom-0 border-t border-border-default bg-surface-card px-4 pt-3 pb-6">
          <Button
            size="lg"
            fullWidth
            disabled
            aria-describedby="review-verdict-note"
            icon={<Icon name="shield" size={16} />}
          >
            Review verdict
          </Button>
          <p id="review-verdict-note" className="sr-only">
            {reviewNote}
          </p>
        </div>
      </div>
    )
  }

  return (
    <>
      <Breadcrumb
        items={[
          { label: 'Tenders', href: '/bids' },
          { label: bid.notice_number ?? bid.title, mono: bid.notice_number !== null },
        ]}
      />
      <PageHeader
        title={bid.title}
        actions={
          <>
            <Badge tone={status.tone}>{status.label}</Badge>
            {reviewButton}
            <p id="review-verdict-note" className="sr-only">
              {reviewNote}
            </p>
          </>
        }
        className="mb-0"
      />
      <div className="mt-4 mb-6 flex flex-wrap gap-2.5">
        <Tag>{formatLanguagePair(bid.source_language, bid.bidder_language)}</Tag>
        <Tag>
          {plural(totalPages, 'page')} · {formatLanguage(bid.source_language)}
        </Tag>
        <Tag>{plural(bid.documents.length, 'document')}</Tag>
        {bid.notice_number !== null && <Tag mono>{bid.notice_number}</Tag>}
      </div>
      {liveRegion}
      {isRunning && status.hint !== undefined && (
        <Notice className="mb-6">
          <span className="font-medium text-text-primary">{status.label}.</span> {status.hint}
        </Notice>
      )}
      {bid.status === 'failed' && bid.failure_reason !== null && (
        <Notice tone="danger" title="The run stopped" className="mb-6">
          {bid.failure_reason}
        </Notice>
      )}
      {pollError !== undefined && (
        <p className="m-0 mb-4 [font:var(--type-body-sm)] text-text-muted">
          Could not refresh: {describeApiError(pollError)}
        </p>
      )}
      <div className="mb-7 grid gap-4 md:grid-cols-3">
        <MetricCard
          label="Requirements extracted"
          value={bid.requirements.length}
          deltaTone="neutral"
          period={isRunning ? 'so far · all cited' : 'all cited'}
        />
        <MetricCard
          label="Pages in the pack"
          value={totalPages}
          delta={unreadPages > 0 ? `${unreadPages} unread` : undefined}
          deltaTone="neutral"
          period={plural(bid.documents.length, 'document')}
        />
        <MetricCard
          label="Problems flagged"
          value={bid.problems.length}
          deltaTone="neutral"
          period="listed under the table"
        />
      </div>
      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_400px]">
        <RequirementList
          requirements={bid.requirements}
          problems={bid.problems}
          documents={bid.documents}
          bidderLanguage={bid.bidder_language}
          activeCitation={activeCitation}
          onCite={handleCite}
          emptyMessage={emptyMessage}
        />
        <SourcePanel documents={bid.documents} selection={selection} onSelect={handleSelect} />
      </div>
    </>
  )
}

/**
 * One sentence per change worth announcing — the stage moving on, or requirements arriving —
 * for the page's single live region. Requirement counts are announced at most once per
 * change so a screen reader is not read every poll.
 */
function useStatusAnnouncement(bid: BidResponse): string {
  const [announcement, setAnnouncement] = useState('')
  const previousRef = useRef<{ status: BidResponse['status']; count: number } | undefined>(
    undefined
  )
  useEffect(() => {
    const previous = previousRef.current
    const current = { status: bid.status, count: bid.requirements.length }
    previousRef.current = current
    if (previous === undefined) {
      return
    }
    if (previous.status !== current.status) {
      setAnnouncement(
        `${BID_STATUS_LABELS[current.status].label}. ${plural(current.count, 'requirement')} extracted.`
      )
    } else if (previous.count !== current.count) {
      setAnnouncement(`${plural(current.count, 'requirement')} extracted so far.`)
    }
  }, [bid.status, bid.requirements.length])
  return announcement
}

function describeEmptyList(bid: BidResponse): string {
  if (bid.status === 'failed') {
    return 'The run stopped before any requirement was extracted.'
  }
  if (isBidSettled(bid)) {
    return 'No requirements were extracted from this pack. The footer of the problems line says what the run could not read.'
  }
  return `${BID_STATUS_LABELS[bid.status].label}… requirements appear here as soon as they are extracted, each with its page in the tender.`
}
