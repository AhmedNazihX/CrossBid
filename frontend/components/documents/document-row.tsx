'use client'

import { useCallback, useEffect, useRef } from 'react'

import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { Tag } from '@/components/ui/tag'
import { Td, Tr } from '@/components/ui/data-table'
import { describeApiError } from '@/lib/api-client'
import {
  getDocument,
  hasPages,
  analysesUsing,
  isDeletable,
  isDocumentSettled,
  type DocumentResponse,
} from '@/lib/documents'
import { formatPageList, plural } from '@/lib/format'
import { usePolling } from '@/lib/use-polling'
import {
  DOCUMENT_KIND_LABELS,
  DOCUMENT_STATUS_LABELS,
  statusBadgeTone,
} from './document-labels'

export interface DocumentRowProps {
  readonly document: DocumentResponse
  /** Called with each new state the poll returns, and the state it replaced. */
  readonly onChange: (next: DocumentResponse, previous: DocumentResponse) => void
  /** Whether this row is ticked for deletion. */
  readonly isSelected: boolean
  /** Ticking or unticking the row; a document a bid has claimed cannot be ticked at all. */
  readonly onSelectedChange: (document: DocumentResponse, isSelected: boolean) => void
}

/**
 * One table row that keeps itself current (story S4.2.2), in the row shape of
 * `NewBid.dc.html`'s procurement-documents list: name and meta, then a status `Badge`.
 *
 * Each in-progress row runs its own `usePolling` — a hook cannot run inside the table's
 * `map`, and a row stops on its own the moment it is `ready` or `failed`, so a table of
 * twenty ready documents and one fresh upload makes exactly one request every two seconds.
 * The parent hears about every change so the list and the live region stay truthful.
 */
export function DocumentRow({
  document,
  onChange,
  isSelected,
  onSelectedChange,
}: DocumentRowProps) {
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
  // An ESPD request has no pages to count, so both page columns read — rather than 0.
  const isPaginated = hasPages(value.kind)

  return (
    <Tr>
      <Td className="w-px pr-0">
        <SelectDocument
          document={value}
          isSelected={isSelected}
          onSelectedChange={onSelectedChange}
        />
      </Td>
      <th
        scope="row"
        className="min-w-[220px] max-w-[20rem] px-5 py-3.5 text-left align-middle font-medium [overflow-wrap:anywhere]"
      >
        <span className="block">{value.name}</span>
        {!isDeletable(value) && (
          <Tag className="mt-1.5" title={explainInUse(value)}>
            In {analysesUsing(value)} — cannot be deleted
            <span className="sr-only">. {explainInUse(value)}</span>
          </Tag>
        )}
      </th>
      <Td className="text-text-secondary">{DOCUMENT_KIND_LABELS[value.kind].label}</Td>
      <Td className="max-w-[22rem]">
        <div className="flex flex-col items-start gap-1">
          <Badge tone={statusBadgeTone(value.status)}>
            {DOCUMENT_STATUS_LABELS[value.status]}
          </Badge>
          {value.status === 'failed' && value.failure_reason !== null && (
            <p className="m-0 [font:var(--type-body-sm)] text-status-danger-text">
              {value.failure_reason}
            </p>
          )}
          {error !== undefined && (
            <p className="m-0 [font:var(--type-body-sm)] text-text-muted">
              Could not refresh: {describeApiError(error)}
            </p>
          )}
        </div>
      </Td>
      <Td className="text-right tabular-nums">{isParsed && isPaginated ? value.pages : '—'}</Td>
      <Td className="text-right tabular-nums">
        <UnreadPages document={value} hasCount={isParsed && isPaginated} />
      </Td>
      <Td className="text-right tabular-nums">
        <WithheldPassages document={value} />
      </Td>
    </Tr>
  )
}

/**
 * Said once, for the pointer (`title`) and the screen reader (visually hidden text) alike.
 * Calm and factual on purpose: this is neither an error nor an accusation. The file is
 * fine, the rest of it was read in full, and the count exists so a bidder who can see a
 * passage on the page that was never cited knows why.
 */
