'use client'

import { useId, useState } from 'react'
import { cn } from 'cn'

import { DataTable, Td, Th, Tr } from '@/components/ui/data-table'
import { Icon } from '@/components/ui/icons'
import { Tabs } from '@/components/ui/tabs'
import { Tag } from '@/components/ui/tag'
import type { BidDocument, ExtractionProblem, MatrixRow, Requirement } from '@/lib/bids'
import { formatLanguage, requirementLabel } from '@/lib/format'
import { CitationLink } from './citation-link'
import { isSameCitation, type Citation } from './citation'
import { describeProblems } from './problems'
import { RequirementDetail } from './requirement-detail'
import { RowStatusBadge } from './row-status-badge'
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
  /** `true` while the run is still in flight, so a missing row means "not yet", not "never". */
  readonly isChecking: boolean
  readonly activeCitation: Citation | undefined
  readonly onCite: (citation: Citation) => void
  /** Rendered inside the table area while there is nothing to list yet. */
  readonly emptyMessage: React.ReactNode
}

/**
 * The requirement table of `Main.dc.html` (stories S4.5.1 and S3.3.1): ID tag in the
 * citation face, category, the requirement explained in the bidder's language, the citation
 * that jumps the source panel to its page, and the Evidence column carrying the row's status
 * in the fixed vocabulary. Expanding a row opens `RequirementDetail` — the tender's words on
 * the left, the check's evidence and the eCertis card on the right. Category tabs filter; the
 * footer line names what the run could not do.
 *
 * Read-only: S4.5.2 adds the artboard's Confirm / Change status / Add evidence controls.
 */
export function RequirementList({
  requirements,
  rowsByRequirement,
  problems,
  documents,
  bidderLanguage,
  isChecking,
  activeCitation,
  onCite,
  emptyMessage,
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
    ...problemLines,
  ].join(' · ')

  return (
    <div className="flex flex-col gap-3.5">
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
              <Th className="min-w-[180px]">
                Requirement (explained in {formatLanguage(bidderLanguage)})
              </Th>
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
}: RequirementRowProps) {
  const detailId = `${requirement.id}-detail`
  const citation: Citation = { documentName: requirement.document_name, page: requirement.page }
  const explained = requirement.translation ?? requirement.source_text
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
            className={cn(
              'flex w-full items-start gap-2 rounded-sm text-left text-base leading-[1.4] text-text-primary hover:underline',
              !isExpanded && 'items-center'
            )}
          >
            <span className={cn('min-w-0 flex-1', !isExpanded && 'truncate')}>{explained}</span>
            <Icon
              name="chev"
              size={14}
              className={cn(
                'mt-[3px] text-text-muted transition-transform',
                isExpanded && 'rotate-180'
              )}
            />
          </button>
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
            <RowStatusBadge status={row.status} />
          )}
        </Td>
      </Tr>
      <Tr hidden={!isExpanded} id={detailId} className={cn(isExpanded && 'bg-surface-sunken')}>
        <Td colSpan={5} className="pt-0 pb-[18px]">
          <RequirementDetail
            requirement={requirement}
            row={row}
            isChecking={isChecking}
            activeCitation={activeCitation}
            onCite={onCite}
          />
        </Td>
      </Tr>
    </>
  )
}
