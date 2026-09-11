'use client'

import { DataTable, Th } from '@/components/ui/data-table'
import type { DocumentResponse } from '@/lib/documents'
import { DocumentRow } from './document-row'

export interface DocumentsTableProps {
  readonly documents: readonly DocumentResponse[]
  readonly onDocumentChange: (next: DocumentResponse, previous: DocumentResponse) => void
}

/**
 * The company's documents, newest first, in the design system's table shape
 * (`DataTable`, from `Main.dc.html` / `Dashboard.dc.html`) — story S4.2.2, restyled for
 * ADR-0014 without a change in behaviour.
 *
 * The container scrolls horizontally when a phone is narrower than five columns, so the
 * page never does; the name and status cells wrap so a failure reason is read in full.
 */
export function DocumentsTable({ documents, onDocumentChange }: DocumentsTableProps) {
  return (
    <DataTable
      caption="Your company's documents, newest first, with their processing status."
      footer="Unread pages have no text layer — a scan without OCR — and the agent says so rather than guessing what is on them."
    >
      <thead>
        <tr>
          <Th>Name</Th>
          <Th>Type</Th>
          <Th>Status</Th>
          <Th className="text-right">Pages</Th>
          <Th className="text-right">Unread pages</Th>
        </tr>
      </thead>
      <tbody>
        {documents.map((document) => (
          <DocumentRow key={document.id} document={document} onChange={onDocumentChange} />
        ))}
      </tbody>
    </DataTable>
  )
}
