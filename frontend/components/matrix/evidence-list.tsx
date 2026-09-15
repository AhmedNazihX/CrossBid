'use client'

import { TAB_NAME_CHARS } from '@/lib/format'
import { CitationLink } from './citation-link'
import { isSameCitation, type Citation } from './citation'

/**
 * What the list needs of a citation: the passage's address, and its text when one was
 * kept. A matrix row's `Evidence` always carries the quote; a chat answer's `Citation`
 * (S4.6.1) may not, because the server resolves it from the retrieved passage and a
 * passage can be cited for its page alone.
 */
export interface CitedPassage {
  readonly document_id: string
  readonly document_name: string
  readonly page: number
  readonly quote?: string | null
}

export interface EvidenceListProps {
  readonly evidence: readonly CitedPassage[]
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
 *
 * The chat panel lists an answer's citations with this same component, so a cited page
 * looks and behaves the same whether a check or an answer pointed at it.
 */
export function EvidenceList({
  evidence,
  activeCitation,
  onCite,
  isPhone = false,
}: EvidenceListProps) {
  return (
    <ul className="m-0 flex list-none flex-col gap-2.5 p-0">
      {evidence.map((item, index) => {
        const citation: Citation = {
          documentId: item.document_id,
          documentName: item.document_name,
          page: item.page,
        }
        const quote = item.quote ?? ''
        return (
          <li key={`${item.document_id}:${item.page}:${index}`} className="min-w-0">
            <CitationLink
              citation={citation}
              isActive={isSameCitation(activeCitation, citation)}
              onCite={onCite}
              nameChars={TAB_NAME_CHARS}
              className={isPhone ? 'min-h-11' : undefined}
            />
            {quote !== '' && (
              <blockquote className="m-0 mt-0.5 border-l-2 border-border-default pl-2.5 text-base leading-[1.5] text-text-secondary italic">
                &ldquo;{quote}&rdquo;
              </blockquote>
            )}
          </li>
        )
      })}
    </ul>
  )
}
