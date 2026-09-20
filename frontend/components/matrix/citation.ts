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
  /**
   * The words this citation points at, for the source drawer to mark on the page (ADR-0105).
   *
   * Every citation has one — `Evidence.quote` and `Requirement.source_text` are both required
   * and both verbatim — but it is optional here because a `Citation` is an address and a
   * caller that only has the address is still making a valid one.
   */
  readonly quote?: string
}

/**
 * Two citations point at the same place: the same file, the same page.
 *
 * **The quote is deliberately not compared.** This decides which citation the matrix draws as
 * active, and two requirements citing two clauses of one page should both light up when that
 * page is open — which is what "the panel is showing this" means. Comparing the quote as well
 * would be a different feature, and not one anybody asked for.
 */
export function isSameCitation(a: Citation | undefined, b: Citation): boolean {
  return a !== undefined && a.documentName === b.documentName && a.page === b.page
}
