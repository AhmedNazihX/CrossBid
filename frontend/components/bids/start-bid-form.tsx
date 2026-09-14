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
type OffsetValue = '' | '0' | '60' | '120' | '180'

/**
 * The offsets a European notice actually prints, and **no default**.
 *
 * Defaulting this to the browser's own offset is the tempting thing and is wrong: a German
 * bidder reading a French notice would submit Berlin's clock for Paris's deadline and never
 * see it happen. The backend refuses a timestamp with no offset for the same reason
 * (`routers/bids.py`), so the form asks rather than guesses — and a deadline is the one field
 * where a silent few hours is a real error rather than a tidiness one.
 */
const DEADLINE_NEEDS_ITS_ZONE =
  'Give the zone the notice states, or clear the deadline. A time with no zone would move it.'

const DEADLINE_OFFSETS: readonly { value: OffsetValue; label: string }[] = [
  { value: '', label: 'As the notice states…' },
  { value: '0', label: 'UTC+00:00 · UK, Portugal, Ireland' },
  { value: '60', label: 'UTC+01:00 · most of the EU, winter' },
  { value: '120', label: 'UTC+02:00 · most of the EU, summer' },
  { value: '180', label: 'UTC+03:00 · Finland, Greece, the Baltics, summer' },
]

/**
 * `2026-10-09T16:00` plus `120` becomes `2026-10-09T16:00:00+02:00` — the wall clock the
 * buyer printed, carrying the offset they printed it in. `null` unless both halves are
 * present, because either alone describes nothing the backend will accept.
 */
function deadlineAt(local: string, offsetMinutes: OffsetValue): string | null {
  if (local === '' || offsetMinutes === '') {
    return null
  }
  const minutes = Number(offsetMinutes)
  const sign = minutes < 0 ? '-' : '+'
  const absolute = Math.abs(minutes)
  const hh = String(Math.floor(absolute / 60)).padStart(2, '0')
  const mm = String(absolute % 60).padStart(2, '0')
  // `datetime-local` yields `YYYY-MM-DDTHH:mm`, and omits `:ss` unless a step demands it.
  const withSeconds = local.length === 16 ? `${local}:00` : local
  return `${withSeconds}${sign}${hh}:${mm}`
}

export function StartBidForm() {
  const router = useRouter()
  const [listState, setListState] = useState<ListState>({ phase: 'loading' })
  const [noticeNumber, setNoticeNumber] = useState('')
  const [sourceLanguage, setSourceLanguage] = useState<SourceLanguage>('fr')
  const [buyer, setBuyer] = useState('')
  const [deadlineLocal, setDeadlineLocal] = useState('')
  const [deadlineOffset, setDeadlineOffset] = useState<OffsetValue>('')
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
  // A deadline with no offset is not "a deadline we can almost use": it is refused by the
  // backend and, worse, would be dropped silently here. So it blocks the submit rather than
  // being discarded — a reviewer who typed a date must not find the bid has none.
  const isDeadlineIncomplete = deadlineLocal !== '' && deadlineOffset === ''
  const canStart =
    selected.size > 0 && noticeNumber.trim().length > 0 && !isDeadlineIncomplete && !isStarting

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
        buyer: buyer.trim() === '' ? null : buyer.trim(),
        deadline: deadlineAt(deadlineLocal, deadlineOffset),
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
          <Input
            label="Buyer (optional)"
            name="buyer"
            value={buyer}
            onChange={(event) => setBuyer(event.target.value)}
            placeholder="Ministère de l’Intérieur"
            autoComplete="off"
            hint="The contracting authority, as the notice names it."
          />
          <div className="grid gap-4 sm:grid-cols-[1fr_auto]">
            <Input
              label="Deadline (optional)"
              name="deadline"
              type="datetime-local"
              value={deadlineLocal}
              onChange={(event) => setDeadlineLocal(event.target.value)}
              hint="The date and time the notice states, exactly as it prints them."
            />
            <Select
              label="Its time zone"
              name="deadline_offset"
              value={deadlineOffset}
              onValueChange={setDeadlineOffset}
              options={DEADLINE_OFFSETS}
              error={isDeadlineIncomplete ? DEADLINE_NEEDS_ITS_ZONE : undefined}
              hint={isDeadlineIncomplete ? undefined : 'Exactly as the notice prints it.'}
            />
          </div>
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
