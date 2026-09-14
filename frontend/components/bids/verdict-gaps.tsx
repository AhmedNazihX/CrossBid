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

export function VerdictGaps({ gaps, labels }: VerdictGapsProps) {
  return (
    <>
      {SECTIONS.map((section) => {
        const listed = gaps.filter((gap) => gap.severity === section.severity)
        if (listed.length === 0) {
          return null
        }
        return (
          <Card
            key={section.severity}
            title={section.title}
            icon={<Icon name={section.icon} size={20} />}
          >
            <p className="m-0 mb-3.5 [font:var(--type-body-sm)] text-text-muted">
              {section.summary}
            </p>
            <ul className="m-0 flex list-none flex-col gap-3 p-0">
              {listed.map((gap) => (
                <GapLine
                  key={`${gap.requirement_id}-${gap.summary}`}
                  gap={gap}
                  label={labels.get(gap.requirement_id)}
                />
              ))}
            </ul>
          </Card>
        )
      })}
    </>
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
      <span className="min-w-[14rem] flex-1 [overflow-wrap:anywhere]">{gap.summary}</span>
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
