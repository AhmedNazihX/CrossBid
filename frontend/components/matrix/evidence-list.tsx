'use client'

import type { Evidence } from '@/lib/bids'
import { TAB_NAME_CHARS } from '@/lib/format'
import { CitationLink } from './citation-link'
import { isSameCitation, type Citation } from './citation'

export interface EvidenceListProps {
  readonly evidence: readonly Evidence[]
  readonly activeCitation: Citation | undefined
  readonly onCite: (citation: Citation) => void
  /** 44 px rows for the phone card; the desktop row keeps the 32 px citation face. */
  readonly isPhone?: boolean
}

/**
 * The cited passages of an expanded row — the "Evidence in your profile" block of
 * `Main.dc.html`. One item per citation: the document and page in the citation face, and
 * under it the passage the check read, verbatim. The citation is the same `CitationLink` the
 * Source column uses, so a click moves the source panel to that page of that document —
 * whether the passage came from the tender pack or from the bidder's own files.
 */
export function EvidenceList({
  evidence,
  activeCitation,
  onCite,
  isPhone = false,
}: EvidenceListProps) {
  return (
    <ul className="m-0 flex list-none flex-col gap-2.5 p-0">
      {evidence.map((item) => {
        const citation: Citation = {
          documentId: item.document_id,
          documentName: item.document_name,
          page: item.page,
        }
        return (
          <li key={`${item.document_id}:${item.page}:${item.quote}`} className="min-w-0">
            <CitationLink
              citation={citation}
              isActive={isSameCitation(activeCitation, citation)}
              onCite={onCite}
              nameChars={TAB_NAME_CHARS}
              className={isPhone ? 'min-h-11' : undefined}
            />
            <blockquote className="m-0 mt-0.5 border-l-2 border-border-default pl-2.5 text-base leading-[1.5] text-text-secondary italic">
              &ldquo;{item.quote}&rdquo;
            </blockquote>
          </li>
        )
      })}
    </ul>
  )
}
