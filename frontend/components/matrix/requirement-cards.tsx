'use client'

import { useState } from 'react'
import { cn } from 'cn'

import { Eyebrow } from '@/components/ui/eyebrow'
import { Icon } from '@/components/ui/icons'
import { Tag } from '@/components/ui/tag'
import type { MatrixRow, Requirement } from '@/lib/bids'
import { requirementLabel } from '@/lib/format'
import { CitationLink } from './citation-link'
import { isSameCitation, type Citation } from './citation'
import { CATEGORY_LABELS, CATEGORY_ORDER } from './requirement-labels'
import { RowEvidence } from './row-evidence'
import { RowStatusBadge } from './row-status-badge'

export interface RequirementCardsProps {
  readonly requirements: readonly Requirement[]
  readonly rowsByRequirement: ReadonlyMap<string, MatrixRow>
  readonly isChecking: boolean
  readonly activeCitation: Citation | undefined
  readonly onCite: (citation: Citation) => void
  readonly emptyMessage: React.ReactNode
}

/**
 * The phone's requirement cards (`WorkspacePhone.dc.html`): grouped under an eyebrow per
 * category with its count; each card a white 12 px-radius tile headed by the row's status
 * badge, with the requirement id and its citation, the requirement explained, and the
 * agent's one sentence underneath — the artboard's evidence line. Expanding a card shows the
 * cited passages and the eCertis card. Every tap target is at least 44 px.
 */
export function RequirementCards({
  requirements,
  rowsByRequirement,
  isChecking,
  activeCitation,
  onCite,
  emptyMessage,
}: RequirementCardsProps) {
  if (requirements.length === 0) {
    return <div className="text-text-secondary">{emptyMessage}</div>
  }
  const indexed = requirements.map((requirement, index) => ({ requirement, index }))
  return (
    <div className="flex flex-col gap-2.5">
      {CATEGORY_ORDER.map((category) => {
        const group = indexed.filter(({ requirement }) => requirement.category === category)
        if (group.length === 0) {
          return null
        }
        return (
          <section
            key={category}
            aria-labelledby={`group-${category}`}
            className="flex flex-col gap-2.5"
          >
            <Eyebrow id={`group-${category}`} className="pt-1">
              {CATEGORY_LABELS[category]} · {group.length}
            </Eyebrow>
            {group.map(({ requirement, index }) => (
              <RequirementCard
                key={requirement.id}
                requirement={requirement}
                row={rowsByRequirement.get(requirement.id)}
                isChecking={isChecking}
                label={requirementLabel(index)}
                activeCitation={activeCitation}
                onCite={onCite}
              />
            ))}
          </section>
        )
      })}
    </div>
  )
}

interface RequirementCardProps {
  readonly requirement: Requirement
  readonly row: MatrixRow | undefined
  readonly isChecking: boolean
  readonly label: string
  readonly activeCitation: Citation | undefined
  readonly onCite: (citation: Citation) => void
}

function RequirementCard({
  requirement,
  row,
  isChecking,
  label,
  activeCitation,
  onCite,
}: RequirementCardProps) {
  const [isExpanded, setExpanded] = useState(false)
  const detailId = `${requirement.id}-evidence`
  const citation: Citation = {
    documentName: requirement.document_name,
    page: requirement.page ?? null,
    criterionId: requirement.ecertis_criterion_id ?? undefined,
  }
  return (
    <article className="flex flex-col gap-2 rounded-lg border border-border-default bg-surface-card px-4 py-3.5 shadow-xs">
      {row === undefined ? (
        <span className="[font:var(--type-body-sm)] text-text-muted">
          {isChecking ? 'Checking…' : 'Not checked'}
        </span>
      ) : (
        <RowStatusBadge status={row.status} className="self-start" />
      )}
      <div className="flex flex-wrap items-center justify-between gap-x-2">
        <Tag mono>{label}</Tag>
        <CitationLink
          citation={citation}
          isActive={isSameCitation(activeCitation, citation)}
          onCite={onCite}
          className="min-h-11"
        />
      </div>
      <p className="m-0 text-base leading-[1.45] text-text-primary">
        {requirement.translation ?? requirement.source_text}
      </p>
      {row !== undefined && (
        <>
          <p className="m-0 [font:var(--type-body-sm)] text-text-secondary">
            {row.agent_rationale}
          </p>
          <button
            type="button"
            onClick={() => setExpanded((current) => !current)}
            aria-expanded={isExpanded}
            aria-controls={detailId}
            className="-mx-1 inline-flex min-h-11 items-center gap-1.5 self-start rounded-sm px-1 text-[13px] font-medium text-text-secondary"
          >
            {isExpanded ? 'Hide evidence' : 'Show evidence'}
            <Icon
              name="chev"
              size={14}
              className={cn('transition-transform', isExpanded && 'rotate-180')}
            />
          </button>
          <div id={detailId} hidden={!isExpanded}>
            <RowEvidence
              row={row}
              activeCitation={activeCitation}
              onCite={onCite}
              isPhone
              showRationale={false}
            />
          </div>
        </>
      )}
    </article>
  )
}
