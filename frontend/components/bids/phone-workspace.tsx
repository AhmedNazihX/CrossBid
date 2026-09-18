/**
 * `WorkspacePhone.dc.html` below 900 px: the header, four tabs, and a sticky Review button.
 *
 * Split out of `bid-workspace.tsx` with the desktop layout beside it (audit M23) — one
 * component held both, and the busiest screen in the product was the only god component in
 * the tree. The markup is unchanged; what it draws now arrives as `WorkspaceState` rather
 * than being computed above it.
 */
'use client'

import { RequirementCards } from '@/components/matrix/requirement-cards'
import { MatrixSummary } from '@/components/matrix/matrix-summary'
import { SourcePanel } from '@/components/pdf/source-panel'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/ui/icons'
import { Notice } from '@/components/ui/notice'
import { tabId, Tabs } from '@/components/ui/tabs'
import { useRouter } from 'next/navigation'
import { describeApiError } from '@/lib/api-client'
import { formatLanguagePair, plural } from '@/lib/format'
import { AskPanel } from './ask-panel'
import { DecisionLine } from './decision-line'
import { VerdictPanel } from './verdict-panel'
import { DeleteBid } from './delete-bid'
import { RunLiveness } from './run-liveness'
import { UnsearchablePack } from './unsearchable-pack'
import { PHONE_TABS, type PhoneTab, type WorkspaceState } from './workspace-state'

/** One namespace for the phone's sections: the panel's id, and the tab's derived from it. */
const phonePanelId = (value: PhoneTab): string => `phone-panel-${value}`

export function PhoneWorkspace({ state }: { readonly state: WorkspaceState }) {
  const router = useRouter()
  const {
    bid,
    pollError,
    selection,
    activeCitation,
    phoneTab,
    setPhoneTab,
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
    showVerdict,
    backToMatrix,
    emptyMessage,
    reviewNote,
  } = state

  const verdictPanel = (
    <VerdictPanel
      bid={bid}
      rowEdits={edits.edits}
      blockedRowCount={edits.blockers.length}
      onReviewed={onReviewed}
      onBackToMatrix={backToMatrix}
    />
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
          {isRunning && (
            <>
              {' · '}
              <RunLiveness startedAt={bid.created_at} />
            </>
          )}
        </p>
        {bid.verdict !== null && <DecisionLine bid={bid} verdict={bid.verdict} />}
        {bid.status === 'failed' && bid.failure_reason !== null && (
          <Notice tone="danger" title="The run stopped">
            {bid.failure_reason}
          </Notice>
        )}
        <UnsearchablePack documents={bid.documents} />
        <Tabs
          items={PHONE_TABS}
          value={phoneTab}
          onChange={setPhoneTab}
          size="lg"
          fullWidth
          aria-label="Workspace sections"
          panelId={phonePanelId}
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
        <div
          id={phonePanelId('matrix')}
          role="tabpanel"
          aria-labelledby={tabId(phonePanelId('matrix'))}
          hidden={phoneTab !== 'matrix'}
        >
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
        <div
          id={phonePanelId('source')}
          role="tabpanel"
          aria-labelledby={tabId(phonePanelId('source'))}
          hidden={phoneTab !== 'source'}
        >
          {phoneTab === 'source' && (
            <SourcePanel
              documents={sourceDocuments}
              selection={selection}
              onSelect={handleSelect}
              variant="phone"
            />
          )}
        </div>
        <div
          id={phonePanelId('verdict')}
          role="tabpanel"
          aria-labelledby={tabId(phonePanelId('verdict'))}
          hidden={phoneTab !== 'verdict'}
        >
          {phoneTab === 'verdict' && verdictPanel}
        </div>
        {/* Always mounted, unlike the source tab: there is no iframe to spare, and a
              half-typed question must survive a look at the page it is about. */}
        <div
          id={phonePanelId('ask')}
          role="tabpanel"
          aria-labelledby={tabId(phonePanelId('ask'))}
          hidden={phoneTab !== 'ask'}
        >
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
      <div className="mx-4 mb-6 mt-2 border-t border-border-subtle pt-5">
        {/* At the foot, away from Review verdict: a destructive action beside the primary one
            is a misclick waiting to happen, and this is not a step in the workflow. */}
        <DeleteBid
          bidId={bid.id}
          title={bid.notice_number ?? bid.title}
          onDeleted={() => router.replace('/bids')}
        />
      </div>
    </div>
  )
}
