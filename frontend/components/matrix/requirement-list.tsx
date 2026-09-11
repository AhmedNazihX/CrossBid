'use client'

import { useId, useState } from 'react'
import { cn } from 'cn'

import { DataTable, Td, Th, Tr } from '@/components/ui/data-table'
import { Eyebrow } from '@/components/ui/eyebrow'
import { Icon } from '@/components/ui/icons'
import { Tabs } from '@/components/ui/tabs'
import { Tag } from '@/components/ui/tag'
import type { BidDocument, ExtractionProblem, Requirement } from '@/lib/bids'
import { formatLanguage, requirementLabel } from '@/lib/format'
import { CitationLink } from './citation-link'
import { isSameCitation, type Citation } from './citation'
import { describeProblems } from './problems'
import {
  CATEGORY_LABELS,
  CATEGORY_ORDER,
  CHECKABILITY_LABELS,
  countByCategory,
  describeThreshold,
  KIND_LABELS,
  STAGE_LABELS,
  type CategoryFilter,
} from './requirement-labels'

export interface RequirementListProps {
  readonly requirements: readonly Requirement[]
  readonly problems: readonly ExtractionProblem[]
  readonly documents: readonly BidDocument[]
  readonly bidderLanguage: string
  readonly activeCitation: Citation | undefined
  readonly onCite: (citation: Citation) => void
  /** Rendered inside the table area while there is nothing to list yet. */
  readonly emptyMessage: React.ReactNode
}

/**
 * The requirement table of `Main.dc.html` (story S4.5.1, Increment 1): ID tag in the
 * citation face, category, the requirement explained in the bidder's language with the
 * source quote on expand, the citation that jumps the source panel to its page, and the
 * Evidence column — which says "Checked in Increment 2" rather than showing a status the
 * run has not produced. Category tabs filter; the footer line names what the run could not
 * do.
 */
export function RequirementList({
  requirements,
  problems,
  documents,
  bidderLanguage,
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
          caption="Requirements extracted from the tender, each cited to a page."
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
              <Th className="w-[124px]">Evidence</Th>
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
  readonly label: string
  readonly isExpanded: boolean
  readonly onToggle: () => void
  readonly activeCitation: Citation | undefined
  readonly onCite: (citation: Citation) => void
  readonly showDocument: boolean
}

function RequirementRow({
  requirement,
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
        <Td className="text-[13px] leading-[1.4] text-text-muted">Checked in Increment 2</Td>
      </Tr>
      <Tr hidden={!isExpanded} id={detailId} className={cn(isExpanded && 'bg-surface-sunken')}>
        <Td colSpan={5} className="pt-0 pb-[18px]">
          <div className="grid gap-5 shell:grid-cols-2 shell:pl-[116px]">
            <div>
              <Eyebrow className="mb-1.5">
                Source ({formatLanguage(requirement.source_lang)})
              </Eyebrow>
              <p className="m-0 mb-1.5 [font:var(--type-mono)] text-text-muted">
                {requirement.document_name} p. {requirement.page}
              </p>
              <blockquote
                lang={requirement.source_lang}
                className="m-0 text-base leading-[1.5] text-text-secondary italic"
              >
                &ldquo;{requirement.source_text}&rdquo;
              </blockquote>
            </div>
            <div>
              <Eyebrow className="mb-1.5">About this requirement</Eyebrow>
              <dl className="m-0 grid grid-cols-[max-content_minmax(0,1fr)] gap-x-3 gap-y-1 text-base leading-[1.5]">
                <dt className="text-text-muted">Weight</dt>
                <dd className="m-0">{KIND_LABELS[requirement.kind]}</dd>
                <dt className="text-text-muted">Stage</dt>
                <dd className="m-0">{STAGE_LABELS[requirement.stage]}</dd>
                <dt className="text-text-muted">Evidence</dt>
                <dd className="m-0">{CHECKABILITY_LABELS[requirement.checkable]}</dd>
                {requirement.threshold !== null && requirement.threshold !== undefined && (
                  <>
                    <dt className="text-text-muted">Threshold</dt>
                    <dd className="m-0">{describeThreshold(requirement.threshold)}</dd>
                  </>
                )}
                {requirement.deadline !== null && requirement.deadline !== undefined && (
                  <>
                    <dt className="text-text-muted">Deadline</dt>
                    <dd className="m-0">{requirement.deadline}</dd>
                  </>
                )}
                {requirement.ecertis_criterion_id !== null &&
                  requirement.ecertis_criterion_id !== undefined && (
                    <>
                      <dt className="text-text-muted">eCertis</dt>
                      <dd className="m-0">
                        Mapped to an ESPD criterion — the German evidence card arrives in
                        Increment 2
                      </dd>
                    </>
                  )}
              </dl>
            </div>
          </div>
        </Td>
      </Tr>
    </>
  )
}
