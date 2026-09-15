'use client'

/**
 * The three steps of `NewBid.dc.html`, in one flow (story S4.3.1).
 *
 * 1. **Find it on TED** — search by what you do and where, pick a notice.
 * 2. **Upload the pack** — the buyer's platform holds the files; Crossbid never fetches
 *    from it (the no-scraping rule), so the bidder drops them in here.
 * 3. **Start** — confirm what the agent will be told, and run it.
 *
 * **Picking a notice moves the flow on; it does not submit anything.** Nothing is created
 * until Start, so Change is always available and costs nothing. The notice lives in this
 * component's state rather than in the URL because it is half a form, not a page: a
 * refreshed `/bids/new?notice=…` that restored the choice but not the uploads would be a
 * worse lie than starting over.
 *
 * **Search can be skipped.** A bidder who already has the publication number — from an
 * email, or from the buyer directly — should not be made to search for a notice they can
 * already name, so the step offers a way past itself and the start form keeps its own
 * fields. That is also what keeps this screen working the day TED is down.
 *
 * **Steps 2 and 3 share one list.** The panel owns the only `GET /documents` on the page and
 * reports every change up to here — an upload accepted, a row polled to ready — and the
 * start form renders from that, so a file dropped in step 2 is in step 3's checklist before
 * the bidder has scrolled to it. Two components each fetching on mount was how the flow
 * shipped, and it meant the form's list was frozen from before the first upload
 * (2026-09-15). The panel also uploads as `tender_document` here rather than its own
 * evidence default, because a pack is tender documents and the start step keeps nothing else.
 */
import { useEffect, useState } from 'react'

import { FoundOnTed } from '@/components/bids/found-on-ted'
import { StartBidForm } from '@/components/bids/start-bid-form'
import { TenderSearch } from '@/components/bids/tender-search'
import { DocumentsPanel, type DocumentListState } from '@/components/documents/documents-panel'
import { Badge } from '@/components/ui/badge'
import { loadProfile } from '@/lib/companies'
import type { DocumentKind } from '@/lib/documents'
import type { TedNotice } from '@/lib/tenders'

/** What a file in a pack is, until the bidder says otherwise; see the docblock above. */
const PACK_DEFAULT_KIND: DocumentKind = 'tender_document'

export function NewBidFlow() {
  const language = useBidderLanguage()
  const [notice, setNotice] = useState<TedNotice | undefined>(undefined)
  const [searchSkipped, setSearchSkipped] = useState(false)
  const [documentList, setDocumentList] = useState<DocumentListState>({ phase: 'loading' })
  const past = notice !== undefined || searchSkipped

  if (!past) {
    return (
      <div className="flex flex-col gap-5">
        <Step number={1} title="Find the tender on TED" />
        <TenderSearch language={language} onPick={setNotice} />
        <p className="m-0 [font:var(--type-body-sm)] text-text-muted">
          Already have the publication number?{' '}
          <button
            type="button"
            className="rounded-sm underline underline-offset-2 hover:text-text-primary"
            onClick={() => setSearchSkipped(true)}
          >
            Enter it yourself
          </button>
          .
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-8">
      {notice !== undefined && (
        <FoundOnTed notice={notice} onChange={() => setNotice(undefined)} />
      )}
      {notice === undefined && (
        <p className="m-0 [font:var(--type-body-sm)] text-text-muted">
          Entering the notice by hand.{' '}
          <button
            type="button"
            className="rounded-sm underline underline-offset-2 hover:text-text-primary"
            onClick={() => setSearchSkipped(false)}
          >
            Search TED instead
          </button>
          .
        </p>
      )}

      <div className="flex flex-col gap-4">
        <Step number={2} title="Upload the pack" />
        <DocumentsPanel defaultKind={PACK_DEFAULT_KIND} onDocumentsChange={setDocumentList} />
      </div>

      <div className="flex flex-col gap-4">
        <Step number={3} title="Start" />
        <StartBidForm notice={notice} documentList={documentList} />
      </div>
    </div>
  )
}

/**
 * The bidder's explanation language, for TED's own title translations (S1.2.1).
 *
 * Fetched here rather than threaded down from the page, which is a server component and has
 * no session to ask. `undefined` until it arrives and if it never does: the search still
 * works, it just shows titles in the notice's own language, which is the honest fallback.
 */
function useBidderLanguage(): string | undefined {
  const [language, setLanguage] = useState<string | undefined>(undefined)

  useEffect(() => {
    const controller = new AbortController()
    loadProfile(controller.signal)
      .then(({ profile }) => setLanguage(profile?.language))
      .catch(() => undefined)
    return () => controller.abort()
  }, [])

  return language
}

function Step({ number, title }: Readonly<{ number: number; title: string }>) {
  return (
    <div className="flex items-center gap-3">
      <Badge tone="info" pill={false}>
        Step {number} of 3
      </Badge>
      <h2 className="m-0 text-[length:var(--text-md)] font-semibold text-text-primary">
        {title}
      </h2>
    </div>
  )
}
