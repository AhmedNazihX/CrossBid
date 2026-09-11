'use client'

import { useCallback, useEffect, useState } from 'react'

import { EmptyState } from '@/components/common/empty-state'
import { Card } from '@/components/ui/card'
import { Icon } from '@/components/ui/icons'
import { Notice } from '@/components/ui/notice'
import { describeApiError } from '@/lib/api-client'
import {
  listDocuments,
  uploadDocument,
  type DocumentKind,
  type DocumentResponse,
} from '@/lib/documents'
import { DOCUMENT_STATUS_LABELS } from './document-labels'
import { DocumentsTable } from './documents-table'
import { UploadForm } from './upload-form'

type ListState =
  | { readonly phase: 'loading' }
  | { readonly phase: 'failed'; readonly message: string }
  | { readonly phase: 'loaded' }

/**
 * The upload form, the documents table and the one live region that ties them together
 * (story S4.2.2), on the design system's `Card` and `Notice` (ADR-0014).
 *
 * This is the only component on the page that talks to the API for the list: it loads
 * `GET /documents` once on mount, prepends each 202 row the form produces, and merges the
 * states the rows poll for themselves. Status changes are announced from here, in one
 * `role="status"` region, because a region per row would read every poll aloud.
 */
export function DocumentsPanel() {
  const [documents, setDocuments] = useState<readonly DocumentResponse[]>([])
  const [listState, setListState] = useState<ListState>({ phase: 'loading' })
  const [announcement, setAnnouncement] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    listDocuments(controller.signal)
      .then((found) => {
        setDocuments(found)
        setListState({ phase: 'loaded' })
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) {
          setListState({ phase: 'failed', message: describeApiError(cause) })
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

  return (
    <div className="flex flex-col gap-6">
      <Card title="Upload a document" icon={<Icon name="upload" size={20} />}>
        <p className="m-0 mb-4 max-w-[720px] text-text-secondary">
          CrossBid reads each PDF page by page and indexes it, so the agent can quote it as
          evidence. Processing takes a moment; the table below shows how far each file has got.
        </p>
        <UploadForm onUpload={handleUpload} />
      </Card>

      <p role="status" aria-live="polite" className="sr-only">
        {announcement}
      </p>

      <DocumentsSection
        documents={documents}
        listState={listState}
        onChange={handleDocumentChange}
      />
    </div>
  )
}

function DocumentsSection({
  documents,
  listState,
  onChange,
}: {
  readonly documents: readonly DocumentResponse[]
  readonly listState: ListState
  readonly onChange: (next: DocumentResponse, previous: DocumentResponse) => void
}) {
  if (listState.phase === 'failed' && documents.length === 0) {
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
  if (documents.length === 0) {
    return (
      <EmptyState
        title="No documents yet"
        description="The agent can only claim what your documents prove. Upload the certificates, accounts, insurance and references you normally attach to a bid, and CrossBid will match each tender requirement to a page in them."
        steps={[
          'Choose a PDF above and pick “Company evidence” as its type.',
          'Watch its status until it reads Ready — or Failed, with the reason to fix.',
          'Repeat for each certificate; the agent cites the page it found the evidence on.',
        ]}
      />
    )
  }
  return <DocumentsTable documents={documents} onDocumentChange={onChange} />
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
