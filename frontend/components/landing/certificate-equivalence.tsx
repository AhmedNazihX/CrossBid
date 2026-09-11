import { Tag } from '@/components/ui/tag'
import { SECTION_IDS } from './links'
import { Lead, MarketingEyebrow, SectionTitle, Wrap } from './section-primitives'

/**
 * "Certificate equivalence" of `Landing.dc.html` (`Sections.jsx`'s `Certificates`): the
 * 4-row table in a 14 px-radius card on the left (sunken 12 px header, 13 px rows with mono
 * country tags and the mono 11 px basis), the copy on the right, 56 px apart, the copy
 * column 1.15× wider. The artboard draws the table as a CSS grid; here it is a real
 * `<table>` with the same measures, and below `lg` the copy comes first and the table
 * scrolls sideways inside its card rather than squeezing.
 */
interface EquivalenceRow {
  readonly requestedIn: string
  readonly requested: string
  readonly equivalentIn: string
  readonly equivalent: string
  readonly basis: string
}

const ROWS: readonly EquivalenceRow[] = [
  {
    requestedIn: 'FR',
    requested: 'Attestation de régularité fiscale',
    equivalentIn: 'DE',
    equivalent: 'Bescheinigung in Steuersachen',
    basis: 'Dir. 2014/24 Art. 60 · eCertis',
  },
  {
    requestedIn: 'FR',
    requested: 'Attestation URSSAF',
    equivalentIn: 'DE',
    equivalent: 'Unbedenklichkeitsbescheinigung',
    basis: 'Dir. 2014/24 Art. 60 · eCertis',
  },
  {
    requestedIn: 'FR',
    requested: 'Extrait Kbis',
    equivalentIn: 'DE',
    equivalent: 'Handelsregisterauszug',
    basis: 'Dir. 2014/24 Ann. XI',
  },
  {
    requestedIn: 'DE',
    requested: 'Auszug Gewerbezentralregister',
    equivalentIn: 'FR',
    equivalent: 'Extrait de casier judiciaire (bulletin n° 3)',
    basis: 'Dir. 2014/24 Art. 60 · eCertis',
  },
]

const HEADER_CELL = 'px-1.5 py-3 text-left text-sm font-medium leading-none text-text-secondary'
const BODY_CELL =
  'px-1.5 py-[13px] align-middle text-[13px] leading-[1.3] [overflow-wrap:anywhere]'

export function CertificateEquivalence() {
  return (
    <section id={SECTION_IDS.certificates} className="scroll-mt-[68px] pt-20 lg:pt-32">
      <Wrap>
        <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)] lg:items-center lg:gap-14">
          <div className="min-w-0 overflow-hidden rounded-[14px] border border-border-default bg-surface-card shadow-xs lg:order-first">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[480px] border-collapse">
                <colgroup>
                  <col className="w-[60px]" />
                  <col />
                  <col className="w-[48px]" />
                  <col />
                  <col />
                </colgroup>
                <thead>
                  <tr className="border-b border-border-default bg-surface-sunken">
                    <th scope="col" className={`${HEADER_CELL} pl-[18px]`}>
                      <span className="sr-only">Requested in</span>
                    </th>
                    <th scope="col" className={HEADER_CELL}>
                      Requested
                    </th>
                    <th scope="col" className={HEADER_CELL}>
                      <span className="sr-only">Equivalent in</span>
                    </th>
                    <th scope="col" className={HEADER_CELL}>
                      Your equivalent
                    </th>
                    <th scope="col" className={`${HEADER_CELL} pr-[18px]`}>
                      Basis
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {ROWS.map((row, index) => (
                    <tr
                      key={`${row.requestedIn}-${row.requested}`}
                      className={index > 0 ? 'border-t border-border-default' : undefined}
                    >
                      <td className={`${BODY_CELL} pl-[18px] whitespace-nowrap`}>
                        <Tag mono>{row.requestedIn}</Tag>
                      </td>
                      <td className={BODY_CELL}>{row.requested}</td>
                      <td className={`${BODY_CELL} whitespace-nowrap`}>
                        <Tag mono>{row.equivalentIn}</Tag>
                      </td>
                      <td className={BODY_CELL}>{row.equivalent}</td>
                      <td
                        className={`${BODY_CELL} pr-[18px] font-mono text-xs leading-[1.4] text-text-muted`}
                      >
                        {row.basis}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="-order-1 lg:order-none">
            <MarketingEyebrow>Certificate equivalence</MarketingEyebrow>
            <SectionTitle>The buyer asks in their system. You answer in yours.</SectionTitle>
            <Lead>
              CrossBid maps requested certificates and registrations to their equivalents in
              your home country through the EU&apos;s eCertis service, and cites the directive
              or national rule that makes the equivalence valid.
            </Lead>
          </div>
        </div>
      </Wrap>
    </section>
  )
}
