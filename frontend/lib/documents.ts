/**
 * Typed calls and client-side rules for the `/documents` routes (story S4.2.2).
 *
 * The types come straight from the generated schema, so a field the backend renames stops
 * compiling here. The validation mirrors `backend/crossbid/routers/documents.py` on purpose:
 * refusing a 60 MB scan before it leaves the browser is kinder than a 413 after the upload,
 * but the server stays the authority — its `detail` is shown whenever it disagrees.
 */
import type { components } from './api'
import { apiRequest } from './api-client'

export type DocumentResponse = components['schemas']['DocumentResponse']
export type DocumentKind = components['schemas']['DocumentKind']
export type DocumentStatus = components['schemas']['DocumentStatus']

export const DOCUMENT_KINDS: readonly DocumentKind[] = [
  'company_evidence',
  'tender_document',
  'tender_notice',
]

/** Same cap as `MAX_UPLOAD_MEGABYTES` in the router; the message below quotes it. */
export const MAX_UPLOAD_MEGABYTES = 50
export const MAX_UPLOAD_BYTES = MAX_UPLOAD_MEGABYTES * 1024 * 1024

const PDF_SUFFIX = '.pdf'
/** Declared types a browser may send for a genuine PDF; the server checks the magic bytes. */
const ACCEPTED_CONTENT_TYPES: ReadonlySet<string> = new Set([
  'application/pdf',
  'application/x-pdf',
  'application/octet-stream',
  '',
])

const SETTLED_STATUSES: ReadonlySet<DocumentStatus> = new Set(['ready', 'failed'])

/** `true` once the pipeline has finished with the document, for better or worse. */
export function isDocumentSettled(document: DocumentResponse): boolean {
  return SETTLED_STATUSES.has(document.status)
}

export function isDocumentKind(value: unknown): value is DocumentKind {
  return typeof value === 'string' && (DOCUMENT_KINDS as readonly string[]).includes(value)
}

/**
 * The reason a file cannot be uploaded, in the bidder's words, or `undefined` when it can.
 * Checked in the order the server checks, so both sides name the same problem first.
 */
export function validateUploadFile(file: File | null | undefined): string | undefined {
  if (file === null || file === undefined || file.name.trim().length === 0) {
    return 'Choose a PDF to upload.'
  }
  if (!file.name.toLowerCase().endsWith(PDF_SUFFIX)) {
    return `Only PDF files are accepted; the filename must end in ${PDF_SUFFIX}.`
  }
  if (!ACCEPTED_CONTENT_TYPES.has(file.type.toLowerCase())) {
    return 'Only PDF files are accepted; this file is another type.'
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return `The file is larger than ${MAX_UPLOAD_MEGABYTES} MB.`
  }
  if (file.size === 0) {
    return 'The file is empty.'
  }
  return undefined
}

/** Every document of the company, newest first. */
export async function listDocuments(
  signal?: AbortSignal
): Promise<readonly DocumentResponse[]> {
  const response = await apiRequest('get', '/documents', { signal })
  return response.documents
}

/** One document's current state — the call the poll repeats. */
export function getDocument(
  documentId: string,
  signal?: AbortSignal
): Promise<DocumentResponse> {
  return apiRequest('get', '/documents/{document_id}', {
    path: { document_id: documentId },
    signal,
  })
}

/**
 * Sends the PDF and resolves with the 202 row (`status: "uploaded"`). The field names are
 * the multipart schema's: `file` and `kind`.
 */
export function uploadDocument(file: File, kind: DocumentKind): Promise<DocumentResponse> {
  const formData = new FormData()
  formData.append('file', file, file.name)
  formData.append('kind', kind)
  return apiRequest('post', '/documents', { formData })
}
