'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Link from 'next/link'
import { cn } from 'cn'

import { Breadcrumb } from '@/components/layout/breadcrumb'
import { LAST_BID_STORAGE_KEY } from '@/components/layout/nav-items'
import { PageHeader } from '@/components/layout/page-header'
import { MatrixSummary } from '@/components/matrix/matrix-summary'
import { RequirementCards } from '@/components/matrix/requirement-cards'
import { RequirementList } from '@/components/matrix/requirement-list'
import { indexRowsByRequirement } from '@/components/matrix/row-status'
import type { AttachableDocument } from '@/components/matrix/row-attachments'
import { useRowEdits } from '@/components/matrix/use-row-edits'
import { useRowFeedback } from '@/components/matrix/use-row-feedback'
import { citableDocuments } from '@/components/matrix/source-documents'
import type { Citation } from '@/components/matrix/citation'
import { SourcePanel, type SourceSelection } from '@/components/pdf/source-panel'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/ui/icons'
import { MetricCard } from '@/components/ui/metric-card'
import { Notice } from '@/components/ui/notice'
import { Tabs } from '@/components/ui/tabs'
import { VerdictChip } from '@/components/ui/verdict-chip'
import { Tag } from '@/components/ui/tag'
import { API_BASE_URL, describeApiError } from '@/lib/api-client'
import {
  getBid,
  isAwaitingReview,
  isBidSettled,
  type BidResponse,
  type Verdict,
} from '@/lib/bids'
import { listDocuments } from '@/lib/documents'
import { formatLanguage, formatLanguagePair, plural } from '@/lib/format'
import { SHELL_MEDIA_QUERY, useMediaQuery } from '@/lib/use-media-query'
import { usePolling } from '@/lib/use-polling'
import { AskPanel } from './ask-panel'
import { BID_STATUS_LABELS } from './bid-status'
import { citationsOf, useBidChat } from './use-bid-chat'
import { VerdictPanel } from './verdict-panel'

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
 * **The desktop right column is the phone's tab set, minus Matrix (ADR-0060).** Source, Ask
 * and Verdict share one 400 px column under one `Tabs`, and the column is sticky, so all
 * three stay in reach while the matrix scrolls. This replaced a stacked column (Source, then
 * Ask beneath it) with the verdict rendered *after* the whole matrix: measured on the FR bid
 * at 1440×900 the page was 23 204 px tall, "Ask the tender" began at y=1 351 and the verdict
 * at y=13 876 — the product's one output, fifteen screens down. Now the decision is a line
 * under the header, the header's "Review verdict" opens the Verdict tab, and a citation in
 * an answer or a row switches the column to Source and lands on the page, exactly as the
 * phone's tab does. On the phone the tabs are as they were: Matrix / Source / Verdict / Ask,
 * a tap away. Chat state lives in `useBidChat` here rather than in the panel, so a
 * breakpoint change or a tab switch does not lose the exchanges made so far.
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

type PhoneTab = 'matrix' | 'source' | 'verdict' | 'ask'
/**
 * The desktop right column's segments: the phone's set minus Matrix, which on desktop is the
 * left column. Same vocabulary, same `Tabs`, so a bidder who learned the phone learns nothing
 * new on a laptop — and so the verdict is one click from the top of the page rather than
 * fifteen screens below it (ADR-0060).
 */
type SideTab = 'source' | 'ask' | 'verdict'

