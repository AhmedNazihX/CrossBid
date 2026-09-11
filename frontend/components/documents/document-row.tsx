'use client'

import { useCallback, useEffect, useRef } from 'react'

import { Badge } from '@/components/ui/badge'
import { TableCell, TableHead, TableRow } from '@/components/ui/table'
import { describeApiError } from '@/lib/api-client'
import { getDocument, isDocumentSettled, type DocumentResponse } from '@/lib/documents'
import { usePolling } from '@/lib/use-polling'
import {
  DOCUMENT_KIND_LABELS,
  DOCUMENT_STATUS_LABELS,
  statusBadgeVariant,
} from './document-labels'

export interface DocumentRowProps {
  readonly document: DocumentResponse
  /** Called with each new state the poll returns, and the state it replaced. */
  readonly onChange: (next: DocumentResponse, previous: DocumentResponse) => void
}

/**
 * One table row that keeps itself current.
 *
 * Each in-progress row runs its own `usePolling` — a hook cannot run inside the table's
 * `map`, and a row stops on its own the moment it is `ready` or `failed`, so a table of
 * twenty ready documents and one fresh upload makes exactly one request every two seconds.
 * The parent hears about every change so the list and the live region stay truthful.
 */
export function DocumentRow({ document, onChange }: DocumentRowProps) {
  const fetchLatest = useCallback(
    (signal: AbortSignal) => getDocument(document.id, signal),
    [document.id]
  )
  const { value, error } = usePolling({
    initialValue: document,
    fetchLatest,
    isSettled: isDocumentSettled,
  })

  // Report upward only when the poll produced something new; the first render is the
  // parent's own value coming back, and re-announcing it would double every upload.
  const reportedRef = useRef(value)
  useEffect(() => {
    if (reportedRef.current !== value) {
      onChange(value, reportedRef.current)
      reportedRef.current = value
    }
  }, [value, onChange])

  const isParsed = value.status !== 'uploaded'
  const statusLabel = DOCUMENT_STATUS_LABELS[value.status]

  return (
    <TableRow>
      <TableHead
        scope="row"
        className="h-auto max-w-[16rem] py-3 font-medium break-words whitespace-normal"
      >
        {value.name}
      </TableHead>
      <TableCell className="py-3">{DOCUMENT_KIND_LABELS[value.kind].label}</TableCell>
      <TableCell className="max-w-[20rem] py-3 whitespace-normal">
        <div className="flex flex-col gap-1">
          <Badge variant={statusBadgeVariant(value.status)}>{statusLabel}</Badge>
          {value.status === 'failed' && value.failure_reason !== null && (
            <p className="text-destructive text-sm">{value.failure_reason}</p>
          )}
          {error !== undefined && (
            <p className="text-muted-foreground text-xs">
              Could not refresh: {describeApiError(error)}
            </p>
          )}
        </div>
      </TableCell>
      <TableCell className="py-3 text-right tabular-nums">
        {isParsed ? value.pages : '—'}
      </TableCell>
      <TableCell className="py-3 text-right tabular-nums">
        <UnreadPages document={value} isParsed={isParsed} />
      </TableCell>
    </TableRow>
  )
}

/**
 * The count, with the page numbers on hover for a mouse and read aloud for a screen
 * reader — `title` alone reaches neither the keyboard nor assistive technology.
 */
function UnreadPages({
  document,
  isParsed,
}: {
  document: DocumentResponse
  isParsed: boolean
}) {
  if (!isParsed) {
    return <>—</>
  }
  if (document.unread_page_count === 0) {
    return <>0</>
  }
  const pageList = document.unread_pages.join(', ')
  return (
    <span title={`Pages ${pageList}`}>
      {document.unread_page_count}
      <span className="sr-only"> unread: pages {pageList}</span>
    </span>
  )
}
