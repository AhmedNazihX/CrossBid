import type { BadgeTone } from '@/components/ui/badge'
import type { DocumentKind, DocumentStatus } from '@/lib/documents'

export interface DocumentKindLabel {
  /** What the bidder sees in the select and the table. */
  readonly label: string
  /** The one-line hint under the select for that choice. */
  readonly hint: string
}

/**
 * Plain-English names for the API's `DocumentKind` values. The enum is the backend's; the
 * words here are the bidder's, so neither side has to know the other's.
 */
export const DOCUMENT_KIND_LABELS: Readonly<Record<DocumentKind, DocumentKindLabel>> = {
  company_evidence: {
    label: 'Company evidence',
    hint: 'Certificates, accounts, insurance, references — what proves your own facts.',
  },
  tender_document: {
    label: 'Tender document',
    hint: 'A procurement document the buyer published: specifications, contract terms.',
  },
  tender_notice: {
    label: 'Tender notice',
    hint: 'The contract notice itself, as published on TED or the national platform.',
  },
}

/**
 * What each pipeline stage means to the bidder. `uploaded → parsed → embedded → ready` is
 * the machine's vocabulary; these are the words a non-engineer can act on.
 */
export const DOCUMENT_STATUS_LABELS: Readonly<Record<DocumentStatus, string>> = {
  uploaded: 'Uploaded, reading…',
  parsed: 'Read, indexing…',
  embedded: 'Indexed, finishing…',
  ready: 'Ready',
  failed: 'Failed',
}

/**
 * The design system's status pairing: green for done, red for failed, and the one blue in
 * the system for "in progress" (`colors-status`). Never orange — that is not a status colour.
 */
export function statusBadgeTone(status: DocumentStatus): BadgeTone {
  if (status === 'ready') {
    return 'success'
  }
  if (status === 'failed') {
    return 'danger'
  }
  return 'info'
}
