'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Icon } from '@/components/ui/icons'
import { Input } from '@/components/ui/input'
import { Notice } from '@/components/ui/notice'
import { Select } from '@/components/ui/select'
import { Tag } from '@/components/ui/tag'
import { describeApiError } from '@/lib/api-client'
import { startBid } from '@/lib/bids'
import {
  hasPages,
  listDocuments,
  TENDER_DOCUMENT_KINDS,
  type DocumentResponse,
} from '@/lib/documents'
import { plural } from '@/lib/format'
import {
  DOCUMENT_KIND_LABELS,
  DOCUMENT_STATUS_LABELS,
  statusBadgeTone,
} from '@/components/documents/document-labels'

type SourceLanguage = 'fr' | 'de' | 'en'

const SOURCE_LANGUAGES: readonly { value: SourceLanguage; label: string }[] = [
  { value: 'fr', label: 'French (FR)' },
  { value: 'de', label: 'German (DE)' },
  { value: 'en', label: 'English (EN)' },
]

type ListState =
  | { readonly phase: 'loading' }
  | { readonly phase: 'failed'; readonly message: string }
  | { readonly phase: 'loaded'; readonly documents: readonly DocumentResponse[] }

/**
 * The start step — the third card of `NewBid.dc.html` (story S4.5.1 brings it forward from
 * S4.3.1, whose TED search and in-flow upload land in Increment 4).
 *
 * A notice number, the tender's language, a checklist of the company's tender documents
 * (`GET /documents`, kinds `tender_document` / `tender_notice`, not yet attached to a bid),
 * and Start analysis → `POST /bids` → the workspace. Documents still processing are listed
 * but cannot be chosen, with their status; the API's `detail` is shown on any refusal.
 */
export function StartBidForm() {
  const router = useRouter()
  const [listState, setListState] = useState<ListState>({ phase: 'loading' })
  const [noticeNumber, setNoticeNumber] = useState('')
  const [sourceLanguage, setSourceLanguage] = useState<SourceLanguage>('fr')
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set())
  const [error, setError] = useState<string | undefined>(undefined)
  const [isStarting, setIsStarting] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    listDocuments(controller.signal)
      .then((documents) => setListState({ phase: 'loaded', documents }))
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) {
          setListState({ phase: 'failed', message: describeApiError(cause) })
        }
      })
    return () => controller.abort()
  }, [])

  const tenderDocuments = useMemo(
    () =>
      listState.phase === 'loaded'
        ? listState.documents.filter(
            (document) => TENDER_DOCUMENT_KINDS.has(document.kind) && document.bid_id === null
          )
        : [],
    [listState]
  )
  const readyCount = tenderDocuments.filter((document) => document.status === 'ready').length
  const canStart = selected.size > 0 && noticeNumber.trim().length > 0 && !isStarting

  function toggle(documentId: string, isChecked: boolean) {
    setSelected((current) => {
      const next = new Set(current)
      if (isChecked) {
        next.add(documentId)
      } else {
        next.delete(documentId)
      }
      return next
    })
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!canStart) {
      return
    }
    setError(undefined)
    setIsStarting(true)
    try {
      const bid = await startBid({
        notice_number: noticeNumber.trim(),
        document_ids: [...selected],
        source_language: sourceLanguage,
      })
      router.push(`/bids/${encodeURIComponent(bid.id)}`)
    } catch (cause) {
      setError(describeApiError(cause))
      setIsStarting(false)
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      aria-busy={isStarting}
      noValidate
      className="flex flex-col gap-5"
    >
      <Notice>
        Searching TED and uploading the pack from this screen arrive with the full flow
        (S4.3.1). Until then, upload the tender&rsquo;s documents on the{' '}
        <Link href="/company" className="underline">
          Company profile
        </Link>{' '}
        page with the type <b className="font-medium">Tender document</b> — and, where the buyer
        published one, the <b className="font-medium">ESPD / DUME request</b> XML, which names
        the EU criteria outright — then start here.
      </Notice>

      <Card
        title="Start"
        icon={<Icon name="spark" size={20} />}
        actions={<Tag>{`${selected.size} of ${readyCount} ready selected`}</Tag>}
      >
        <div className="grid gap-4 shell:grid-cols-2">
          <Input
            label="Notice number"
            name="notice_number"
            value={noticeNumber}
            onChange={(event) => setNoticeNumber(event.target.value)}
            placeholder="618320-2026"
            autoComplete="off"
            required
            hint="The TED publication number of the tender."
          />
          <Select
            label="Tender language"
            name="source_language"
            value={sourceLanguage}
            onValueChange={setSourceLanguage}
            options={SOURCE_LANGUAGES}
            hint="The language the procurement documents are written in."
          />
        </div>

        <fieldset className="m-0 mt-5 min-w-0 border-0 p-0">
          <legend className="mb-2.5 text-[13px] font-medium leading-none text-text-primary">
            Procurement documents
          </legend>
          <DocumentChecklist
            listState={listState}
            documents={tenderDocuments}
            selected={selected}
            onToggle={toggle}
            disabled={isStarting}
          />
        </fieldset>

        <div className="mt-5 flex flex-col gap-4 border-t border-border-default pt-5 shell:flex-row shell:items-center">
          <div className="flex flex-1 flex-col gap-1">
            <span className="font-medium">
              Explain the requirements in your company&rsquo;s language
            </span>
            <span className="[font:var(--type-body-sm)] text-text-muted">
              Set on your company profile. About five minutes for a 200-page pack. The agent
              stops before any verdict and waits for your confirmation.
            </span>
          </div>
          <Button
            type="submit"
            size="lg"
            disabled={!canStart}
            icon={<Icon name="spark" size={16} />}
            className="w-full shell:w-auto"
          >
            {isStarting ? 'Starting…' : 'Start analysis'}
          </Button>
        </div>

        {error !== undefined && (
          <Notice tone="danger" title="The bid was not started" className="mt-4">
            {error}
          </Notice>
        )}
      </Card>
    </form>
  )
}

