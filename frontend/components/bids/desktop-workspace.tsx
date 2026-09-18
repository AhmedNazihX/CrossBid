/**
 * `Main.dc.html` at 900 px and above: the matrix on the left, one 400 px sticky column of
 * Source / Ask / Verdict on the right (ADR-0060).
 *
 * Split out of `bid-workspace.tsx` with the phone layout beside it (audit M23). The markup is
 * unchanged; what it draws now arrives as `WorkspaceState` rather than being computed above
 * it.
 */
'use client'

import Link from 'next/link'

import { Breadcrumb } from '@/components/layout/breadcrumb'
import { PageHeader } from '@/components/layout/page-header'
import { MatrixSummary } from '@/components/matrix/matrix-summary'
import { RequirementList } from '@/components/matrix/requirement-list'
import { SourcePanel } from '@/components/pdf/source-panel'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/ui/icons'
import { MetricCard } from '@/components/ui/metric-card'
import { Notice } from '@/components/ui/notice'
import { tabId, Tabs } from '@/components/ui/tabs'
import { useRouter } from 'next/navigation'
import { Tag } from '@/components/ui/tag'
import { describeApiError } from '@/lib/api-client'
import { formatLanguage, formatLanguagePair, plural } from '@/lib/format'
import { AskPanel } from './ask-panel'
import { DecisionLine } from './decision-line'
import { DeleteBid } from './delete-bid'
import { RunLiveness } from './run-liveness'
import { UnsearchablePack } from './unsearchable-pack'
import { VerdictPanel } from './verdict-panel'
import type { SideTab, WorkspaceState } from './workspace-state'

/** One namespace for the right-hand column: the panel's id, and the tab's derived from it. */
const sidePanelId = (value: SideTab): string => `side-panel-${value}`

export function DesktopWorkspace({ state }: { readonly state: WorkspaceState }) {
  // The bid stops existing when it is deleted, and the workspace polls it — so leaving is
  // part of the delete rather than something the bidder is left to do.
  const router = useRouter()
  const {
    bid,
    pollError,
    selection,
    activeCitation,
    sideTab,
    setSideTab,
    announcement,
    edits,
    feedback,
    chat,
    status,
    isRunning,
    totalPages,
    unreadPages,
    rowsByRequirement,
    sourceDocuments,
    hasRows,
    review,
    handleCite,
    handleSelect,
    onReviewed,
    emptyMessage,
    reviewNote,
  } = state

  const verdictPanel = (
    <VerdictPanel
      bid={bid}
      rowEdits={edits.edits}
      blockedRowCount={edits.blockers.length}
      onReviewed={onReviewed}
      onBackToMatrix={undefined}
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
          <span className="font-medium text-text-primary">{status.label}.</span> {status.hint}{' '}
          <RunLiveness startedAt={bid.created_at} />
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
      <UnsearchablePack documents={bid.documents} />
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
            panelId={sidePanelId}
          />
          {/* All three stay mounted and are hidden, not unmounted: the PDF keeps its page, a
              half-typed question survives a look at the source, and a half-written override
              reason survives a look at the page it is about. The phone unmounts Source to
              spare an iframe on a small device; a laptop has the memory. */}
          <div
            id={sidePanelId('source')}
            role="tabpanel"
            aria-labelledby={tabId(sidePanelId('source'))}
            hidden={sideTab !== 'source'}
          >
            <SourcePanel
              documents={sourceDocuments}
              selection={selection}
              onSelect={handleSelect}
            />
          </div>
          <div
            id={sidePanelId('ask')}
            role="tabpanel"
            aria-labelledby={tabId(sidePanelId('ask'))}
            hidden={sideTab !== 'ask'}
          >
            {askPanel('panel')}
          </div>
          {bid.verdict !== null && (
            <div
              id={sidePanelId('verdict')}
              role="tabpanel"
              aria-labelledby={tabId(sidePanelId('verdict'))}
              hidden={sideTab !== 'verdict'}
            >
              <div id="verdict" className="scroll-mt-4">
                {verdictPanel}
              </div>
            </div>
          )}
        </div>
      </div>
      <div className="mt-8 border-t border-border-subtle pt-5">
        {/* At the foot, away from Review verdict: a destructive action beside the primary one
            is a misclick waiting to happen, and this is not a step in the workflow. */}
        <DeleteBid
          bidId={bid.id}
          title={bid.notice_number ?? bid.title}
          onDeleted={() => router.replace('/bids')}
        />
      </div>
    </>
  )
}