const WITHHELD_EXPLANATION =
  'These passages read like instructions aimed at the agent rather than tender text, so they were not given to the agent. The rest of the document was read in full.'

/**
 * The injection guard's result for this document (S2.3.1, S5.3; audit M11) — how many
 * passages were kept out of the corpus, from `flagged_chunk_count`, which the API has sent
 * "for a badge" since S2.3.1 and which no screen read until 2026-09-16.
 *
 * A warning badge in words rather than a red one, because nothing is wrong with the file;
 * the sentence is in the text, not in the colour. The chunk numbers are the pipeline's, not
 * pages, so they are not printed — a bidder has nothing to turn to. `0` is shown only once
 * the document is `ready`: the guard runs before embedding, so an earlier zero would claim a
 * count that has not yet been taken, the same reason `UnreadPages` waits for a parse.
 */
function WithheldPassages({ document }: { document: DocumentResponse }) {
  if (document.flagged_chunk_count > 0) {
    return (
      <Badge tone="warning" size="sm" title={WITHHELD_EXPLANATION}>
        <span>{plural(document.flagged_chunk_count, 'passage')} withheld</span>
        <span className="sr-only">. {WITHHELD_EXPLANATION}</span>
      </Badge>
    )
  }
  return <>{document.status === 'ready' ? '0' : '—'}</>
}

/**
 * The count, with the page numbers on hover for a mouse and read aloud for a screen
 * reader — `title` alone reaches neither the keyboard nor assistive technology.
 *
 * `hasCount` is false both before the file is parsed and for a kind that has no pages at
 * all, because in either case a `0` would claim something that was never counted.
 */
function UnreadPages({
  document,
  hasCount,
}: {
  document: DocumentResponse
  hasCount: boolean
}) {
  if (!hasCount) {
    return <>—</>
  }
  if (document.unread_page_count === 0) {
    return <>0</>
  }
  const pageList = formatPageList(document.unread_pages)
  return (
    <span title={pageList}>
      {document.unread_page_count}
      <span className="sr-only"> unread: {pageList}</span>
    </span>
  )
}

/**
 * Why a document an analysis is using cannot be ticked: the API refuses to delete it with a
 * 409, because that run's requirements cite its pages. A checkbox that can only lead to a
 * refusal is worse than no checkbox, so the box is disabled and the row says what is true.
 *
 * One template, grammatical at one and at many, because a document may now be used by several
 * analyses at once (ADR-0103) and the count is what makes the sentence actionable.
 */
function explainInUse(document: DocumentResponse): string {
  return (
    `Used by ${analysesUsing(document)}, whose requirements cite its pages. ` +
    'Delete those analyses and this file can be deleted too.'
  )
}

/**
 * The row's tick box, and the whole of the row's part in deleting.
 *
 * It lives in the FIRST column on purpose. The table scrolls horizontally when the window is
 * narrower than its content, and the delete control used to be the last column: at 1100 px
 * it sat 106 px past the right edge, reachable only by scrolling the table sideways with
 * nothing on screen to say it was there. Leading the row means the control is visible before
 * anything can be clipped, and the button that acts on the selection sits above the table,
 * outside the scrolling box entirely.
 *
 * The label names the document rather than reading "Select": on a twenty-nine row pack,
 * twenty-nine controls called "Select" are one control to anyone using a screen reader.
 */
function SelectDocument({
  document,
  isSelected,
  onSelectedChange,
}: {
  document: DocumentResponse
  isSelected: boolean
  onSelectedChange: (document: DocumentResponse, isSelected: boolean) => void
}) {
  const isClaimed = !isDeletable(document)
  return (
    <Checkbox
      checked={isSelected}
      disabled={isClaimed}
      title={isClaimed ? explainInUse(document) : undefined}
      onChange={(event) => onSelectedChange(document, event.target.checked)}
      label={
        <span className="sr-only">
          {isClaimed
            ? `${document.name} — used by ${analysesUsing(document)}, cannot be deleted`
            : `Select ${document.name}`}
        </span>
      }
    />
  )
}
