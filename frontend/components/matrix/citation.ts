/**
 * Where a requirement or a piece of evidence was read: the document, and the 1-indexed page.
 *
 * `page` is **null for a requirement that came from a DUME/ESPD request**. That file is XML,
 * it has no pages, and the source panel renders PDFs — so there is nothing to jump to and the
 * citation must not offer to. The backend enforces the same rule from the other side: a
 * requirement's page is present exactly when its source has pages, in the model and in a
 * check constraint. A page-less citation renders as a label, never as a link.
 */
export interface Citation {
  readonly documentName: string
  readonly page: number | null
  /**
   * The document's id when the citation knows it — evidence carries one, an extracted
   * requirement is matched by name. It settles which file to open when two documents in the
   * bid share a filename.
   */
  readonly documentId?: string
  /** The eCertis criterion a page-less (ESPD) citation points at, shown in place of a page. */
  readonly criterionId?: string
}

export function isSameCitation(a: Citation | undefined, b: Citation): boolean {
  return a !== undefined && a.documentName === b.documentName && a.page === b.page
}
