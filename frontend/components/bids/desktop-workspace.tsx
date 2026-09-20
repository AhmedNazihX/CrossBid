/**
 * The bid workspace at 900 px and above: the matrix on the left under "Ask the tender", the
 * verdict alone in a sticky right rail, and the source page as a drawer over both (ADR-0104).
 *
 * **What this deviates from, and what sanctions it.** `Main.dc.html` draws the matrix beside a
 * permanent 400 px source column and puts the verdict on its own screen, `Verdict.dc.html`.
 * ADR-0060 collapsed all three — Source, Ask and Verdict — into one tabbed 400 px column,
 * which fixed a real measured problem (the verdict had been fifteen screens down) by making
 * three unrelated things compete for one column. The drawing this layout follows instead is
 * `Landing.dc.html`'s `ProductFrame`, the hero mock, which has always shown requirement rows
 * on the left and the recommendation and review cards alone on the right.
 *
 * **ADR-0060's guarantee is kept, and strengthened.** Its finding was that the product's one
 * output must be above the fold. A rail that only ever holds the verdict is stronger than a
 * tab that holds it one click away: there is no state of this page in which the verdict is
 * not on screen. The rail is never empty either — before the run writes a verdict it says so,
 * so the two-column shape does not appear halfway through a run.
 *
 * **A citation still lands on its page in one click**, which is the other thing ADR-0060
 * bought. `handleCite` opens the drawer rather than selecting a tab, and the drawer gets most
 * of the window instead of 400 px of it.
 *
 * Split out of `bid-workspace.tsx` with the phone layout beside it (audit M23); what it draws
 * arrives as `WorkspaceState` rather than being computed here.
 */
'use client'

import Link from 'next/link'

import { Breadcrumb } from '@/components/layout/breadcrumb'
import { PageHeader } from '@/components/layout/page-header'
import { MatrixSummary } from '@/components/matrix/matrix-summary'
import { RequirementList } from '@/components/matrix/requirement-list'
import { SourceDrawer } from '@/components/pdf/source-drawer'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Icon } from '@/components/ui/icons'
import { MetricCard } from '@/components/ui/metric-card'
import { Notice } from '@/components/ui/notice'
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
import type { WorkspaceState } from './workspace-state'

export function DesktopWorkspace({ state }: { readonly state: WorkspaceState }) {
  // The bid stops existing when it is deleted, and the workspace polls it — so leaving is
  // part of the delete rather than something the bidder is left to do.
  const router = useRouter()
  const {
    bid,
    pollError,
    selection,
    activeCitation,
    isSourceOpen,
    setSourceOpen,
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
      // Since ADR-0104 it carries no click handler: the rail it points at is already on
      // screen, so the anchor only has to move focus there.
      <Button asChild className="hover:no-underline">
        <Link href="#verdict">
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
      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="flex min-w-0 flex-col gap-4">
          {/* Above the matrix, not in a side column: ADR-0060 found the chat below the fold
              and moved it into a tab, which put it behind a click instead. Here it is the
              first thing under the metrics, and its `banner` variant is the one that bounds
              its own log so a long conversation cannot push the rows off the screen. */}
          <AskPanel
            chat={chat}
            feedback={feedback}
            bidderLanguage={bid.bidder_language}
            activeCitation={activeCitation}
            onCite={handleCite}
            variant="banner"
          />
          <div className="flex flex-wrap items-center gap-3">
            {hasRows && (
              <MatrixSummary
                rows={bid.matrix_rows}
                requirementCount={bid.requirements.length}
                isChecking={isRunning}
                className="min-w-0 flex-1"
              />
            )}
            {/* The drawer's other way in. A citation opens it on the page it cites; this
                opens it on whatever was last looked at, for a bidder who wants to read the
                pack rather than check a line. */}
            {sourceDocuments.length > 0 && (
              <Button
                variant="secondary"
                size="sm"
                icon={<Icon name="file" size={16} />}
                onClick={() => setSourceOpen(true)}
              >
                Open the pack
              </Button>
            )}
          </div>
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
        {/* The rail is the verdict and nothing else. Sticky at `xl`, scrolling internally
            when taller than the viewport rather than pushing the page: the measured page is
            23 204 px tall and a non-sticky column had left the screen by row 20 (ADR-0060).
            Below `xl` the grid is one column and the rail follows the matrix, which is the
            right order once it is no longer carrying the chat and the source with it. */}
        <div className="flex min-w-0 flex-col gap-4 xl:sticky xl:top-4 xl:max-h-[calc(100dvh-2rem)] xl:overflow-y-auto">
          <div id="verdict" className="scroll-mt-4">
            {bid.verdict !== null ? (
              <VerdictPanel
                bid={bid}
                rowEdits={edits.edits}
                blockedRowCount={edits.blockers.length}
                onReviewed={onReviewed}
                onBackToMatrix={undefined}
              />
            ) : (
              <Card title="Verdict" icon={<Icon name="shield" size={20} />} padding={20}>
                <p className="m-0 [font:var(--type-body-sm)] text-text-secondary">
                  {reviewNote}
                </p>
              </Card>
            )}
          </div>
        </div>
      </div>
      <SourceDrawer
        documents={sourceDocuments}
        selection={selection}
        onSelect={handleSelect}
        activeCitation={activeCitation}
        isOpen={isSourceOpen}
        onOpenChange={setSourceOpen}
      />
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
