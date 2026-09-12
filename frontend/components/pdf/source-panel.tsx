'use client'

import { cn } from 'cn'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Icon } from '@/components/ui/icons'
import { Notice } from '@/components/ui/notice'
import { formatPageList, shortDocumentName } from '@/lib/format'
import { useSignedUrl } from '@/lib/use-signed-url'

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
  /** `phone` fills the Source tab; `panel` is the 400 px card beside the matrix. */
  readonly variant?: 'panel' | 'phone'
}

/**
 * The 400 px "Source" card of `Main.dc.html` (story S4.5.1): document tabs, a page
 * indicator with 32 px previous / next controls, the PDF, and the unread-pages note.
 *
 * The PDF is the browser's own viewer — an `<iframe>` on the document's signed URL with a
 * `#page=N` fragment (ADR-0014: no PDF library until the native viewer proves
 * insufficient). The iframe is keyed on document and page, so a citation click remounts it
 * and the viewer opens the cited page rather than staying where it was. The URL is
 * refreshed before it expires (`useSignedUrl`).
 */
export function SourcePanel({
  documents,
  selection,
  onSelect,
  variant = 'panel',
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
      <div className="-mt-1.5 mb-3 flex flex-wrap items-center gap-1.5">
        <div role="group" aria-label="Documents" className="flex min-w-0 flex-wrap gap-1.5">
          {documents.map((document) => {
            const isCurrent = document.id === current.id
            return (
              <Button
                key={document.id}
                size="sm"
                variant={isCurrent ? 'secondary' : 'ghost'}
                aria-pressed={isCurrent}
                title={document.name}
                onClick={() => onSelect({ documentId: document.id, page: 1 })}
                className={cn(isPhone && 'h-11')}
              >
                {shortDocumentName(document.name)}
              </Button>
            )
          })}
        </div>
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
        {pageUrl !== undefined ? (
          <iframe
            key={`${current.id}:${page}`}
            src={pageUrl}
            title={`${current.name}, page ${page}`}
            className={cn(
              'block w-full border border-border-default bg-surface-card shadow-sm',
              isPhone ? 'h-[60vh] min-h-[360px]' : 'h-[560px]'
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
            className={cn(
              'm-0 flex items-center justify-center text-text-muted',
              isPhone ? 'h-[60vh] min-h-[360px]' : 'h-[560px]'
            )}
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
