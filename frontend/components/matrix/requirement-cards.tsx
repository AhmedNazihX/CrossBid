'use client'

import { Eyebrow } from '@/components/ui/eyebrow'
import { Tag } from '@/components/ui/tag'
import type { Requirement } from '@/lib/bids'
import { requirementLabel } from '@/lib/format'
import { CitationLink } from './citation-link'
import { isSameCitation, type Citation } from './citation'
import { CATEGORY_LABELS, CATEGORY_ORDER } from './requirement-labels'

export interface RequirementCardsProps {
  readonly requirements: readonly Requirement[]
  readonly activeCitation: Citation | undefined
  readonly onCite: (citation: Citation) => void
  readonly emptyMessage: React.ReactNode
}

/**
 * The phone's requirement cards (`WorkspacePhone.dc.html`): grouped under an eyebrow per
 * category with its count; each card a white 12 px-radius tile with the category tag and
 * the citation on top, the explained requirement below, and — in Increment 1 — a muted
 * evidence line instead of a status. Every tap target is at least 44 px.
 */
export function RequirementCards({
  requirements,
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
            {group.map(({ requirement, index }) => {
              const citation: Citation = {
                documentName: requirement.document_name,
                page: requirement.page,
              }
              return (
                <article
                  key={requirement.id}
                  className="flex flex-col gap-2 rounded-lg border border-border-default bg-surface-card px-4 py-3.5 shadow-xs"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <Tag mono>{requirementLabel(index)}</Tag>
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
                  <p className="m-0 [font:var(--type-body-sm)] text-text-secondary">
                    Evidence: checked in Increment 2
                  </p>
                </article>
              )
            })}
          </section>
        )
      })}
    </div>
  )
}
