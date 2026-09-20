'use client'

/**
 * Step 1 of `NewBid.dc.html` — finding the notice on TED (story S4.3.1).
 *
 * The screen exists so that a bidder never learns the TED portal, so it asks for the three
 * things they already know — what they do (CPV), where they will bid (country), and a word
 * from the tender — and nothing else. Everything the expert query needs beyond that is the
 * client's business (ADR-0043).
 *
 * **Titles arrive in the bidder's own language.** TED publishes every notice title in all 24
 * EU languages, so the company profile's `language` is passed down and a German bidder reads
 * a French tender's title in German, with no model call and no cost. It is the cheapest
 * appearance of the cross-border wedge anywhere in the product.
 *
 * **The documents link goes to the buyer's platform, and that is the point.** TED almost
 * never hosts the pack: `document-url-lot` is a national portal, and the no-scraping rule
 * means Crossbid will not fetch from it. So the result offers the link and the next step
 * asks the bidder to drop the files in — which is the whole reason the upload step exists.
 */
import { useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Icon } from '@/components/ui/icons'
import { Input } from '@/components/ui/input'
import { Notice } from '@/components/ui/notice'
import { Select } from '@/components/ui/select'
import { describeApiError } from '@/lib/api-client'
import { BIDDER_COUNTRIES } from '@/lib/companies'
import { formatDate } from '@/lib/format'
import {
  countryNameOf,
  CPV_SUGGESTIONS,
  isBoughtElsewhere,
  isNoticeClosed,
  searchTenders,
  type TedNotice,
} from '@/lib/tenders'

type Phase =
  | { readonly kind: 'idle' }
  | { readonly kind: 'searching' }
  | { readonly kind: 'results'; readonly notices: readonly TedNotice[]; readonly total: number }
  | { readonly kind: 'failed'; readonly message: string }

export interface TenderSearchProps {
  /** The bidder's language, so TED's own translations are used where they exist. */
  readonly language: string | undefined
  readonly onPick: (notice: TedNotice) => void
}

export function TenderSearch({ language, onPick }: TenderSearchProps) {
  const [cpv, setCpv] = useState(CPV_SUGGESTIONS[0]?.code ?? '72000000')
  const [country, setCountry] = useState('fr')
  const [keyword, setKeyword] = useState('')
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' })

  async function onSearch(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setPhase({ kind: 'searching' })
    try {
      const page = await searchTenders(
        { cpv: [cpv], countries: [country], keyword },
        { language }
      )
      setPhase({ kind: 'results', notices: page.notices, total: page.total })
    } catch (cause) {
      setPhase({ kind: 'failed', message: describeApiError(cause) })
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <Card>
        <form className="flex flex-col gap-4" onSubmit={onSearch}>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Select
              label="What you do"
              hint="CPV, the vocabulary buyers classify tenders with"
              options={CPV_SUGGESTIONS.map((entry) => ({
                value: entry.code,
                label: `${entry.code} · ${entry.label}`,
              }))}
              value={cpv}
              onValueChange={setCpv}
              disabled={phase.kind === 'searching'}
            />
            <Select
              label="Where the work is"
              options={BIDDER_COUNTRIES.map((entry) => ({
                value: entry.code,
                label: entry.label,
              }))}
              value={country}
              onValueChange={setCountry}
              disabled={phase.kind === 'searching'}
            />
          </div>
          <Input
            label="Keyword"
            hint="Optional. One phrase, searched across the whole notice."
            placeholder="cyber security"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            disabled={phase.kind === 'searching'}
          />
          <div>
            <Button type="submit" disabled={phase.kind === 'searching'}>
              {phase.kind === 'searching' ? 'Searching TED…' : 'Search TED'}
            </Button>
          </div>
        </form>
      </Card>

      {phase.kind === 'failed' && (
        <Notice tone="danger" title="The search did not run">
          {phase.message}
        </Notice>
      )}

      {phase.kind === 'results' && phase.notices.length === 0 && (
        <Notice title="Nothing published under those filters">
          TED answered, and no contract notice matches. Drop the keyword first — it is matched
          as whole words against the notice&rsquo;s own language, so an English phrase rarely
          finds a French tender. Then widen the CPV, or try a neighbouring country.
        </Notice>
      )}

      {phase.kind === 'results' && phase.notices.length > 0 && (
        <div className="flex flex-col gap-3">
          <p className="m-0 [font:var(--type-body-sm)] text-text-muted">
            {/* Not "open notices": TED counts every notice matching the filters, and its
                oldest matches are years past their deadline. Each card says which it is. */}
            {phase.total.toLocaleString()} notices match. Showing the most recent{' '}
            {phase.notices.length}.
          </p>
          {phase.notices.map((notice) => (
            <NoticeResult
              key={notice.publication_number}
              notice={notice}
              searchedCountry={country}
              onPick={onPick}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function NoticeResult({
  notice,
  searchedCountry,
  onPick,
}: Readonly<{
  notice: TedNotice
  /** The alpha-2 the bidder searched on, so the card can say when the buyer is elsewhere. */
  searchedCountry: string
  onPick: (notice: TedNotice) => void
}>) {
  const isClosed = isNoticeClosed(notice)
  const isForeign = isBoughtElsewhere(notice, searchedCountry)
  return (
    <Card>
      <div className="flex flex-col gap-3">
        <div className="flex flex-col gap-1">
          <h3 className="m-0 text-[length:var(--text-md)] font-semibold text-text-primary">
            {notice.title}
          </h3>
          <p className="m-0 [font:var(--type-body-sm)] text-text-secondary">
            {notice.buyer ?? 'Buyer not named on the notice'} · {notice.publication_number}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Three states, not two. A notice years past its deadline used to carry the same
              blue "Due" chip as a live one, and TED serves plenty of them. "No deadline
              published" stays its own answer: 351 of 521 recent French CPV-72 contract
              notices carry none, so silence means unknown and never means closed. */}
          <Badge
            tone={notice.deadline === null ? 'neutral' : isClosed ? 'danger' : 'info'}
            pill={false}
          >
            {notice.deadline === null
              ? 'No deadline published'
              : `${isClosed ? 'Closed' : 'Due'} ${formatDate(notice.deadline)}`}
          </Badge>
          {/* The country clause filters on where the work happens, which for a pan-European
              framework includes France while the buyer sits in London. That is an honest
              match and it used to be invisible, which is how it arrived as a bug report. */}
          {notice.buyer_countries.length > 0 && (
            <Badge tone={isForeign ? 'warning' : 'neutral'} pill={false}>
              Buyer in {notice.buyer_countries.map(countryNameOf).join(', ')}
            </Badge>
          )}
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

        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" size="sm" onClick={() => onPick(notice)}>
            Use this notice
          </Button>
          {notice.notice_pdf_url !== null && (
            <Button asChild variant="secondary" size="sm">
              <a href={notice.notice_pdf_url} target="_blank" rel="noopener noreferrer">
                Read the notice
                <Icon name="ext" size={16} aria-hidden />
              </a>
            </Button>
          )}
          {notice.documents_url !== null && (
            <Button asChild variant="ghost" size="sm">
              <a href={notice.documents_url} target="_blank" rel="noopener noreferrer">
                Buyer&rsquo;s platform
                <Icon name="ext" size={16} aria-hidden />
              </a>
            </Button>
          )}
        </div>
      </div>
    </Card>
  )
}
