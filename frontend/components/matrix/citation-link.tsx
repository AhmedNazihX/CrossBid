'use client'

import { cn } from 'cn'

import { Icon } from '@/components/ui/icons'
import { CITATION_NAME_CHARS, shortDocumentName } from '@/lib/format'
import type { Citation } from './citation'

interface CitationLinkProps {
  readonly citation: Citation
  readonly isActive: boolean
  readonly onCite: (citation: Citation) => void
  /** Omit the document name when the pack has one document — the page alone identifies it. */
  readonly showDocument?: boolean
  /** How much of the filename fits: the Source column is narrow, an evidence line is not. */
  readonly nameChars?: number
  readonly className?: string
}

/**
 * The Source cell of `Main.dc.html`: `<document> p. N` in the citation face with the
 * external-link glyph. Clicking it opens that page in the source panel — S4.5.1's
 * jump-to-page. `aria-pressed` marks the citation the panel currently shows.
 */
export function CitationLink({
  citation,
  isActive,
  onCite,
  showDocument = true,
  nameChars = CITATION_NAME_CHARS,
  className,
}: CitationLinkProps) {
  // A DUME/ESPD requirement has no page and its file is XML, which the source panel cannot
  // render. Offering the usual link would promise a jump that cannot happen, so it reads as
  // a label: the file, and the criterion the buyer keyed it on. Not from an artboard —
  // `Main.dc.html` predates ESPD ingestion and has no state for a page-less citation.
  if (citation.page === null) {
    return (
      <span
        title={citation.criterionId ?? citation.documentName}
        className={cn(
          'inline-flex min-h-8 items-center gap-[5px] [font:var(--type-mono)] text-text-muted',
          className
        )}
      >
        {showDocument && shortDocumentName(citation.documentName, nameChars)}
        {showDocument && ' · '}
        ESPD criterion
      </span>
    )
  }

  return (
    <button
      type="button"
      onClick={() => onCite(citation)}
      aria-pressed={isActive}
      aria-label={`Open ${citation.documentName}, page ${citation.page}, in the source panel`}
      title={`${citation.documentName}, page ${citation.page}`}
      className={cn(
        'inline-flex min-h-8 items-center gap-[5px] rounded-sm px-1 -mx-1 text-left [font:var(--type-mono)] text-text-link hover:bg-surface-hover hover:underline',
        isActive && 'bg-surface-sunken underline',
        className
      )}
    >
      <span className="whitespace-nowrap">
        {showDocument ? `${shortDocumentName(citation.documentName, nameChars)} ` : ''}
        p. {citation.page}
      </span>
      <Icon name="ext" size={12} />
    </button>
  )
}
