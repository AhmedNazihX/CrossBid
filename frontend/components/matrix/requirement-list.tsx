'use client'

import { useId, useState } from 'react'
import { cn } from 'cn'

import { DataTable, Td, Th, Tr } from '@/components/ui/data-table'
import { Icon } from '@/components/ui/icons'
import { Notice } from '@/components/ui/notice'
import { Tabs } from '@/components/ui/tabs'
import { Tag } from '@/components/ui/tag'
import type { BidDocument, ExtractionProblem, MatrixRow, Requirement } from '@/lib/bids'
import { formatLanguage, requirementLabel } from '@/lib/format'
import { CitationLink } from './citation-link'
import { isSameCitation, type Citation } from './citation'
import { describeProblems } from './problems'
import {
  isSwitchable,
  RequirementLanguageToggle,
  requirementTextIn,
  type RequirementLanguage,
} from './requirement-language'
import { RequirementDetail } from './requirement-detail'
import type { RowReview } from './row-review-controls'
import type { RowFeedbackController } from './use-row-feedback'
import { RowStatusChange } from './row-status-change'
import {
  CATEGORY_LABELS,
  CATEGORY_ORDER,
  countByCategory,
  type CategoryFilter,
} from './requirement-labels'

export interface RequirementListProps {
  readonly requirements: readonly Requirement[]
  /** The matrix row answering each requirement, keyed by requirement id; grows per poll. */
  readonly rowsByRequirement: ReadonlyMap<string, MatrixRow>
  readonly problems: readonly ExtractionProblem[]
  readonly documents: readonly BidDocument[]
  readonly bidderLanguage: string
  /** The bidder's thumbs on this bid, for the rating control under each row (S4.6.3). */
  readonly feedback: RowFeedbackController
  /** `true` while the run is still in flight, so a missing row means "not yet", not "never". */
  readonly isChecking: boolean
  readonly activeCitation: Citation | undefined
  readonly onCite: (citation: Citation) => void
  /** Rendered inside the table area while there is nothing to list yet. */
  readonly emptyMessage: React.ReactNode
  /**
   * The reviewer's pending edits and the documents they may attach (S4.5.2). Absent while
   * the bid is not parked at its interrupt, which leaves the table exactly as S4.5.1 built it.
   */
  readonly review?: RowReview
}

/**
 * The requirement table of `Main.dc.html` (stories S4.5.1 and S3.3.1): ID tag in the
 * citation face, category, the requirement explained in the bidder's language, the citation
 * that jumps the source panel to its page, and the Evidence column carrying the row's status
 * in the fixed vocabulary. Expanding a row opens `RequirementDetail` — the tender's words on
 * the left, the check's evidence and the eCertis card on the right. Category tabs filter; the
 * footer line names what the run could not do.
 *
 * With a `review` the Evidence column also carries the reviewer's pending status beside the
 * agent's, and every expanded row gains the artboard's Confirm / Change status / Add evidence
 * controls (S4.5.2). What the run could not do is a notice above the table rather than a word
 * in the footer: unread pages and dropped rows are the reviewer's problem to act on, and a
 * footer is where a count goes to be skipped.
 *
 * **Deviation from `Main.dc.html`, recorded per ADR-0014: a collapsed row wraps its
 * requirement instead of clipping it to one line.** The artboard draws the requirement cell
 * `white-space: nowrap; text-overflow: ellipsis` over a `minmax(0, 1fr)` column — in a
 * table that had the page to itself. Since ADR-0060 put a 400 px column beside it, the table
 * measures 649 px at 1440×900, the four fixed columns (92 + 88 + 152 + 152) take 484 px, and
 * the requirement column has 165 px: an 88-character German sentence clipped to "Die
 * Angebote mü…", so a reviewer had to expand every one of 144 rows to read the thing the
 * product extracted. Nothing can be reclaimed from the fixed columns — measured content is
 * 133 px in Source and 128 px in Evidence — so the honest fix is height: the sentence
 * wraps, the row grows, and the chevron stays on the first line. The header over that
 * column wraps too (`Th wrap`): at 194 px it was drawn across "Source".
 */
