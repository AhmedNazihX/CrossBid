'use client'

import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Icon } from '@/components/ui/icons'
import { Tag } from '@/components/ui/tag'
import type { Gap, GapSeverity, Requirement } from '@/lib/bids'
import { requirementLabel } from '@/lib/format'

/**
 * The two gap lists of `Verdict.dc.html` (story S4.5.3): "What would change the verdict" for
 * the `blocking` gaps, "Strengthens position" for the `open_item` ones.
 *
 * They are one component because the split is the whole point. A reviewer deciding whether
 * to override needs to see, before the radio buttons, which gaps stand between this tender
 * and a different verdict and which merely improve the offer — a single list of "gaps" would
 * make an open item look like a blocker and push a bidder away from a tender they could win.
 * Each line carries the requirement's `REQ-` label so it can be found again in the matrix.
 *
 * **Each list is capped, and that is a correction rather than a feature.** `Verdict.dc.html`
 * draws four gap rows; this rendered every one of them, and the FR bid has 142. At the rail's
 * 380 px that is ten thousand pixels of cards between the recommendation and the decision the
 * reviewer came to make — the fold ADR-0106 is about. The first few are shown and the rest are
 * one click away, which is the artboard's shape with an honest count on it.
 */
export interface VerdictGapsProps {
  readonly gaps: readonly Gap[]
  /** Requirement id → the matrix's display label, from `requirementLabels`. */
  readonly labels: ReadonlyMap<string, string>
}

interface GapSection {
  readonly severity: GapSeverity
  readonly title: string
  readonly icon: 'fileCheck' | 'layers'
  /** Said once above the list, so no line has to repeat what its severity means. */
  readonly summary: string
}

const SECTIONS: readonly GapSection[] = [
  {
    severity: 'blocking',
    title: 'What would change the verdict',
    icon: 'fileCheck',
    summary: 'Each of these stands between this tender and a better verdict.',
  },
  {
    severity: 'open_item',
    title: 'Strengthens position',
    icon: 'layers',
    summary: 'None of these blocks the bid; each makes the offer harder to fault.',
  },
]

/**
 * How many gaps a list shows before it asks. Five rather than the artboard's four because a
 * fifth line costs nothing and the round number reads as a cap rather than as all there is.
 */
const SHOWN_BY_DEFAULT = 5

export function VerdictGaps({ gaps, labels }: VerdictGapsProps) {
  return (
    <>
      {SECTIONS.map((section) => {
        const listed = gaps.filter((gap) => gap.severity === section.severity)
        if (listed.length === 0) {
          return null
        }
        return (
          <GapSectionCard
            key={section.severity}
            section={section}
            gaps={listed}
            labels={labels}
          />
        )
      })}
    </>
  )
}

function GapSectionCard({
  section,
  gaps,
  labels,
}: {
  readonly section: GapSection
  readonly gaps: readonly Gap[]
  readonly labels: ReadonlyMap<string, string>
}) {
  const [isExpanded, setExpanded] = useState(false)
  const isCapped = gaps.length > SHOWN_BY_DEFAULT
  const shown = isExpanded || !isCapped ? gaps : gaps.slice(0, SHOWN_BY_DEFAULT)
  return (
    <Card title={section.title} icon={<Icon name={section.icon} size={20} />}>
      <p className="m-0 mb-3.5 [font:var(--type-body-sm)] text-text-muted">{section.summary}</p>
      <ul className="m-0 flex list-none flex-col gap-3 p-0">
        {shown.map((gap) => (
          <GapLine
            key={`${gap.requirement_id}-${gap.summary}`}
            gap={gap}
            label={labels.get(gap.requirement_id)}
          />
        ))}
      </ul>
      {isCapped && (
        // The count is on the control, not hidden behind it: "and 137 more" is the fact a
        // reviewer needs to judge the tender, whether or not they open the list.
        <Button
          variant="ghost"
          size="sm"
          className="mt-3 -ml-3"
          aria-expanded={isExpanded}
          onClick={() => setExpanded((open) => !open)}
        >
          {isExpanded
            ? `Show the first ${SHOWN_BY_DEFAULT}`
            : `Show all ${gaps.length} · ${gaps.length - SHOWN_BY_DEFAULT} more`}
        </Button>
      )}
    </Card>
  )
}

function GapLine({ gap, label }: { readonly gap: Gap; readonly label: string | undefined }) {
  const shortfall = describeShortfall(gap)
  return (
    <li className="flex flex-wrap items-baseline gap-x-3.5 gap-y-1 leading-[1.4]">
      {label !== undefined && (
        <Tag mono className="shrink-0">
          {label}
        </Tag>
      )}
      {/* 12 rem, not 14: the panel now stacks in a 385 px tab and a 343 px phone panel
          (ADR-0060), whose list lines are ~290 px inside the card. At 14 rem the sentence
          could not fit beside a 68 px `REQ-` tag and dropped under it on every line;
          at 12 rem it sits beside the tag as the artboard draws it, and the shortfall
          wraps below. */}
      <span className="min-w-[12rem] flex-1 [overflow-wrap:anywhere]">{gap.summary}</span>
      {shortfall !== undefined && (
        <span className="[font:var(--type-body-sm)] font-medium text-text-secondary">
          {shortfall}
        </span>
      )}
    </li>
  )
}

/**
 * "Needs 29 FTE · you have 21 FTE" — the numbers the agent compared, when it recorded them.
 * A gap without them is not a lesser gap, so the line simply ends after its sentence.
 */
function describeShortfall(gap: Gap): string | undefined {
  const required = gap.required ?? undefined
  const actual = gap.actual ?? undefined
  if (required === undefined) {
    return actual === undefined ? undefined : `You have ${actual}`
  }
  return actual === undefined ? `Needs ${required}` : `Needs ${required} · you have ${actual}`
}

/**
 * Requirement id → "REQ-007". The label is the requirement's position in the bid's list, not
 * anything the API stores, so it has to be derived from the same array the matrix numbers.
 */
export function requirementLabels(
  requirements: readonly Requirement[]
): ReadonlyMap<string, string> {
  return new Map(
    requirements.map((requirement, index) => [requirement.id, requirementLabel(index)])
  )
}
