/**
 * What the workspace knows about itself, apart from how it is drawn.
 *
 * `bid-workspace.tsx` held the poll, six pieces of state, the derived counts, the two
 * handlers, the announcement and both complete layouts in one 709-line component — the only
 * god component in the tree, on the busiest screen in the product (audit M23). The split is
 * along the seam that was already there: this file is everything a layout would have to
 * compute, and `desktop-workspace.tsx` and `phone-workspace.tsx` are the two ways of drawing
 * it. Nothing about the behaviour changed; every docblock moved with the code it explains.
 */
'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { indexRowsByRequirement } from '@/components/matrix/row-status'
import type { AttachableDocument } from '@/components/matrix/row-attachments'
import { useRowEdits, type RowEditsController } from '@/components/matrix/use-row-edits'
import {
  useRowFeedback,
  type RowFeedbackController,
} from '@/components/matrix/use-row-feedback'
import { citableDocuments } from '@/components/matrix/source-documents'
import type { Citation } from '@/components/matrix/citation'
import type { RowReview } from '@/components/matrix/row-review-controls'
import type { SourceDocument, SourceSelection } from '@/components/pdf/source-panel'
import type { MatrixRow } from '@/lib/bids'
import { getBidConditional, isAwaitingReview, isBidSettled, type BidResponse } from '@/lib/bids'
import type { Conditional } from '@/lib/conditional-get'
import { listDocuments } from '@/lib/documents'
import { plural } from '@/lib/format'
import { SHELL_MEDIA_QUERY, useMediaQuery } from '@/lib/use-media-query'
import { usePolling } from '@/lib/use-polling'
import { BID_STATUS_LABELS } from './bid-status'
import { citationsOf, useBidChat, type BidChatController } from './use-bid-chat'

export type PhoneTab = 'matrix' | 'source' | 'verdict' | 'ask'

export const PHONE_TABS: readonly { value: PhoneTab; label: string }[] = [
  { value: 'matrix', label: 'Matrix' },
  { value: 'source', label: 'Source' },
  { value: 'verdict', label: 'Verdict' },
  { value: 'ask', label: 'Ask' },
]

/**
 * The company's own evidence, as the documents a reviewer may attach to a row (S4.5.2).
 *
 * Fetched once, and only while the bid is parked: a finished bid has nothing to attach to,
 * and a running one has no rows yet. Tender documents are deliberately not offered — a row
 * is proved by what the bidder holds, not by the buyer's own pack — and a document still
 * being parsed is not attachable, so both filters are applied here rather than in the panel.
 *
 * A failure costs the attach control and nothing else: the reviewer can still change a
 * status and give a reason, so the list stays empty and the panel says so.
 */
const ATTACHABLE_DOCUMENTS = 200

function useAttachableDocuments(isEnabled: boolean): readonly AttachableDocument[] {
  const [documents, setDocuments] = useState<readonly AttachableDocument[]>([])
  useEffect(() => {
    if (!isEnabled) {
      return
    }
    const controller = new AbortController()
    // One explicit page at the API's ceiling (M13). This is a picker inside a row editor,
    // not a list to browse: it has nowhere to put a "Load more", and asking for the maximum
    // is what the old unbounded query effectively did for every honest account.
    listDocuments({ limit: ATTACHABLE_DOCUMENTS, signal: controller.signal })
      .then((page) =>
        setDocuments(
          page.documents
            .filter((d) => d.kind === 'company_evidence' && d.status === 'ready')
            .map((d) => ({ id: d.id, name: d.name }))
        )
      )
      .catch(() => {
        // Attaching is one of three things a reviewer can do to a row; losing the list must
        // not take the other two with it.
      })
    return () => controller.abort()
  }, [isEnabled])
  return documents
}

/**
 * One sentence per change worth announcing — the stage moving on, requirements arriving, or
 * matrix rows arriving — for the page's single live region. Counts are announced at most
 * once per change so a screen reader is not read every poll, and the checked count is
 * announced against the total, because rows land lane by lane rather than all at once.
 */
function useStatusAnnouncement(bid: BidResponse): string {
  const [announcement, setAnnouncement] = useState('')
  const previousRef = useRef<Snapshot | undefined>(undefined)
  const { status } = bid
  const requirements = bid.requirements.length
  const rows = bid.matrix_rows.length
  useEffect(() => {
    const previous = previousRef.current
    const current: Snapshot = { status, requirements, rows }
    previousRef.current = current
    if (previous === undefined) {
      return
    }
    const sentence = describeChange(previous, current)
    if (sentence !== undefined) {
      setAnnouncement(sentence)
    }
  }, [status, requirements, rows])
  return announcement
}

