'use client'

import { cn } from 'cn'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Icon } from '@/components/ui/icons'
import { Notice } from '@/components/ui/notice'
import { Select } from '@/components/ui/select'
import { formatPageList, shortDocumentName } from '@/lib/format'
import { useSignedUrl } from '@/lib/use-signed-url'
import { PdfPageView } from './pdf-page-view'

export interface SourceSelection {
  readonly documentId: string
  readonly page: number
}

/**
 * A document the panel can open. `BidDocumentResponse` satisfies it; so does a file the
 * check cited from the company's own documents, which is not part of the bid and whose page
 * count is unknown (`pages: 0`, shown as `p. N / ?`).
 */
export interface SourceDocument {
  readonly id: string
  readonly name: string
  readonly pages: number
  readonly unread_pages: readonly number[]
}

export interface SourcePanelProps {
  readonly documents: readonly SourceDocument[]
  readonly selection: SourceSelection | undefined
  readonly onSelect: (selection: SourceSelection) => void
  /** `phone` fills the Source tab; `drawer` is the overlay the desktop opens (ADR-0104). */
  readonly variant?: 'phone' | 'drawer'
  /**
   * The cited sentence to mark on the page — `drawer` only, and only while the citation being
   * shown is the one that opened it. The phone keeps the browser's own viewer, which cannot
   * mark anything.
   */
  readonly highlightQuote?: string
}

/**
 * The "Source" card of `Main.dc.html` (story S4.5.1): the document being read, a page
 * indicator with previous / next controls, the page itself, and the unread-pages note.
 *
 * The artboard draws this as a permanent 400 px column beside the matrix, one chip per
 * document across the top. Since ADR-0104 the desktop opens it as a drawer instead, and since
 * ADR-0105 **the chips are gone**: a drawer opened by a citation is showing one page of one
 * file, and a dozen chips above the viewer were furniture from the column it used to be. A
 * pack with more than one document gets a `Select` instead, which is one line rather than
 * twelve and is the design system's own control; a single-document pack gets nothing, because
 * the drawer's title already names the file.
 *
 * **Two renderers, on purpose.** `drawer` draws the page with pdf.js so the citation can be
 * marked on it (`pdf-page-view.tsx` carries that whole argument). `phone` keeps the browser's
 * own viewer in an `<iframe>` with a `#page=N` fragment, as ADR-0014 specified: a canvas and a
 * synthetic text layer are worse than the native viewer on a touch screen, where pinch-zoom
 * and the system's own reading tools are what a reader actually uses.
 */
export function SourcePanel({
  documents,
  selection,
  onSelect,
  variant = 'drawer',
  highlightQuote,
}: SourcePanelProps) {
  const current = documents.find((d) => d.id === selection?.documentId) ?? documents[0]
  const page = current === undefined ? 1 : clampPage(selection?.page ?? 1, current.pages)
  const { url, error, retry } = useSignedUrl(current?.id)
  const isPhone = variant === 'phone'

  if (current === undefined) {
    return (
      <Card title="Source" icon={<Icon name="file" size={20} />} padding={20}>
        <p className="m-0 text-text-secondary">This bid has no documents to show.</p>
      </Card>
    )
  }

  const pageUrl = url === undefined ? undefined : `${url}#page=${page}`
  const canGoBack = page > 1
  const canGoForward = current.pages === 0 || page < current.pages
  const controlSize = isPhone ? 'size-11' : 'size-8'
  const frameHeight = isPhone
    ? 'h-[60vh] min-h-[360px]'
    : 'h-[calc(100dvh-260px)] min-h-[420px]'

  return (
    <Card
      title="Source"
      icon={<Icon name="file" size={20} />}
      padding={20}
      actions={
        pageUrl !== undefined && (
          <a
            href={pageUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex min-h-8 items-center gap-1.5 text-[13px] font-medium leading-none text-text-secondary"
          >
            Open source page
            <Icon name="ext" size={14} />
          </a>
        )
      }
    >
      <div className="-mt-1.5 mb-3 flex flex-wrap items-end gap-3">
        {documents.length > 1 && (
          <Select
            label="Document"
            className="min-w-0 flex-1"
            options={documents.map((document) => ({
              value: document.id,
              label: shortDocumentName(document.name),
            }))}
            value={current.id}
            onValueChange={(documentId) => onSelect({ documentId, page: 1 })}
          />
        )}
        <div className="ml-auto flex items-center gap-1.5">
          <button
            type="button"
            aria-label="Previous page"
            disabled={!canGoBack}
            onClick={() => onSelect({ documentId: current.id, page: page - 1 })}
            className={cn(
              'inline-flex items-center justify-center rounded-md border border-border-default text-text-primary hover:bg-surface-hover disabled:cursor-not-allowed disabled:opacity-50',
              controlSize
            )}
          >
            <Icon name="chevL" size={16} />
          </button>
          <span className="[font:var(--type-mono)] tabular-nums" aria-live="polite">
            p. {page} / {current.pages > 0 ? current.pages : '?'}
          </span>
          <button
            type="button"
            aria-label="Next page"
            disabled={!canGoForward}
            onClick={() => onSelect({ documentId: current.id, page: page + 1 })}
            className={cn(
              'inline-flex items-center justify-center rounded-md border border-border-default text-text-primary hover:bg-surface-hover disabled:cursor-not-allowed disabled:opacity-50',
              controlSize
            )}
          >
            <Icon name="chevR" size={16} />
          </button>
        </div>
      </div>

      <div className="rounded-md border border-border-default bg-surface-sunken p-4">
        {url !== undefined && !isPhone ? (
          <PdfPageView
            url={url}
            documentId={current.id}
            documentName={current.name}
            page={page}
            quote={highlightQuote}
          />
        ) : pageUrl !== undefined ? (
          <iframe
            key={`${current.id}:${page}`}
            src={pageUrl}
            title={`${current.name}, page ${page}`}
            className={cn(
              'block w-full border border-border-default bg-surface-card shadow-sm',
              frameHeight
            )}
          />
        ) : error !== undefined ? (
          <div className="flex flex-col gap-3">
            <Notice tone="danger" title="The document could not be opened">
              {error}
            </Notice>
            <Button variant="secondary" size="sm" onClick={retry} className="self-start">
              Try again
            </Button>
          </div>
        ) : (
          <p
            role="status"
            className={cn('m-0 flex items-center justify-center text-text-muted', frameHeight)}
          >
            Opening {shortDocumentName(current.name)}…
          </p>
        )}
      </div>

      {current.unread_pages.length > 0 && (
        <div className="mt-3 flex items-center gap-2 [font:var(--type-body-sm)] text-text-muted">
          <Icon name="alert" size={14} />
          <span>
            {formatPageList(current.unread_pages)}{' '}
            {current.unread_pages.length === 1 ? 'has' : 'have'} no text layer and{' '}
            {current.unread_pages.length === 1 ? 'was' : 'were'} not read.
          </span>
        </div>
      )}
    </Card>
  )
}

function clampPage(page: number, total: number): number {
  const floor = Math.max(1, Math.trunc(page))
  return total > 0 ? Math.min(floor, total) : floor
}
