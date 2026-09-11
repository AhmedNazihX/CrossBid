import { Badge } from '@/components/ui/badge'
import { Eyebrow } from '@/components/ui/eyebrow'
import { Icon } from '@/components/ui/icons'
import { Tag } from '@/components/ui/tag'
import { SECTION_IDS } from './links'
import { Lead, MarketingEyebrow, SectionTitle, Wrap } from './section-primitives'

/**
 * "Every requirement, cited" of `Landing.dc.html` (`Sections.jsx`'s `Features`): a two-column
 * grid with 64 px between — copy and three check rows (22 px success circles) on the left,
 * the REQ-002 card on the right (16 px radius, 24 px padding, `--shadow-md`): the mono id,
 * "Exclusion ·", the mono citation with the 12 px external glyph, the shell's muted
 * eyebrows over the French source and the German explanation, and the Supported badge
 * with the two certificates. One column below `lg`.
 *
 * The citation is a `<span>`: there is no source PDF behind a marketing sample to open.
 */
interface Check {
  readonly title: string
  readonly text: string
}

const CHECKS: readonly Check[] = [
  {
    title: 'Source-linked extraction',
    text: 'Page and clause reference on every requirement.',
  },
  {
    title: 'Translated, not paraphrased',
    text: 'The original text stays alongside the explanation.',
  },
  {
    title: 'Refuses when unsure',
    text: 'If the documents do not support a verdict, CrossBid says so.',
  },
]

export function CitedRequirements() {
  return (
    <section id={SECTION_IDS.product} className="scroll-mt-[68px] pt-20 lg:pt-32">
      <Wrap>
        <div className="grid gap-10 lg:grid-cols-2 lg:items-center lg:gap-16">
          <div>
            <MarketingEyebrow>Every requirement, cited</MarketingEyebrow>
            <SectionTitle>No claim without a page number.</SectionTitle>
            <Lead>
              Each extracted line links to the exact page and clause in the tender. Reviewers
              check the source, not the summary.
            </Lead>
            <ul className="mt-8 flex flex-col gap-3.5">
              {CHECKS.map((check) => (
                <li key={check.title} className="flex gap-3">
                  <span className="mt-px inline-flex size-[22px] shrink-0 items-center justify-center rounded-full bg-status-success-bg text-status-success">
                    <Icon name="check" size={14} />
                  </span>
                  <div>
                    <p className="text-[length:var(--text-md)] font-medium leading-[1.3]">
                      {check.title}
                    </p>
                    <p className="text-base leading-[1.5] text-text-secondary">{check.text}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>

          <article
            aria-label="Sample requirement REQ-002"
            className="min-w-0 rounded-xl border border-border-default bg-surface-card p-6 shadow-md"
          >
            <div className="mb-4 flex flex-wrap items-center gap-2.5">
              <Tag mono>REQ-002</Tag>
              <span className="text-[13px] font-medium leading-none text-text-secondary">
                Exclusion ·
              </span>
              <span className="inline-flex items-center gap-[5px] [font:var(--type-mono)] text-text-link">
                RC p. 7 §4.2
                <Icon name="ext" size={12} />
              </span>
            </div>
            <Eyebrow className="mb-1.5">Source (FR)</Eyebrow>
            <p lang="fr" className="mb-4 text-base italic leading-[1.5] text-text-secondary">
              “Le candidat doit être à jour de ses obligations fiscales et sociales au 31
              décembre de l&apos;année précédant la consultation.”
            </p>
            <Eyebrow className="mb-1.5">Explained (DE)</Eyebrow>
            <p lang="de" className="mb-4 text-base leading-[1.5]">
              Steuern und Sozialabgaben sind zum 31. Dezember des Vorjahres vollständig
              entrichtet. In Deutschland belegt das eine Bescheinigung in Steuersachen des
              Finanzamts und eine Unbedenklichkeitsbescheinigung der Krankenkasse — so ordnet
              eCertis dieses Kriterium zu.
            </p>
            <div className="flex flex-wrap items-center gap-2.5 border-t border-border-default pt-4">
              <Badge tone="success">Supported</Badge>
              <span className="text-[13px] leading-[1.3] text-text-secondary">
                Bescheinigung in Steuersachen, 03/2026 · Krankenkasse, 02/2026
              </span>
            </div>
          </article>
        </div>
      </Wrap>
    </section>
  )
}