interface Snapshot {
  readonly status: BidResponse['status']
  readonly requirements: number
  readonly rows: number
}

function describeChange(previous: Snapshot, current: Snapshot): string | undefined {
  if (previous.status !== current.status) {
    return `${BID_STATUS_LABELS[current.status].label}. ${plural(current.requirements, 'requirement')} extracted.`
  }
  if (previous.rows !== current.rows) {
    return `${current.rows} of ${plural(current.requirements, 'requirement')} checked so far.`
  }
  if (previous.requirements !== current.requirements) {
    return `${plural(current.requirements, 'requirement')} extracted so far.`
  }
  return undefined
}

function describeEmptyList(bid: BidResponse): string {
  if (bid.status === 'failed') {
    return 'The run stopped before any requirement was extracted.'
  }
  if (isBidSettled(bid)) {
    return 'No requirements were extracted from this pack. The footer of the problems line says what the run could not read.'
  }
  return `${BID_STATUS_LABELS[bid.status].label}… requirements appear here as soon as they are extracted, each with its page in the tender.`
}

/** Everything the two layouts draw, computed once. See the module docstring for the split. */
export interface WorkspaceState {
  /** The bid as it is right now: the reviewed answer if there is one, else the latest poll. */
  readonly bid: BidResponse
  /** Why the last refresh failed, if it did. The screen keeps the rows it already has. */
  readonly pollError: unknown
  /** `undefined` until the media query has answered — neither layout may be drawn yet. */
  readonly isDesktop: boolean | undefined

  readonly selection: SourceSelection | undefined
  readonly activeCitation: Citation | undefined
  readonly phoneTab: PhoneTab
  readonly setPhoneTab: (value: PhoneTab) => void
  /**
   * Whether the desktop's source drawer is open (ADR-0104). The phone keeps its Source tab;
   * this is the desktop's equivalent, and it is deliberately not a tab value — the drawer is
   * an overlay over the whole workspace, not one of a set of things the right rail can be.
   */
  readonly isSourceOpen: boolean
  readonly setSourceOpen: (isOpen: boolean) => void

  readonly announcement: string
  readonly edits: RowEditsController
  readonly feedback: RowFeedbackController
  readonly attachable: readonly AttachableDocument[]
  readonly chat: BidChatController

  readonly status: (typeof BID_STATUS_LABELS)[keyof typeof BID_STATUS_LABELS]
  readonly isRunning: boolean
  readonly totalPages: number
  readonly unreadPages: number
  readonly rowsByRequirement: ReadonlyMap<string, MatrixRow>
  readonly sourceDocuments: readonly SourceDocument[]
  readonly hasRows: boolean
  /** Only while the bid is parked; `undefined` leaves the matrix as S4.5.1 built it. */
  readonly review: RowReview | undefined

  readonly handleCite: (citation: Citation) => void
  readonly handleSelect: (next: SourceSelection) => void
  readonly onReviewed: (bid: BidResponse) => void
  readonly showVerdict: () => void
  readonly backToMatrix: () => void

  readonly emptyMessage: string | undefined
  readonly reviewNote: string
}

/**
 * The poll, the six pieces of state, the derived counts and the two handlers — once, for
 * whichever layout is drawn. Moved here whole from `bid-workspace.tsx` (M23); every comment
 * below explains the line it sits on and travelled with it.
 */
