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
export type DocumentUrlResponse = components['schemas']['DocumentUrlResponse']

/**
 * The kinds `POST /bids` accepts as a tender pack; company evidence is refused with 422.
 *
 * `tender_espd_request` belongs here for the reason `readmodel/bids.py` gives about its own
 * copy of this set: the published ESPD request is one of the tender's files, and omitting it
 * is "the one way to upload a DUME and never use it". This set omitted it until 2026-09-14,
 * which is exactly what that comment warned about — see the note on `DOCUMENT_KINDS`.
 */
export const TENDER_DOCUMENT_KINDS: ReadonlySet<DocumentKind> = new Set([
  'tender_document',
  'tender_notice',
  'tender_espd_request',
])

/**
 * The choices in the upload form's type select, in the order they are offered.
 *
 * `tender_espd_request` was missing here until 2026-09-14 while the router, the graph, the
 * matrix and `DOCUMENT_KIND_LABELS` all already handled it — so the DUME could not be
 * uploaded through the product at all, and the eCertis card it exists to light up stayed
 * dark end to end (ADR-0022). Any new `DocumentKind` must be added here to be reachable.
 */
export const DOCUMENT_KINDS: readonly DocumentKind[] = [
  'company_evidence',
  'tender_document',
  'tender_notice',
  'tender_espd_request',
]

/** Same cap as `MAX_UPLOAD_MEGABYTES` in the router; the message below quotes it. */
export const MAX_UPLOAD_MEGABYTES = 50
export const MAX_UPLOAD_BYTES = MAX_UPLOAD_MEGABYTES * 1024 * 1024

/**
 * `safe_xml.MAX_XML_BYTES`. An ESPD request is fully parsed inside the request rather than in
 * a background task, so it is capped far below the PDF limit; the server's message quotes the
 * figure in bytes, and this one matches it.
 */
export const MAX_ESPD_BYTES = 4 * 1024 * 1024

const PDF_SUFFIX = '.pdf'
const XML_SUFFIX = '.xml'

/** What a browser or `curl` sends when it does not know better; allowed for either shape. */
const GENERIC_CONTENT_TYPES: readonly string[] = ['application/octet-stream', '']

/** Declared types a browser may send for a genuine PDF; the server checks the magic bytes. */
const PDF_CONTENT_TYPES: ReadonlySet<string> = new Set([
  'application/pdf',
  'application/x-pdf',
  ...GENERIC_CONTENT_TYPES,
])

/** Declared types for an ESPD request; the server settles it on the root element. */
const XML_CONTENT_TYPES: ReadonlySet<string> = new Set([
  'application/xml',
  'text/xml',
  'application/espd+xml',
  ...GENERIC_CONTENT_TYPES,
])

/**
 * One upload shape: what the file input offers, and the four refusals in the server's words.
 *
 * There are two, keyed by kind exactly as `XML_KINDS` keys them in the router. Keeping the
 * messages identical to the server's `*_DETAIL` constants is the point of this module — the
 * bidder sees the same sentence whichever side notices first.
 */
interface UploadShape {
  /** The file input's `accept`, so the picker greys out what would be refused anyway. */
  readonly accept: string
  /** The hint under the file input. */
  readonly hint: string
  readonly suffix: string
  readonly contentTypes: ReadonlySet<string>
  readonly maxBytes: number
  readonly missing: string
  readonly wrongSuffix: string
  readonly wrongType: string
  readonly tooLarge: string
}

const PDF_UPLOAD: UploadShape = {
  accept: 'application/pdf,.pdf',
  hint: `One PDF, up to ${MAX_UPLOAD_MEGABYTES} MB.`,
  suffix: PDF_SUFFIX,
  contentTypes: PDF_CONTENT_TYPES,
  maxBytes: MAX_UPLOAD_BYTES,
  missing: 'Choose a PDF to upload.',
  wrongSuffix: `Only PDF files are accepted; the filename must end in ${PDF_SUFFIX}.`,
  wrongType: 'Only PDF files are accepted; the file was sent as another type.',
  tooLarge: `The file is larger than ${MAX_UPLOAD_MEGABYTES} MB.`,
}

