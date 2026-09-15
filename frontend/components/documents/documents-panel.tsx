'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'

import { EmptyState, type EmptyStateProps } from '@/components/common/empty-state'
import { Card } from '@/components/ui/card'
import { Icon } from '@/components/ui/icons'
import { Notice } from '@/components/ui/notice'
import { describeApiError } from '@/lib/api-client'
import {
  listDocuments,
  TENDER_DOCUMENT_KINDS,
  uploadDocument,
  type DocumentKind,
  type DocumentResponse,
} from '@/lib/documents'
import { DOCUMENT_KIND_LABELS, DOCUMENT_STATUS_LABELS } from './document-labels'
import { DocumentsTable } from './documents-table'
import { UploadForm } from './upload-form'

/** How far the first `GET /documents` has got; the rows themselves live in `documents`. */
type LoadState =
  | { readonly phase: 'loading' }
  | { readonly phase: 'failed'; readonly message: string }
  | { readonly phase: 'loaded' }

/**
 * The list as this panel knows it, in a shape a sibling can render from without asking the
 * API for a copy of its own. `loaded` carries every document — every kind, every status,
 * the upload accepted a second ago included — so a consumer that wants only the finished
 * tender files filters, as `StartBidForm` does.
 */
export type DocumentListState =
  | { readonly phase: 'loading' }
  | { readonly phase: 'failed'; readonly message: string }
  | { readonly phase: 'loaded'; readonly documents: readonly DocumentResponse[] }

/** `/company`'s default: that page is where the certificates live. */
const DEFAULT_KIND: DocumentKind = 'company_evidence'

export interface DocumentsPanelProps {
  /**
   * The type the upload form starts on and returns to after each upload.
   *
   * `/company` leaves this alone. The new-bid flow passes `tender_document`, because the
   * start step keeps only `TENDER_DOCUMENT_KINDS`: a pack uploaded under the evidence
   * default dropped out of that checklist with no explanation, which is how the flow's
   * whole purpose got lost (found 2026-09-15). The empty state follows the same choice, so
   * it never tells a bidder mid-flow to pick the one type the start step cannot see.
   */
  readonly defaultKind?: DocumentKind
  /**
   * Hears the list every time this panel's knowledge of it changes: the first
   * `GET /documents`, each accepted upload, and each state a row polls into — `ready`
   * included, which is the one the start step is waiting for. The new-bid flow feeds it to
   * `StartBidForm`, so a file dropped in step 2 is in step 3 without a second fetch or a
   * refresh. `/company` has no such sibling and passes nothing.
   */
  readonly onDocumentsChange?: (state: DocumentListState) => void
}

/**
 * The upload form, the documents table and the one live region that ties them together
 * (story S4.2.2), on the design system's `Card` and `Notice` (ADR-0014).
 *
 * This is the only component on the page that talks to the API for the list: it loads
 * `GET /documents` once on mount, prepends each 202 row the form produces, and merges the
 * states the rows poll for themselves. Anything else on the page that wants the list is
 * told through `onDocumentsChange` rather than fetching a copy, because a copy taken on
 * mount is stale from the first upload on. Status changes are announced from here, in one
 * `role="status"` region, because a region per row would read every poll aloud.
 */
export function DocumentsPanel({
  defaultKind = DEFAULT_KIND,
  onDocumentsChange,
}: DocumentsPanelProps = {}) {
  const [documents, setDocuments] = useState<readonly DocumentResponse[]>([])
  const [loadState, setLoadState] = useState<LoadState>({ phase: 'loading' })
  const [announcement, setAnnouncement] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    listDocuments(controller.signal)
      .then((found) => {
        setDocuments(found)
        setLoadState({ phase: 'loaded' })
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) {
          setLoadState({ phase: 'failed', message: describeApiError(cause) })
        }
      })
    return () => controller.abort()
  }, [])

  const handleUpload = useCallback(async (file: File, kind: DocumentKind) => {
    let accepted: DocumentResponse
    try {
      accepted = await uploadDocument(file, kind)
    } catch (cause) {
      throw new Error(describeApiError(cause), { cause })
    }
    setDocuments((current) => [accepted, ...current.filter((d) => d.id !== accepted.id)])
    setAnnouncement(`${accepted.name} uploaded. ${DOCUMENT_STATUS_LABELS[accepted.status]}`)
  }, [])

  const handleDocumentChange = useCallback(
    (next: DocumentResponse, previous: DocumentResponse) => {
      setDocuments((current) => current.map((d) => (d.id === next.id ? next : d)))
      if (next.status !== previous.status) {
        setAnnouncement(describeStatusChange(next))
      }
    },
    []
  )

  // Memoised because the effect below keys on it: a fresh object every render would tell
  // the parent every render, the parent's `setState` would render this panel again, and the
  // two would chase each other for ever.
  const listState = useMemo(() => toListState(loadState, documents), [loadState, documents])

  // The list changes from three places — the first fetch, an accepted upload, a row's poll —
  // and two of them go through functional updaters that never hold the new array in the
  // handler. So the parent is told from one effect over the settled state, once per change,
  // rather than from three handlers each recomputing what the others just did.
  useEffect(() => {
    onDocumentsChange?.(listState)
  }, [onDocumentsChange, listState])

  return (
    <div className="flex flex-col gap-6">
      <Card title="Upload a document" icon={<Icon name="upload" size={20} />}>
        <p className="m-0 mb-4 max-w-[720px] text-text-secondary">
          CrossBid reads each PDF page by page and indexes it, so the agent can quote it as
          evidence. Processing takes a moment; the table below shows how far each file has got.
        </p>
        <UploadForm onUpload={handleUpload} defaultKind={defaultKind} />
      </Card>

      <p role="status" aria-live="polite" className="sr-only">
        {announcement}
      </p>

      <DocumentsSection
        listState={listState}
        emptyState={emptyStateFor(defaultKind)}
        onChange={handleDocumentChange}
      />
    </div>
  )
}

