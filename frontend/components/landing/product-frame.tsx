import { cn } from 'cn'

import { Badge, type BadgeTone } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tag } from '@/components/ui/tag'
import { VerdictChip } from '@/components/ui/verdict-chip'

/**
 * The product frame under the hero of `Landing.dc.html` (`Hero.jsx`'s `ProductFrame`): a
 * 980 px browser chrome (three 10 px stone dots, the mono address) around a static sample
 * of the workspace — the FR tender's tags and title, four requirement rows with the
 * design-system evidence badges, the "CrossBid recommends" No-go card and the sunken
 * "Awaiting review" card — with the 140 px protection gradient fading into the canvas.
 *
 * The content is the artboard's sample text, not live data; the "Confirm verdict" control
 * is a styled `<span>` because nothing here is a real verdict to confirm. Below `lg` the
 * two columns stack; below `md` each row's citation and badge drop under the title
 * (`md:contents` returns them to their own grid cells).
 */
interface SampleRow {
  readonly id: string
  readonly title: string
  readonly source: string
  readonly tone: BadgeTone
  readonly status: string
}

const SAMPLE_ROWS: readonly SampleRow[] = [
  {
    id: 'REQ-002',
    title: 'Steuern und Sozialabgaben vollständig entrichtet',
    source: 'RC p. 7 §4.2',
    tone: 'success',
    status: 'Supported',
  },
  {
    id: 'REQ-009',
    title: 'Durchschnittsumsatz ≥ 2 Mio. € (netto)',
    source: 'RC p. 9 §5.1',
    tone: 'danger',
    status: 'Unsupported',
  },
  {
    id: 'REQ-014',
    title: 'ISO/IEC 27001 oder gleichwertig',
    source: 'RC p. 11 §5.4',
    tone: 'success',
    status: 'Supported',
  },
  {
    id: 'REQ-017',
    title: 'Drei vergleichbare Referenzen aus drei Jahren',
    source: 'RC p. 12 §5.5',
    tone: 'warning',
    status: 'Partially supported',
  },
]

export function ProductFrame() {
  return (
    <div className="relative mx-auto mt-14 max-w-[980px]">
      <div className="overflow-hidden rounded-xl border border-border-default bg-surface-card shadow-lg">
        <div className="flex items-center gap-2 border-b border-border-default bg-surface-sunken px-4 py-3">
          <span aria-hidden="true" className="size-2.5 shrink-0 rounded-full bg-stone-300" />
          <span aria-hidden="true" className="size-2.5 shrink-0 rounded-full bg-stone-300" />
          <span aria-hidden="true" className="size-2.5 shrink-0 rounded-full bg-stone-300" />
          <span className="ml-3 truncate [font:var(--type-mono)] text-text-muted">
            app.crossbid.eu / tenders / 618320-2026
          </span>
        </div>

        <div className="grid gap-6 p-4 text-left sm:p-7 lg:grid-cols-[minmax(0,1fr)_300px]">
          <div className="min-w-0">
            <div className="mb-3.5 flex flex-wrap gap-2">
              <Tag>Ministère de l&apos;éducation nationale</Tag>
              <Tag>France → Germany</Tag>
              <Tag>25 pages · FR</Tag>
            </div>
            <p
              lang="fr"
              className="mb-[18px] text-xl font-semibold leading-[1.25] tracking-[-0.02em]"
            >
              Prestations de conseil en architecture d&apos;entreprise et d&apos;expertise
              technique
            </p>
            <div className="overflow-hidden rounded-[10px] border border-border-default">
              {SAMPLE_ROWS.map((row, index) => (
                <div
                  key={row.id}
                  className={cn(
                    'grid grid-cols-[82px_minmax(0,1fr)] items-center gap-3 px-3.5 py-[11px] text-[13px] leading-[1.3]',
                    'md:grid-cols-[82px_minmax(0,1fr)_110px_150px]',
                    index > 0 && 'border-t border-border-default'
                  )}
                >
                  <Tag mono>{row.id}</Tag>
                  <span lang="de" className="truncate">
                    {row.title}
                  </span>
                  <div className="col-start-2 flex flex-wrap items-center gap-3 md:contents">
                    <span className="font-mono text-xs leading-[1.5] text-text-link">
                      {row.source}
                    </span>
                    <Badge tone={row.tone} size="sm">
                      {row.status}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="flex flex-col gap-3">
            <div className="rounded-lg border border-border-default p-[18px]">
              <p className="mb-2.5 text-[13px] leading-none text-text-secondary">
                CrossBid recommends
              </p>
              <VerdictChip verdict="no_go" size="lg" />
              <p className="mt-3 text-[13px] leading-[1.5] text-text-secondary">
                24 of 31 requirements supported. One selection minimum is not met and decides
                the verdict.
              </p>
            </div>
            <div className="rounded-lg border border-border-default bg-surface-sunken p-[18px]">
              <p className="mb-2.5 text-[13px] leading-none text-text-secondary">
                Awaiting review
              </p>
              <Button asChild size="sm" fullWidth>
                <span>Confirm verdict</span>
              </Button>
              <p className="mt-2 text-sm leading-[1.4] text-text-muted">
                Nothing moves forward until a person confirms.
              </p>
            </div>
          </div>
        </div>
      </div>

      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 -bottom-px h-[140px] bg-[image:var(--protect-gradient)]"
      />
    </div>
  )
}
