'use client'

import { useRef } from 'react'

import type { Citation } from '@/components/matrix/citation'
import { SheetContent, SheetDescription, SheetTitle, Sheet } from '@/components/ui/sheet'
import { shortDocumentName } from '@/lib/format'
import { SourcePanel, type SourceDocument, type SourceSelection } from './source-panel'

export interface SourceDrawerProps {
  readonly documents: readonly SourceDocument[]
  readonly selection: SourceSelection | undefined
  readonly onSelect: (selection: SourceSelection) => void
  /** The citation that opened the drawer, whose quote is marked on the page (ADR-0105). */
  readonly activeCitation: Citation | undefined
  readonly isOpen: boolean
  readonly onOpenChange: (isOpen: boolean) => void
}

/**
 * The source page, as an overlay that slides in from the right (ADR-0104).
 *
 * **This has no artboard.** `Main.dc.html` draws the source as a permanent 400 px column
 * beside the matrix, and `canvas.json`'s brief already records that column as the one screen
 * the design system had no component for. The drawing that sanctions this shape instead is
 * `Landing.dc.html`'s `ProductFrame` — the hero mock has always shown the matrix on the left
 * and the verdict alone on the right, with no source frame competing for that column — and
 * the motion and the scrim are the system's own dialog pattern, unchanged: 40 % ink under a
 * 280 ms `--ease-out` slide, with Radix supplying the focus trap, Escape and the dialog role.
 *
 * The panel inside is the same `SourcePanel` the phone tab and the page flow use; only its
 * `drawer` variant differs, and only in how tall the frame is. Opening this is what a
 * citation does — `handleCite` in `workspace-state.ts` — so a row's source and an answer's
 * source arrive the same way, which is what they did when it was a tab.
 *
 * Mounted only while open: the drawer is a portal over the page, so keeping a 1 000 px
 * iframe alive behind the scrim buys nothing. The page it was showing survives regardless,
 * because `selection` lives in the workspace and not in here.
 *
 * **Focus is returned by hand, and it has to be.** Radix's `DialogContent` ends its close by
 * calling `event.preventDefault()` and focusing `triggerRef.current` — the `DialogTrigger`
 * that opened it. This drawer has no trigger: it is opened from a citation anywhere in the
 * matrix, from a citation in a chat answer, and from the "Open the pack" control, so there is
 * no one element Radix could mean. With `triggerRef` empty its handler focuses nothing and
 * the default restore has already been prevented, which drops focus on the body — measured,
 * and the reason `bid-workspace.spec.ts` asserts the citation is focused after Escape. So the
 * element that had focus is recorded as the drawer opens (`onOpenAutoFocus` runs *before*
 * focus moves in) and restored as it closes.
 */
export function SourceDrawer({
  documents,
  selection,
  onSelect,
  activeCitation,
  isOpen,
  onOpenChange,
}: SourceDrawerProps) {
  const openerRef = useRef<HTMLElement | null>(null)
  const current = documents.find((d) => d.id === selection?.documentId) ?? documents[0]
  // Marked only while the page on screen is the page that was cited. Paging by hand clears
  // `activeCitation` in the workspace, so this turns itself off; the check is here for the
  // one case that does not go through `handleCite` at all — the drawer opened from "Open the
  // pack" while an earlier citation is still the active one.
  const highlightQuote =
    activeCitation !== undefined && activeCitation.page === selection?.page
      ? activeCitation.quote
      : undefined

  return (
    <Sheet open={isOpen} onOpenChange={onOpenChange}>
      <SheetContent
        widthClass="w-[min(920px,calc(100vw-64px))]"
        closeLabel="Close the source"
        className="gap-4 p-5"
        onOpenAutoFocus={() => {
          const active = document.activeElement
          openerRef.current = active instanceof HTMLElement ? active : null
        }}
        onCloseAutoFocus={(event) => {
          const opener = openerRef.current
          if (opener === null || !opener.isConnected) {
            return
          }
          event.preventDefault()
          opener.focus()
        }}
      >
        <div className="pr-11">
          <SheetTitle>
            {current === undefined ? 'Source' : shortDocumentName(current.name)}
          </SheetTitle>
          <SheetDescription>
            The page a citation points at. Paging here does not change the matrix.
          </SheetDescription>
        </div>
        <SourcePanel
          documents={documents}
          selection={selection}
          onSelect={onSelect}
          variant="drawer"
          highlightQuote={highlightQuote}
        />
      </SheetContent>
    </Sheet>
  )
}
