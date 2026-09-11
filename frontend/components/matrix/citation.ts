/** Where a requirement was read: the document by name and the 1-indexed page. */
export interface Citation {
  readonly documentName: string
  readonly page: number
}

export function isSameCitation(a: Citation | undefined, b: Citation): boolean {
  return a !== undefined && a.documentName === b.documentName && a.page === b.page
}