/**
 * One reading of "what does the panel know", shared by the section below and by whoever
 * listens through `onDocumentsChange`, so the two never disagree. A failed load still counts
 * as loaded once an upload has put a row in it: the bidder can see that row, so the start
 * step should too.
 */
function toListState(
  loadState: LoadState,
  documents: readonly DocumentResponse[]
): DocumentListState {
  if (loadState.phase === 'failed' && documents.length === 0) {
    return loadState
  }
  if (loadState.phase === 'loading') {
    return loadState
  }
  return { phase: 'loaded', documents }
}

function DocumentsSection({
  listState,
  emptyState,
  onChange,
}: {
  readonly listState: DocumentListState
  readonly emptyState: EmptyStateProps
  readonly onChange: (next: DocumentResponse, previous: DocumentResponse) => void
}) {
  if (listState.phase === 'failed') {
    return (
      <Notice tone="danger" title="Your documents could not be loaded">
        {listState.message}
      </Notice>
    )
  }
  if (listState.phase === 'loading') {
    return (
      <p role="status" className="m-0 [font:var(--type-body-sm)] text-text-muted">
        Loading your documents…
      </p>
    )
  }
  if (listState.documents.length === 0) {
    return <EmptyState {...emptyState} />
  }
  return <DocumentsTable documents={listState.documents} onDocumentChange={onChange} />
}

/**
 * What a company with no documents at all is told, chosen by what the page is for. On
 * `/company` the absence that matters is the evidence; in the new-bid flow it is the pack,
 * and the step that names a type has to name the one the select already shows.
 */
function emptyStateFor(defaultKind: DocumentKind): EmptyStateProps {
  const label = DOCUMENT_KIND_LABELS[defaultKind].label
  if (TENDER_DOCUMENT_KINDS.has(defaultKind)) {
    return {
      title: 'No documents yet',
      description:
        'The agent reads the buyer’s pack to find every requirement, and the notice, the specifications and the contract terms each carry some. Upload them here one file at a time; each one is offered in the start step as soon as it is ready.',
      steps: [
        `Choose a PDF above and pick “${label}” as its type — the notice and the buyer’s ESPD request have types of their own.`,
        'Watch its status until it reads Ready — or Failed, with the reason to fix.',
        'Repeat for each file in the pack. The agent cites the page it found each requirement on.',
      ],
    }
  }
  return {
    title: 'No documents yet',
    description:
      'The agent can only claim what your documents prove. Upload the certificates, accounts, insurance and references you normally attach to a bid, and CrossBid will match each tender requirement to a page in them.',
    steps: [
      `Choose a PDF above and pick “${label}” as its type.`,
      'Watch its status until it reads Ready — or Failed, with the reason to fix.',
      'Repeat for each certificate; the agent cites the page it found the evidence on.',
    ],
  }
}

function describeStatusChange(document: DocumentResponse): string {
  const status = DOCUMENT_STATUS_LABELS[document.status]
  if (document.status === 'failed' && document.failure_reason !== null) {
    return `${document.name}: ${status}. ${document.failure_reason}`
  }
  if (document.status === 'ready') {
    const unread =
      document.unread_page_count === 0
        ? 'every page read'
        : `${document.unread_page_count} of ${document.pages} pages could not be read`
    return `${document.name}: ${status}, ${unread}.`
  }
  return `${document.name}: ${status}`
}
