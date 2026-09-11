'use client'

import {
  Table,
  TableBody,
  TableCaption,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type { DocumentResponse } from '@/lib/documents'
import { DocumentRow } from './document-row'

export interface DocumentsTableProps {
  readonly documents: readonly DocumentResponse[]
  readonly onDocumentChange: (next: DocumentResponse, previous: DocumentResponse) => void
}

/**
 * The company's documents, newest first, in a stock shadcn/ui table (story S4.2.2).
 *
 * The table's own wrapper scrolls horizontally when a phone is narrower than five columns,
 * so the page never does; the name and status cells wrap so a failure reason is read in
 * full rather than clipped.
 */
export function DocumentsTable({ documents, onDocumentChange }: DocumentsTableProps) {
  return (
    <Table>
      <TableCaption className="text-left">
        Unread pages have no text layer — a scan without OCR — and the agent says so rather than
        guessing what is on them.
      </TableCaption>
      <TableHeader>
        <TableRow>
          <TableHead scope="col">Name</TableHead>
          <TableHead scope="col">Type</TableHead>
          <TableHead scope="col">Status</TableHead>
          <TableHead scope="col" className="text-right">
            Pages
          </TableHead>
          <TableHead scope="col" className="text-right">
            Unread pages
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {documents.map((document) => (
          <DocumentRow key={document.id} document={document} onChange={onDocumentChange} />
        ))}
      </TableBody>
    </Table>
  )
}
