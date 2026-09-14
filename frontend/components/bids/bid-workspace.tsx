'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Link from 'next/link'

import { Breadcrumb } from '@/components/layout/breadcrumb'
import { LAST_BID_STORAGE_KEY } from '@/components/layout/nav-items'
import { PageHeader } from '@/components/layout/page-header'
import { MatrixSummary } from '@/components/matrix/matrix-summary'
import { RequirementCards } from '@/components/matrix/requirement-cards'
import { RequirementList } from '@/components/matrix/requirement-list'
import { indexRowsByRequirement } from '@/components/matrix/row-status'
import type { AttachableDocument } from '@/components/matrix/row-attachments'
import { useRowEdits } from '@/components/matrix/use-row-edits'
import { citableDocuments } from '@/components/matrix/source-documents'
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
import { getBid, isAwaitingReview, isBidSettled, type BidResponse } from '@/lib/bids'
import { listDocuments } from '@/lib/documents'
import { formatLanguage, formatLanguagePair, plural } from '@/lib/format'
import { SHELL_MEDIA_QUERY, useMediaQuery } from '@/lib/use-media-query'
import { usePolling } from '@/lib/use-polling'
import { BID_STATUS_LABELS } from './bid-status'
import { VerdictPanel } from './verdict-panel'

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
  const { value: polled, error: pollError } = usePolling({
    initialValue: initial,
    fetchLatest,
    isSettled: isBidSettled,
  })
  // The server's answer to the review is newer than any poll, and polling has stopped by
  // then anyway — `complete` is settled. So a reviewed bid supersedes the polled one for the
  // rest of this mount. A 409 lands here too: the panel re-reads the bid and hands back what
  // is actually true, which is exactly what the screen should switch to (S4.5.3).
  const [reviewed, setReviewed] = useState<BidResponse | undefined>(undefined)
  const bid = reviewed ?? polled
  const isDesktop = useMediaQuery(SHELL_MEDIA_QUERY)
  const [selection, setSelection] = useState<SourceSelection | undefined>(undefined)
  const [activeCitation, setActiveCitation] = useState<Citation | undefined>(undefined)
  const [phoneTab, setPhoneTab] = useState<PhoneTab>('matrix')
  const announcement = useStatusAnnouncement(bid)
  const edits = useRowEdits(bid.matrix_rows)
  const attachable = useAttachableDocuments(isAwaitingReview(bid))

  const status = BID_STATUS_LABELS[bid.status]
  const isRunning = !isBidSettled(bid)
  const totalPages = bid.documents.reduce((sum, d) => sum + d.pages, 0)
  const unreadPages = bid.documents.reduce((sum, d) => sum + d.unread_pages.length, 0)
  const rowsByRequirement = useMemo(
    () => indexRowsByRequirement(bid.matrix_rows),
    [bid.matrix_rows]
  )
  const sourceDocuments = useMemo(
    () => citableDocuments(bid.documents, bid.matrix_rows),
    [bid.documents, bid.matrix_rows]
  )
  const hasRows = bid.matrix_rows.length > 0
  // Only while the bid is parked: omitting it leaves the matrix exactly as S4.5.1 built it,
  // which is what a finished or still-running bid should show.
  const review = isAwaitingReview(bid) ? { edits, attachable } : undefined

  const handleCite = useCallback(
    (citation: Citation) => {
      // A page-less citation is a DUME/ESPD requirement: XML, no pages, and the panel shows
      // PDFs. `CitationLink` renders those as a label rather than a button so this cannot be
      // reached from the UI — the guard is here because the type allows it and opening the
      // panel on nothing would be worse than doing nothing.
      if (citation.page === null) return

      const document =
        sourceDocuments.find((d) => d.id === citation.documentId) ??
        sourceDocuments.find((d) => d.name === citation.documentName)
      setActiveCitation(citation)
      if (document !== undefined) {
        setSelection({ documentId: document.id, page: citation.page })
      }
      setPhoneTab('source')
    },
    [sourceDocuments]
  )

  const handleSelect = useCallback((next: SourceSelection) => {
    setSelection(next)
    setActiveCitation(undefined)
  }, [])

  const emptyMessage = describeEmptyList(bid)
  const reviewNote =
    bid.verdict === null
      ? 'The verdict is written once checking has finished.'
      : 'Confirm the verdict, or override it with a reason. Your row edits go with it.'
  const showVerdict = useCallback(() => setPhoneTab('verdict'), [])
  const backToMatrix = useCallback(() => setPhoneTab('matrix'), [])
  const verdictPanel = (
    <VerdictPanel
      bid={bid}
      rowEdits={edits.edits}
      blockedRowCount={edits.blockers.length}
      onReviewed={setReviewed}
      onBackToMatrix={isDesktop === false ? backToMatrix : undefined}
    />
  )
  const reviewButton =
    bid.verdict === null ? (
      <Button
        disabled
        aria-describedby="review-verdict-note"
        icon={<Icon name="shield" size={16} />}
      >
        Review verdict
      </Button>
    ) : (
      // A link, not a button: the panel is on this page and the action is "take me to it",
      // so it should open in a new tab, be copyable, and move focus the way an anchor does.
      <Link
        href="#verdict"
        className="inline-flex h-9 items-center gap-2 rounded-md bg-accent-default px-3.5 [font:var(--type-body-sm)] font-medium text-text-inverse no-underline transition-colors hover:bg-accent-strong focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-default"
      >
        <Icon name="shield" size={16} />
        Review verdict
      </Link>
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
          {hasRows ? (
            <MatrixSummary
              rows={bid.matrix_rows}
              requirementCount={bid.requirements.length}
              isChecking={isRunning}
            />
          ) : (
            <p className="m-0 text-[13px] leading-none">
              <b className="font-semibold">{bid.requirements.length}</b>
              <span className="text-text-muted"> requirements extracted</span>
              {unreadPages > 0 && (
                <span className="text-text-muted"> · {plural(unreadPages, 'page')} unread</span>
              )}
            </p>
          )}
        </div>
        {liveRegion}
        <div className="flex flex-1 flex-col gap-2.5 px-4 py-3">
          <div id="phone-panel-matrix" role="tabpanel" hidden={phoneTab !== 'matrix'}>
            <RequirementCards
              requirements={bid.requirements}
              rowsByRequirement={rowsByRequirement}
              bidderLanguage={bid.bidder_language}
              isChecking={isRunning}
              activeCitation={activeCitation}
              onCite={handleCite}
              emptyMessage={emptyMessage}
              review={review}
            />
          </div>
          <div id="phone-panel-source" role="tabpanel" hidden={phoneTab !== 'source'}>
            {phoneTab === 'source' && (
              <SourcePanel
                documents={sourceDocuments}
                selection={selection}
                onSelect={handleSelect}
                variant="phone"
              />
            )}
          </div>
          <div id="phone-panel-verdict" role="tabpanel" hidden={phoneTab !== 'verdict'}>
            {phoneTab === 'verdict' && verdictPanel}
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
            disabled={bid.verdict === null}
            aria-describedby="review-verdict-note"
            icon={<Icon name="shield" size={16} />}
            onClick={showVerdict}
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
        <div className="flex min-w-0 flex-col gap-3">
          {hasRows && (
            <MatrixSummary
              rows={bid.matrix_rows}
              requirementCount={bid.requirements.length}
              isChecking={isRunning}
            />
          )}
          <RequirementList
            requirements={bid.requirements}
            rowsByRequirement={rowsByRequirement}
            problems={bid.problems}
            documents={bid.documents}
            bidderLanguage={bid.bidder_language}
            isChecking={isRunning}
            activeCitation={activeCitation}
            onCite={handleCite}
            emptyMessage={emptyMessage}
            review={review}
          />
        </div>
        <SourcePanel
          documents={sourceDocuments}
          selection={selection}
          onSelect={handleSelect}
        />
      </div>
      {bid.verdict !== null && (
        <div id="verdict" className="mt-6 scroll-mt-4">
          {verdictPanel}
        </div>
      )}
    </>
  )
}

