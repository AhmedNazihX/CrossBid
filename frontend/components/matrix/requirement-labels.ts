import type { Requirement, RequirementCategory } from '@/lib/bids'

/**
 * The bidder's words for the `Requirement` enums. Categories fold onto the canvas's three
 * column words — Exclusion, Selection, Technical — plus Formal and Other from the contract.
 */
export const CATEGORY_LABELS: Readonly<Record<RequirementCategory, string>> = {
  exclusion_ground: 'Exclusion',
  economic_financial: 'Selection',
  technical_professional: 'Technical',
  formal: 'Formal',
  other: 'Other',
}

/** Display order of the category tabs and the phone's groups. */
export const CATEGORY_ORDER: readonly RequirementCategory[] = [
  'exclusion_ground',
  'economic_financial',
  'technical_professional',
  'formal',
  'other',
]

export type CategoryFilter = 'all' | RequirementCategory

export const KIND_LABELS: Readonly<Record<Requirement['kind'], string>> = {
  mandatory: 'Mandatory',
  optional: 'Optional',
  informational: 'Informational',
}

export const STAGE_LABELS: Readonly<Record<Requirement['stage'], string>> = {
  bid_eligibility: 'Decides whether you may bid',
  contract_performance: 'Applies once the contract runs',
}

export const CHECKABILITY_LABELS: Readonly<Record<Requirement['checkable'], string>> = {
  company_property: 'A fact about your company — evidence can settle it',
  document_submission: 'A document to attach to the offer',
  neither: 'Neither a company fact nor a document to attach',
}

const COMPARATORS: Readonly<
  Record<NonNullable<Requirement['threshold']>['comparator'], string>
> = {
  at_least: 'at least',
  at_most: 'at most',
  max_age: 'no older than',
  equals: 'exactly',
}

const UNITS: Readonly<Record<NonNullable<Requirement['threshold']>['unit'], string>> = {
  currency: '',
  fte: 'FTE',
  headcount: 'people',
  person_days: 'person-days',
  references: 'references',
  years: 'years',
  percent: '%',
}

const NUMBER = new Intl.NumberFormat('de-DE')

/** "at least 2.000.000 EUR per_year" — the typed threshold as one phrase, never inferred. */
export function describeThreshold(threshold: NonNullable<Requirement['threshold']>): string {
  const unit =
    threshold.unit === 'currency' ? (threshold.currency ?? '') : UNITS[threshold.unit]
  const period =
    threshold.period === null || threshold.period === undefined
      ? ''
      : ` ${threshold.period.replaceAll('_', ' ')}`
  return `${COMPARATORS[threshold.comparator]} ${NUMBER.format(threshold.value)} ${unit}${period}`.trim()
}

export function countByCategory(
  requirements: readonly Requirement[]
): ReadonlyMap<RequirementCategory, number> {
  const counts = new Map<RequirementCategory, number>()
  for (const requirement of requirements) {
    counts.set(requirement.category, (counts.get(requirement.category) ?? 0) + 1)
  }
  return counts
}