export function useWorkspaceState(initial: BidResponse): WorkspaceState {
  /**
   * What the last poll returned, with the `ETag` it came with (M13).
   *
   * A ref rather than state: it is read and written by the poll, never rendered, and a
   * module-level cache would outlive this workspace and leak between two bids in two tabs.
   * Echoing the tag turns an unchanged tick into a 304 with no body, where the body is every
   * requirement and every matrix row — 284 of each on the DE pack, every two seconds.
   */
  const held = useRef<Conditional<BidResponse> | undefined>(undefined)
  const fetchLatest = useCallback(
    async (signal: AbortSignal) => {
      const next = await getBidConditional(initial.id, held.current, signal)
      held.current = next
      // Unchanged, and `next.value` is the very object the last tick returned — so the
      // `useState` below sees no change and nothing re-renders.
      return next.value
    },
    [initial.id]
  )
  const { value: polled, error: pollError } = usePolling({
    initialValue: initial,
    fetchLatest,
    isSettled: isBidSettled,
  })
  // The server's answer to the review is newer than any poll, and polling has stopped by
  // then anyway — `complete` is settled. So a reviewed bid supersedes the polled one for the
  // rest of this mount. A 409 lands here too: the panel re-reads the bid and hands back what
  // is actually true, which is exactly what the screen should switch to (S4.5.3).
  const [reviewed, setReviewed] = useState<BidResponse | undefined>(undefined)
  const bid = reviewed ?? polled
  const isDesktop = useMediaQuery(SHELL_MEDIA_QUERY)
  const [selection, setSelection] = useState<SourceSelection | undefined>(undefined)
  const [activeCitation, setActiveCitation] = useState<Citation | undefined>(undefined)
  const [phoneTab, setPhoneTab] = useState<PhoneTab>('matrix')
  const [isSourceOpen, setSourceOpen] = useState(false)
  const announcement = useStatusAnnouncement(bid)
  const edits = useRowEdits(bid.matrix_rows)
  // Loaded once per bid and passed to both layouts and to the Ask panel, so thirty rows and
  // every chat answer share one request for the thumbs the bidder has already given (S4.6.3).
  const feedback = useRowFeedback(initial.id)
  const attachable = useAttachableDocuments(isAwaitingReview(bid))
  const chat = useBidChat(initial.id)

  const status = BID_STATUS_LABELS[bid.status]
  const isRunning = !isBidSettled(bid)
  const totalPages = bid.documents.reduce((sum, d) => sum + d.pages, 0)
  const unreadPages = bid.documents.reduce((sum, d) => sum + d.unread_pages.length, 0)
  const rowsByRequirement = useMemo(
    () => indexRowsByRequirement(bid.matrix_rows),
    [bid.matrix_rows]
  )
  // An answer may cite a company document no matrix row does; folding those in is what lets
  // its citation open the source panel rather than light up and go nowhere.
  const chatCitations = useMemo(() => citationsOf(chat.exchanges), [chat.exchanges])
  const sourceDocuments = useMemo(
    () => citableDocuments(bid.documents, bid.matrix_rows, chatCitations),
    [bid.documents, bid.matrix_rows, chatCitations]
  )
  const hasRows = bid.matrix_rows.length > 0
  // Only while the bid is parked: omitting it leaves the matrix exactly as S4.5.1 built it,
  // which is what a finished or still-running bid should show.
  const review = isAwaitingReview(bid) ? { edits, attachable } : undefined

  const handleCite = useCallback(
    (citation: Citation) => {
      // A page-less citation is a DUME/ESPD requirement: XML, no pages, and the panel shows
      // PDFs. `CitationLink` renders those as a label rather than a button so this cannot be
      // reached from the UI — the guard is here because the type allows it and opening the
      // panel on nothing would be worse than doing nothing.
      if (citation.page === null) return

      const document =
        sourceDocuments.find((d) => d.id === citation.documentId) ??
        sourceDocuments.find((d) => d.name === citation.documentName)
      setActiveCitation(citation)
      if (document !== undefined) {
        setSelection({ documentId: document.id, page: citation.page })
      }
      // Both layouts answer a citation the same way: the phone moves to its Source tab, the
      // desktop slides the drawer in over the verdict rail.
      setPhoneTab('source')
      setSourceOpen(true)
    },
    [sourceDocuments]
  )

  const handleSelect = useCallback((next: SourceSelection) => {
    setSelection(next)
    setActiveCitation(undefined)
  }, [])

  const emptyMessage = describeEmptyList(bid)
  const reviewNote =
    bid.verdict === null
      ? 'The verdict is written once checking has finished.'
      : 'Confirm the verdict, or override it with a reason. Your row edits go with it.'
  const showVerdict = useCallback(() => setPhoneTab('verdict'), [])
  const backToMatrix = useCallback(() => setPhoneTab('matrix'), [])

  return {
    bid,
    pollError,
    isDesktop,
    selection,
    activeCitation,
    phoneTab,
    setPhoneTab,
    isSourceOpen,
    setSourceOpen,
    announcement,
    edits,
    feedback,
    attachable,
    chat,
    status,
    isRunning,
    totalPages,
    unreadPages,
    rowsByRequirement,
    sourceDocuments,
    hasRows,
    review,
    handleCite,
    handleSelect,
    onReviewed: setReviewed,
    showVerdict,
    backToMatrix,
    emptyMessage,
    reviewNote,
  }
}