const ESPD_UPLOAD: UploadShape = {
  accept: 'application/xml,text/xml,.xml',
  hint: "One XML file — the buyer's published ESPD request (DUME).",
  suffix: XML_SUFFIX,
  contentTypes: XML_CONTENT_TYPES,
  maxBytes: MAX_ESPD_BYTES,
  missing: 'Choose the ESPD request XML to upload.',
  wrongSuffix: `An ESPD request must be an XML file; the filename must end in ${XML_SUFFIX}.`,
  wrongType: 'An ESPD request must be sent as XML; the file was sent as another type.',
  tooLarge: `An ESPD request larger than ${MAX_ESPD_BYTES} bytes is not read; check the file.`,
}

/** The shape a kind is uploaded in. Mirrors `XML_KINDS` in `routers/documents.py`. */
export function uploadShapeFor(kind: DocumentKind): UploadShape {
  return kind === 'tender_espd_request' ? ESPD_UPLOAD : PDF_UPLOAD
}

/**
 * Whether a kind is paginated at all.
 *
 * An ESPD request is an XML form, and `ingestion/pipeline.py` stores zero pages for it as
 * "the honest count". Printing that `0` would tell the bidder we read the file and found no
 * pages, when the truth is that pages do not apply — the same confusion ADR-0022 removed
 * from citations by making a requirement's `page` nullable. Views show `—` instead.
 */
export function hasPages(kind: DocumentKind): boolean {
  return kind !== 'tender_espd_request'
}

const SETTLED_STATUSES: ReadonlySet<DocumentStatus> = new Set(['ready', 'failed'])

/** `true` once the pipeline has finished with the document, for better or worse. */
export function isDocumentSettled(document: DocumentResponse): boolean {
  return SETTLED_STATUSES.has(document.status)
}

export function isDocumentKind(value: unknown): value is DocumentKind {
  return typeof value === 'string' && (DOCUMENT_KINDS as readonly string[]).includes(value)
}

/**
 * The reason a file cannot be uploaded as `kind`, in the bidder's words, or `undefined` when
 * it can. Checked in the order the server checks, so both sides name the same problem first.
 *
 * The rules differ by kind: an ESPD request is XML capped at four megabytes, everything else
 * is a PDF capped at fifty. Neither side can settle the question from the filename alone —
 * the server sniffs the magic bytes of a PDF and fully parses an ESPD request — so this is a
 * courtesy that saves an upload, never the authority.
 */
export function validateUploadFile(
  file: File | null | undefined,
  kind: DocumentKind
): string | undefined {
  const shape = uploadShapeFor(kind)
  if (file === null || file === undefined || file.name.trim().length === 0) {
    return shape.missing
  }
  if (!file.name.toLowerCase().endsWith(shape.suffix)) {
    return shape.wrongSuffix
  }
  if (!shape.contentTypes.has(file.type.toLowerCase())) {
    return shape.wrongType
  }
  if (file.size > shape.maxBytes) {
    return shape.tooLarge
  }
  if (file.size === 0) {
    return 'The uploaded file is empty.'
  }
  return undefined
}

/**
 * Whether a document can be deleted at all (ADR-0088).
 *
 * The one definition. The rule is the API's — it answers 409 for a document a bid has
 * claimed, because that run's requirements cite its pages — and the screen mirrors it so a
 * bidder is never offered a control whose only outcome is a refusal. It lived in three places
 * for about an hour, and a mutation test proved that two of them were never exercised.
 */
export function isDeletable(document: DocumentResponse): boolean {
  return document.bid_id === null
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

/**
 * A short-lived URL for the document's file, for the browser's own PDF viewer (S4.5.1's
 * source panel). `expires_at` says when to ask again; the caller appends `#page=N`.
 */
export function getDocumentUrl(
  documentId: string,
  signal?: AbortSignal
): Promise<DocumentUrlResponse> {
  return apiRequest('get', '/documents/{document_id}/url', {
    path: { document_id: documentId },
    signal,
  })
}

/**
 * Deletes a document and the file behind it. Resolves on the API's 204.
 *
 * Throws `ApiError` with `status === 409` when a bid has already claimed the document:
 * its pages are cited by that run's requirements, so the server keeps it and says why.
 * A 404 means the id is unknown or belongs to another company — the same answer either
 * way, by design.
 */
export function deleteDocument(documentId: string, signal?: AbortSignal): Promise<void> {
  return apiRequest('delete', '/documents/{document_id}', {
    path: { document_id: documentId },
    signal,
  })
}
