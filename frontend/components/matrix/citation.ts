/** Where a requirement or a piece of evidence was read: the document, and the 1-indexed page. */
export interface Citation {
  readonly documentName: string
  readonly page: number
  /**
   * The document's id when the citation knows it — evidence carries one, an extracted
   * requirement is matched by name. It settles which file to open when two documents in the
   * bid share a filename.
   */
  readonly documentId?: string
}

export function isSameCitation(a: Citation | undefined, b: Citation): boolean {
  return a !== undefined && a.documentName === b.documentName && a.page === b.page
}