/**
 * The company's own evidence, as the documents a reviewer may attach to a row (S4.5.2).
 *
 * Fetched once, and only while the bid is parked: a finished bid has nothing to attach to,
 * and a running one has no rows yet. Tender documents are deliberately not offered — a row
 * is proved by what the bidder holds, not by the buyer's own pack — and a document still
 * being parsed is not attachable, so both filters are applied here rather than in the panel.
 *
 * A failure costs the attach control and nothing else: the reviewer can still change a
 * status and give a reason, so the list stays empty and the panel says so.
 */
function useAttachableDocuments(isEnabled: boolean): readonly AttachableDocument[] {
  const [documents, setDocuments] = useState<readonly AttachableDocument[]>([])
  useEffect(() => {
    if (!isEnabled) {
      return
    }
    const controller = new AbortController()
    listDocuments(controller.signal)
      .then((all) =>
        setDocuments(
          all
            .filter((d) => d.kind === 'company_evidence' && d.status === 'ready')
            .map((d) => ({ id: d.id, name: d.name }))
        )
      )
      .catch(() => {
        // Attaching is one of three things a reviewer can do to a row; losing the list must
        // not take the other two with it.
      })
    return () => controller.abort()
  }, [isEnabled])
  return documents
}

/**
 * One sentence per change worth announcing — the stage moving on, requirements arriving, or
 * matrix rows arriving — for the page's single live region. Counts are announced at most
 * once per change so a screen reader is not read every poll, and the checked count is
 * announced against the total, because rows land lane by lane rather than all at once.
 */
function useStatusAnnouncement(bid: BidResponse): string {
  const [announcement, setAnnouncement] = useState('')
  const previousRef = useRef<Snapshot | undefined>(undefined)
  const { status } = bid
  const requirements = bid.requirements.length
  const rows = bid.matrix_rows.length
  useEffect(() => {
    const previous = previousRef.current
    const current: Snapshot = { status, requirements, rows }
    previousRef.current = current
    if (previous === undefined) {
      return
    }
    const sentence = describeChange(previous, current)
    if (sentence !== undefined) {
      setAnnouncement(sentence)
    }
  }, [status, requirements, rows])
  return announcement
}

interface Snapshot {
  readonly status: BidResponse['status']
  readonly requirements: number
  readonly rows: number
}

function describeChange(previous: Snapshot, current: Snapshot): string | undefined {
  if (previous.status !== current.status) {
    return `${BID_STATUS_LABELS[current.status].label}. ${plural(current.requirements, 'requirement')} extracted.`
  }
  if (previous.rows !== current.rows) {
    return `${current.rows} of ${plural(current.requirements, 'requirement')} checked so far.`
  }
  if (previous.requirements !== current.requirements) {
    return `${plural(current.requirements, 'requirement')} extracted so far.`
  }
  return undefined
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