export function RequirementList({
  requirements,
  rowsByRequirement,
  problems,
  documents,
  bidderLanguage,
  feedback,
  isChecking,
  activeCitation,
  onCite,
  emptyMessage,
  review,
}: RequirementListProps) {
  const [filter, setFilter] = useState<CategoryFilter>('all')
  const [expandedId, setExpandedId] = useState<string | undefined>(undefined)
  const panelId = useId()

  const counts = countByCategory(requirements)
  const tabs = [
    { value: 'all' as const, label: 'All requirements', count: requirements.length },
    ...CATEGORY_ORDER.filter((category) => (counts.get(category) ?? 0) > 0).map((category) => ({
      value: category,
      label: CATEGORY_LABELS[category],
      count: counts.get(category) ?? 0,
    })),
  ]
  const indexed = requirements.map((requirement, index) => ({ requirement, index }))
  const shown =
    filter === 'all'
      ? indexed
      : indexed.filter(({ requirement }) => requirement.category === filter)
  const problemLines = describeProblems(problems, documents)
  const footer = [
    `Showing ${shown.length} of ${requirements.length}`,
    'every line links to its page in the tender',
  ].join(' · ')

  return (
    <div className="flex flex-col gap-3.5">
      {problemLines.length > 0 && (
        <Notice title="What the run could not read">
          <ul className="m-0 mt-1 list-disc pl-4">
            {problemLines.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </Notice>
      )}
      <Tabs
        items={tabs}
        value={filter}
        onChange={setFilter}
        variant="underline"
        aria-label="Filter requirements by category"
        panelId={() => panelId}
        className="flex-wrap gap-y-0"
      />
      <div
        id={panelId}
        role="tabpanel"
        aria-label={`${tabs.find((t) => t.value === filter)?.label ?? 'All requirements'}`}
      >
        <DataTable
          caption="Requirements extracted from the tender, each cited to a page, with what the check found."
          footer={requirements.length > 0 ? footer : undefined}
          className="table-fixed [&_td]:px-3 [&_th]:px-3"
        >
          <thead>
            <tr>
              <Th className="w-[92px]">ID</Th>
              <Th className="w-[88px]">Category</Th>
              {/* No width: under `table-fixed` the column without one takes what the fixed
                  columns leave, which is what the artboard's `minmax(0, 1fr)` meant. */}
              <Th wrap>Requirement (explained in {formatLanguage(bidderLanguage)})</Th>
              <Th className={documents.length > 1 ? 'w-[152px]' : 'w-[88px]'}>Source</Th>
              <Th className="w-[152px]">Evidence</Th>
            </tr>
          </thead>
          <tbody>
            {shown.length === 0 && (
              <Tr>
                <Td colSpan={5} className="py-6 text-text-secondary">
                  {requirements.length === 0
                    ? emptyMessage
                    : 'No requirements in this category.'}
                </Td>
              </Tr>
            )}
            {shown.map(({ requirement, index }) => (
              <RequirementRow
                key={requirement.id}
                requirement={requirement}
                row={rowsByRequirement.get(requirement.id)}
                isChecking={isChecking}
                label={requirementLabel(index)}
                isExpanded={expandedId === requirement.id}
                onToggle={() =>
                  setExpandedId((current) =>
                    current === requirement.id ? undefined : requirement.id
                  )
                }
                activeCitation={activeCitation}
                onCite={onCite}
                showDocument={documents.length > 1}
                bidderLanguage={bidderLanguage}
                feedback={feedback}
                review={review}
              />
            ))}
          </tbody>
        </DataTable>
      </div>
    </div>
  )
}

interface RequirementRowProps {
  readonly requirement: Requirement
  readonly row: MatrixRow | undefined
  readonly isChecking: boolean
  readonly label: string
  readonly isExpanded: boolean
  readonly onToggle: () => void
  readonly activeCitation: Citation | undefined
  readonly onCite: (citation: Citation) => void
  readonly showDocument: boolean
  readonly bidderLanguage: string
  readonly feedback: RowFeedbackController
  readonly review?: RowReview
}

function RequirementRow({
  requirement,
  row,
  isChecking,
  label,
  isExpanded,
  onToggle,
  activeCitation,
  onCite,
  showDocument,
  bidderLanguage,
  feedback,
  review,
}: RequirementRowProps) {
  const [language, setLanguage] = useState<RequirementLanguage>('bidder')
  const detailId = `${requirement.id}-detail`
  const citation: Citation = {
    documentName: requirement.document_name,
    page: requirement.page ?? null,
    criterionId: requirement.ecertis_criterion_id ?? undefined,
  }
  const explained = requirementTextIn(requirement, language)
  const canSwitch = isSwitchable(requirement, bidderLanguage)
  const isTranslated = requirement.translation !== null && requirement.translation !== undefined

  return (
    <>
      <Tr className={cn(isExpanded && 'border-b-0 bg-surface-sunken')}>
        <Td>
          <Tag mono className="whitespace-nowrap">
            {label}
          </Tag>
        </Td>
        <Td className="text-text-secondary">{CATEGORY_LABELS[requirement.category]}</Td>
        <Td>
          <button
            type="button"
            onClick={onToggle}
            aria-expanded={isExpanded}
            aria-controls={detailId}
            className="flex w-full items-start gap-2 rounded-sm text-left text-base leading-[1.4] text-text-primary hover:underline"
          >
            <span
              lang={language === 'source' ? requirement.source_lang : bidderLanguage}
              className="min-w-0 flex-1 [overflow-wrap:anywhere]"
            >
              {explained}
            </span>
            <Icon
              name="chev"
              size={14}
              className={cn(
                'mt-[3px] text-text-muted transition-transform',
                isExpanded && 'rotate-180'
              )}
            />
          </button>
          {canSwitch && (
            <RequirementLanguageToggle
              requirement={requirement}
              bidderLanguage={bidderLanguage}
              value={language}
              onChange={setLanguage}
              className="mt-1.5"
            />
          )}
          {!isTranslated && (
            <span className="mt-1 block [font:var(--type-body-sm)] text-text-muted">
              Not yet translated — shown in the tender&rsquo;s language
            </span>
          )}
        </Td>
        <Td>
          <CitationLink
            citation={citation}
            isActive={isSameCitation(activeCitation, citation)}
            onCite={onCite}
            showDocument={showDocument}
          />
        </Td>
        <Td>
          {row === undefined ? (
            <span className="text-[13px] leading-[1.4] text-text-muted">
              {isChecking ? 'Checking…' : 'Not checked'}
            </span>
          ) : (
            <RowStatusChange
              row={row}
              pending={review?.edits.editOf(row.id)?.status}
              isConfirmed={review?.edits.isConfirmed(row.id) ?? false}
            />
          )}
        </Td>
      </Tr>
      <Tr hidden={!isExpanded} id={detailId} className={cn(isExpanded && 'bg-surface-sunken')}>
        <Td colSpan={5} className="pt-0 pb-[18px]">
          <RequirementDetail
            requirement={requirement}
            row={row}
            isChecking={isChecking}
            feedback={feedback}
            activeCitation={activeCitation}
            onCite={onCite}
            review={review}
          />
        </Td>
      </Tr>
    </>
  )
}