const PHONE_TABS: readonly { value: PhoneTab; label: string }[] = [
  { value: 'matrix', label: 'Matrix' },
  { value: 'source', label: 'Source' },
  { value: 'verdict', label: 'Verdict' },
  { value: 'ask', label: 'Ask' },
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
  const [sideTab, setSideTab] = useState<SideTab>('source')
  const announcement = useStatusAnnouncement(bid)
  const edits = useRowEdits(bid.matrix_rows)
  // Loaded once per bid and passed to both layouts and to the Ask panel, so thirty rows and
  // every chat answer share one request for the thumbs the bidder has already given (S4.6.3).
  const feedback = useRowFeedback(initial.id)
  const attachable = useAttachableDocuments(isAwaitingReview(bid))
  const chat = useBidChat(initial.id)

  const status = BID_STATUS_LABELS[bid.status]
  const isRunning = !isBidSettled(bid)
  const totalPages = bid.documents.reduce((sum, d) => sum + d.pages, 0)
  const unreadPages = bid.documents.reduce((sum, d) => sum + d.unread_pages.length, 0)
  const rowsByRequirement = useMemo(
    () => indexRowsByRequirement(bid.matrix_rows),
    [bid.matrix_rows]
  )
  // An answer may cite a company document no matrix row does; folding those in is what lets
  // its citation open the source panel rather than light up and go nowhere.
  const chatCitations = useMemo(() => citationsOf(chat.exchanges), [chat.exchanges])
  const sourceDocuments = useMemo(
    () => citableDocuments(bid.documents, bid.matrix_rows, chatCitations),
    [bid.documents, bid.matrix_rows, chatCitations]
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
      setSideTab('source')
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
  const sideTabs: readonly { readonly value: SideTab; readonly label: string }[] =
    bid.verdict === null
      ? [
          { value: 'source', label: 'Source' },
          { value: 'ask', label: 'Ask' },
        ]
      : [
          { value: 'source', label: 'Source' },
          { value: 'ask', label: 'Ask' },
          { value: 'verdict', label: 'Verdict' },
        ]
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
      // An anchor, not a button: the panel is on this page and the action is "take me to it",
      // so it should open in a new tab, be copyable, and move focus the way an anchor does.
      // `Button asChild` puts the primary variant's classes on the `Link`, so the enabled and
      // disabled states above are one control in one hue, and every colour it uses is a token
      // that exists. The hand-rolled class string this replaced named `bg-accent-default` and
      // `hover:bg-accent-strong`, which the `@theme` block never defines — and an unknown
      // colour under `--color-*: initial` emits nothing rather than failing, so the control
      // shipped as white text on a transparent ground (contrast 1.02:1). The icon is inline
      // because the `asChild` branch does not render the `icon` prop, as on `/bids`.
      <Button asChild className="hover:no-underline">
        <Link href="#verdict" onClick={() => setSideTab('verdict')}>
          <span className="inline-flex size-4">
            <Icon name="shield" size={16} />
          </span>
          Review verdict
        </Link>
      </Button>
    )

  const liveRegion = (
    <p role="status" aria-live="polite" className="sr-only">
      {announcement}
    </p>
  )
  const askPanel = (variant: 'panel' | 'phone') => (
    <AskPanel
      chat={chat}
      feedback={feedback}
      bidderLanguage={bid.bidder_language}
      activeCitation={activeCitation}
      onCite={handleCite}
      variant={variant}
    />
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
          {bid.verdict !== null && <DecisionLine bid={bid} verdict={bid.verdict} />}
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
              feedback={feedback}
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
          {/* Always mounted, unlike the source tab: there is no iframe to spare, and a
              half-typed question must survive a look at the page it is about. */}
          <div id="phone-panel-ask" role="tabpanel" hidden={phoneTab !== 'ask'}>
            {askPanel('phone')}
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
      {bid.verdict !== null && (
        <DecisionLine bid={bid} verdict={bid.verdict} className="mb-5" />
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
            feedback={feedback}
            isChecking={isRunning}
            activeCitation={activeCitation}
            onCite={handleCite}
            emptyMessage={emptyMessage}
            review={review}
          />
        </div>
        {/* Below `xl` the grid is one column, and this panel goes FIRST (`order-first`): a
            tabbed Source / Ask / Verdict under 144 rows would be the buried chat all over
            again, just with tabs on it. Sticky at `xl`, so Source, Ask and Verdict stay in view while the matrix scrolls: the
            measured page is 23 204 px tall and the column had left the screen by row 20.
            It scrolls internally when taller than the viewport rather than pushing the page. */}
        <div className="order-first flex min-w-0 flex-col gap-4 xl:order-none xl:sticky xl:top-4 xl:max-h-[calc(100dvh-2rem)] xl:overflow-y-auto">
          <Tabs
            items={sideTabs}
            value={sideTab}
            onChange={setSideTab}
            fullWidth
            aria-label="Workspace panels"
            panelId={(value) => `side-panel-${value}`}
          />
          {/* All three stay mounted and are hidden, not unmounted: the PDF keeps its page, a
              half-typed question survives a look at the source, and a half-written override
              reason survives a look at the page it is about. The phone unmounts Source to
              spare an iframe on a small device; a laptop has the memory. */}
          <div id="side-panel-source" role="tabpanel" hidden={sideTab !== 'source'}>
            <SourcePanel
              documents={sourceDocuments}
              selection={selection}
              onSelect={handleSelect}
            />
          </div>
          <div id="side-panel-ask" role="tabpanel" hidden={sideTab !== 'ask'}>
            {askPanel('panel')}
          </div>
          {bid.verdict !== null && (
            <div id="side-panel-verdict" role="tabpanel" hidden={sideTab !== 'verdict'}>
              <div id="verdict" className="scroll-mt-4">
                {verdictPanel}
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  )
}

/**
 * The decision, where the eye lands first — on both layouts. The full panel (gaps,
 * rationale, the reviewer's own decision) is one click or one tap away in the Verdict tab;
 * this line exists because the measured desktop page put that panel at y=13 876, and the
 * phone had nothing at all, above the fold that said what CrossBid had concluded (ADR-0060).
 *
 * The chip is qualified until a person has spoken: "· advisory" while `bid.decision` is
 * null, "· confirmed" after the review. Without the first word an unreviewed "No-go" read
 * as final at a glance, and the caveat that it was not lived in the Verdict tab — the very
 * tab a bidder who trusted the chip would not open.
 */
function DecisionLine({
  bid,
  verdict,
  className,
}: {
  readonly bid: BidResponse
  readonly verdict: Verdict
  readonly className?: string
}) {
  const isReviewed = bid.decision !== null
  return (
    <div
      className={cn(
        'flex flex-wrap items-center gap-3 rounded-[14px] border border-border-default bg-surface-card px-4 py-3 shadow-xs',
        className
      )}
    >
      <VerdictChip
        verdict={verdict.decision}
        size="lg"
        confirmed={isReviewed}
        advisory={!isReviewed}
      />
      <p className="m-0 [font:var(--type-body-sm)] text-text-secondary">
        <b className="font-semibold text-text-primary">
          {verdict.mandatory_supported} of {verdict.mandatory_total}
        </b>{' '}
        mandatory requirements supported · {plural(verdict.gaps.length, 'gap')}
        {isReviewed && ' · reviewed'}
      </p>
    </div>
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