function DocumentChecklist({
  listState,
  documents,
  selected,
  onToggle,
  disabled,
}: {
  readonly listState: ListState
  readonly documents: readonly DocumentResponse[]
  readonly selected: ReadonlySet<string>
  readonly onToggle: (documentId: string, isChecked: boolean) => void
  readonly disabled: boolean
}) {
  if (listState.phase === 'loading') {
    return (
      <p role="status" className="m-0 [font:var(--type-body-sm)] text-text-muted">
        Loading your documents…
      </p>
    )
  }
  if (listState.phase === 'failed') {
    return (
      <Notice tone="danger" title="Your documents could not be loaded">
        {listState.message}
      </Notice>
    )
  }
  if (documents.length === 0) {
    return (
      <p className="m-0 text-text-secondary">
        No tender documents are waiting for a bid. Upload the pack on the{' '}
        <Link href="/company" className="underline">
          Company profile
        </Link>{' '}
        page first — the RC, the specifications, the notice, any annexes, and the buyer&rsquo;s
        ESPD request if there is one.
      </p>
    )
  }
  return (
    <ul className="m-0 flex list-none flex-col p-0">
      {documents.map((document, index) => {
        const isReady = document.status === 'ready'
        return (
          <li
            key={document.id}
            className={
              index < documents.length - 1
                ? 'flex items-center gap-3 border-b border-border-default py-3.5'
                : 'flex items-center gap-3 py-3.5'
            }
          >
            <Checkbox
              name="document_ids"
              value={document.id}
              checked={selected.has(document.id)}
              disabled={disabled || !isReady}
              onChange={(event) => onToggle(document.id, event.target.checked)}
              label={document.name}
              description={describeDocument(document)}
              className="min-w-0 flex-1"
            />
            <Badge tone={statusBadgeTone(document.status)} size="sm">
              {DOCUMENT_STATUS_LABELS[document.status]}
            </Badge>
          </li>
        )
      })}
    </ul>
  )
}

/**
 * The one line under a document's checkbox: what it is, and — only where pages exist — how
 * many were read and how many carry no text layer. An ESPD request is XML with no pages, so
 * it names only its type rather than claiming zero of something never counted.
 */
function describeDocument(document: DocumentResponse): string {
  const parts = [DOCUMENT_KIND_LABELS[document.kind].label]
  if (document.status === 'ready' && hasPages(document.kind)) {
    parts.push(plural(document.pages, 'page'))
    if (document.unread_page_count > 0) {
      parts.push(`${plural(document.unread_page_count, 'page')} without a text layer`)
    }
  }
  return parts.join(' \u00b7 ')
}
