'use client'

/**
 * The picked notice, summarised above the upload and start steps — the "Found on TED" card
 * of `NewBid.dc.html` (story S4.3.1).
 *
 * Its job is to let the bidder confirm they are about to spend four minutes and a euro on
 * the *right* tender, so it shows the facts that distinguish one notice from another and
 * nothing else. `Change` goes back to the search rather than to a cleared form: picking the
 * wrong one is a normal thing to do, and a screen that punishes it by dropping the filters
 * makes the bidder type them again.
 *
 * **The deadline is a date with no hour, and the card says so.** TED publishes the day and
 * the buyer's UTC offset and never a time (ADR-0043), so this is the one place a bidder is
 * told where the missing hour has to come from: the notice itself.
 */
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Icon } from '@/components/ui/icons'
import { formatDate } from '@/lib/format'
import type { TedNotice } from '@/lib/tenders'

export interface FoundOnTedProps {
  readonly notice: TedNotice
  readonly onChange: () => void
}

export function FoundOnTed({ notice, onChange }: FoundOnTedProps) {
  return (
    <Card>
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 flex-col gap-1">
            <p className="m-0 [font:var(--type-body-sm)] text-text-muted">Found on TED</p>
            <h2 className="m-0 text-[length:var(--text-md)] font-semibold text-text-primary">
              {notice.title}
            </h2>
            <p className="m-0 [font:var(--type-body-sm)] text-text-secondary">
              {notice.buyer ?? 'Buyer not named on the notice'} · {notice.publication_number}
            </p>
          </div>
          <Button type="button" variant="ghost" size="sm" onClick={onChange}>
            Change
          </Button>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={notice.deadline === null ? 'neutral' : 'info'} pill={false}>
            {notice.deadline === null
              ? 'No deadline published'
              : `Due ${formatDate(notice.deadline)} — TED publishes no time`}
          </Badge>
          {notice.official_languages.length > 0 && (
            <Badge tone="neutral" pill={false}>
              Written in {notice.official_languages.join(', ')}
            </Badge>
          )}
          {notice.submission_languages.length > 0 && (
            <Badge tone="neutral" pill={false}>
              Offers in {notice.submission_languages.join(', ')}
            </Badge>
          )}
        </div>

        {notice.documents_url !== null && (
          <p className="m-0 [font:var(--type-body-sm)] text-text-secondary">
            The buyer publishes the pack on{' '}
            <a
              className="underline underline-offset-2 hover:text-text-primary"
              href={notice.documents_url}
              target="_blank"
              rel="noopener noreferrer"
            >
              their own platform
              <Icon name="ext" size={14} aria-hidden className="ml-1 inline align-[-2px]" />
            </a>
            . Crossbid never fetches from there — download the files and add them below.
          </p>
        )}
      </div>
    </Card>
  )
}
