'use client'

import { cn } from 'cn'

import { Icon } from '@/components/ui/icons'
import type { Requirement } from '@/lib/bids'
import { formatLanguage } from '@/lib/format'

/** Which of the two texts a row is showing: the tender's own words, or the translation. */
export type RequirementLanguage = 'source' | 'bidder'

export interface RequirementLanguageToggleProps {
  readonly requirement: Requirement
  readonly bidderLanguage: string
  readonly value: RequirementLanguage
  readonly onChange: (value: RequirementLanguage) => void
  readonly isPhone?: boolean
  readonly className?: string
}

/**
 * The per-row language switch of story S4.5.2 — "switch each row between French and German".
 *
 * A requirement carries two texts: `source_text`, verbatim in the tender's language, and
 * `translation` in the bidder's. The table shows the translation because that is what the
 * reviewer reads at speed, but the tender's own words are the ones a buyer will hold them to,
 * so every row can be flipped back to the original on its own. Presentation only — nothing
 * is fetched and nothing is recorded.
 *
 * Per row rather than per screen because a reviewer checking one clause against its original
 * does not want the other thirty to change under them. Not on an artboard: `Main.dc.html`
 * shows the original in the expanded row's Source block, which answers the desktop case and
 * not the phone's, where there is no second column.
 */
export function RequirementLanguageToggle({
  requirement,
  bidderLanguage,
  value,
  onChange,
  isPhone = false,
  className,
}: RequirementLanguageToggleProps) {
  const options: readonly { readonly key: RequirementLanguage; readonly language: string }[] = [
    { key: 'bidder', language: bidderLanguage },
    { key: 'source', language: requirement.source_lang },
  ]
  return (
    <span
      role="group"
      aria-label="Language of this requirement"
      className={cn(
        'inline-flex items-center gap-1 rounded-md border border-border-default bg-surface-sunken p-0.5',
        className
      )}
    >
      <Icon name="lang" size={13} className="mx-1 text-text-muted" />
      {options.map(({ key, language }) => (
        <button
          key={key}
          type="button"
          aria-pressed={value === key}
          onClick={() => onChange(key)}
          title={
            key === 'source'
              ? `Show the tender's own words (${formatLanguage(language)})`
              : `Show the translation (${formatLanguage(language)})`
          }
          className={cn(
            'inline-flex items-center rounded-sm px-2 text-[12px] font-medium leading-none',
            isPhone ? 'min-h-11' : 'min-h-7',
            value === key
              ? 'bg-surface-card text-text-primary shadow-xs'
              : 'text-text-muted hover:text-text-primary'
          )}
        >
          {formatLanguage(language)}
        </button>
      ))}
    </span>
  )
}

/** The text the row should show, falling back to the original when nothing was translated. */
export function requirementTextIn(
  requirement: Requirement,
  language: RequirementLanguage
): string {
  return language === 'source'
    ? requirement.source_text
    : (requirement.translation ?? requirement.source_text)
}

/**
 * Only a row that really has two texts gets a switch. An untranslated row already shows the
 * original, and a tender written in the bidder's own language has nothing to switch to.
 */
export function isSwitchable(requirement: Requirement, bidderLanguage: string): boolean {
  const translation = requirement.translation
  return (
    translation !== null &&
    translation !== undefined &&
    translation.length > 0 &&
    formatLanguage(requirement.source_lang) !== formatLanguage(bidderLanguage)
  )
}
