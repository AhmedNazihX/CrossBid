import type { BidDocument, ExtractionProblem } from '@/lib/bids'
import { plural } from '@/lib/format'

/**
 * The muted footer line of `Main.dc.html`'s table: what the run could not do, as counts a
 * reviewer can act on — unread pages, rows dropped for want of a verbatim quote, sections the
 * model could not read. Built from the closed `ExtractionProblemReason` enum and the
 * documents' unread pages; never from document text (ADR-0008).
 */
export function describeProblems(
  problems: readonly ExtractionProblem[],
  documents: readonly BidDocument[]
): readonly string[] {
  const unreadPages = documents.reduce((sum, document) => sum + document.unread_pages.length, 0)
  const count = (...reasons: readonly ExtractionProblem['reason'][]) =>
    problems.filter((problem) => reasons.includes(problem.reason)).length

  const noQuote = count('no_verbatim_quote')
  const untranslated = count('missing_translation')
  const invalid = count('invalid_row', 'invalid_criterion_id')
  const sections = count('section_failed', 'model_error', 'unwrappable_section')
  const documentsFailed = count('unreadable_document', 'unparseable_document')
  const planted = count('planted_instruction')
  const notIndexed = count('indexing_failed')

  return [
    planted > 0
      ? `${plural(planted, 'page')} carrying text addressed to the agent — read before trusting`
      : undefined,
    unreadPages > 0
      ? `${plural(unreadPages, 'page')} without a text layer not read`
      : undefined,
    noQuote > 0
      ? `${plural(noQuote, 'row')} dropped — quote not found on the cited page`
      : undefined,
    untranslated > 0 ? `${plural(untranslated, 'row')} not yet translated` : undefined,
    invalid > 0 ? `${plural(invalid, 'row')} failed validation` : undefined,
    sections > 0 ? `${plural(sections, 'section')} the model could not read` : undefined,
    documentsFailed > 0
      ? `${plural(documentsFailed, 'document')} could not be parsed`
      : undefined,
    // ADR-0057: the document was read and its requirements extracted, but its passages never
    // reached the tender corpus — so a question about it, or a check that would have quoted
    // it, finds nothing. Said out loud because silence is how the empty corpus went unnoticed.
    notIndexed > 0
      ? `${plural(notIndexed, 'document')} not searchable — checks and questions cannot quote from ${notIndexed === 1 ? 'it' : 'them'}`
      : undefined,
  ].filter((line): line is string => line !== undefined)
}
