'use client'

import { Checkbox } from '@/components/ui/checkbox'
import { DataTable, Th } from '@/components/ui/data-table'
import { isDeletable, type DocumentResponse } from '@/lib/documents'
import { DocumentRow } from './document-row'

export interface DocumentsTableProps {
  readonly documents: readonly DocumentResponse[]
  readonly onDocumentChange: (next: DocumentResponse, previous: DocumentResponse) => void
  /** The ids currently ticked for deletion. */
  readonly selectedIds: ReadonlySet<string>
  /** Ticking or unticking one row. */
  readonly onSelectedChange: (document: DocumentResponse, isSelected: boolean) => void
  /**
   * Ticking or unticking every row that can be deleted at all. The table passes the
   * documents themselves rather than a boolean, so which ones are selectable is decided
   * once, here, beside the boxes that show it — the caller stores what it is given.
   */
  readonly onSelectAll: (documents: readonly DocumentResponse[]) => void
}

/**
 * The company's documents, newest first, in the design system's table shape
 * (`DataTable`, from `Main.dc.html` / `Dashboard.dc.html`) — story S4.2.2, restyled for
 * ADR-0014 without a change in behaviour.
 *
 * The container scrolls horizontally when a phone is narrower than six columns, so the
 * page never does; the name and status cells wrap so a failure reason is read in full.
 *
 * The sixth column, *Withheld*, is the injection guard's per-document result (S2.3.1; audit
 * M11): the API had sent `flagged_chunk_count` "for a badge" since S2.3.1 and no screen
 * read it, so a document reading *Ready* could have had passages kept from the agent with
 * nothing beside it saying so. See `WithheldPassages` in `document-row.tsx`.
 */
export function DocumentsTable({
  documents,
  onDocumentChange,
  selectedIds,
  onSelectedChange,
  onSelectAll,
}: DocumentsTableProps) {
  // A document a bid has claimed cannot be deleted (ADR-0088), so it is not selectable and
  // must not count towards "all": a select-all that could never reach every box is a control
  // that looks broken.
  const selectable = documents.filter(isDeletable)
  const allSelected = selectable.length > 0 && selectable.every((d) => selectedIds.has(d.id))

  return (
    <DataTable
      caption="Your company's documents, newest first, with their processing status."
      footer="A document an analysis is using cannot be deleted: those analyses' requirements cite its pages, so removing the file would leave them pointing at a page nobody can open — delete the analyses instead. The same file can be read by any number of analyses, and using it again takes nothing away from the ones that have it. Unread pages have no text layer — a scan without OCR — and the agent says so rather than guessing what is on them. Withheld passages read like instructions aimed at the agent rather than tender text, so they were kept from it; the rest of the file was read as normal."
    >
      <thead>
        <tr>
          <Th className="w-px pr-0">
            <Checkbox
              checked={allSelected}
              disabled={selectable.length === 0}
              onChange={(event) => onSelectAll(event.target.checked ? selectable : [])}
              label={<span className="sr-only">Select every document that can be deleted</span>}
            />
          </Th>
          <Th>Name</Th>
          <Th>Type</Th>
          <Th>Status</Th>
          <Th className="text-right">Pages</Th>
          <Th className="text-right">Unread pages</Th>
          <Th className="text-right">Withheld</Th>
        </tr>
      </thead>
      <tbody>
        {documents.map((document) => (
          <DocumentRow
            key={document.id}
            document={document}
            onChange={onDocumentChange}
            isSelected={selectedIds.has(document.id)}
            onSelectedChange={onSelectedChange}
          />
        ))}
      </tbody>
    </DataTable>
  )
}
