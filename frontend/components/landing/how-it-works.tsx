import { cn } from 'cn'

import { Icon, type IconName } from '@/components/ui/icons'
import { SECTION_IDS } from './links'
import { Lead, MarketingEyebrow, SectionTitle, Wrap } from './section-primitives'

/**
 * "How it works" of `Landing.dc.html` (`Sections.jsx`'s `Steps`): eyebrow, title, lead, then
 * five cards (14 px radius, 22 px padding, `--shadow-xs`), each with a 44 px icon tile on
 * the soft orange with the accent glyph — the fifth on ink with a white glyph — the mono
 * step number, a 17 px title and 14 px / 1.55 text. Five columns at `lg`, two at `sm`,
 * one on the phone.
 */
interface Step {
  readonly title: string
  readonly text: string
  readonly icon: IconName
}

const STEPS: readonly Step[] = [
  {
    title: 'Read',
    text: 'Upload the tender in any EU language. CrossBid extracts every requirement — exclusion, selection, technical, formal — each with a link to its source page.',
    icon: 'file',
  },
  {
    title: 'Translate and explain',
    text: 'Each requirement is translated into your language and explained in plain terms, including what the buyer will accept as proof.',
    icon: 'lang',
  },
  {
    title: 'Map certificates',
    text: 'Requested certificates are matched to their equivalents in your home country through eCertis — Attestation URSSAF to Unbedenklichkeitsbescheinigung — with the legal basis.',
    icon: 'layers',
  },
  {
    title: 'Check evidence',
    text: 'Every requirement is checked against your company documents. Supported, partially supported, or unsupported — never assumed.',
    icon: 'fileCheck',
  },
  {
    title: 'Verdict',
    text: 'Go, No-go, Conditional, or Insufficient evidence — with the compliance matrix behind it. A person confirms before anything proceeds.',
    icon: 'shield',
  },
]

export function HowItWorks() {
  return (
    <section id={SECTION_IDS.howItWorks} className="scroll-mt-[68px] pt-20 lg:pt-32">
      <Wrap>
        <MarketingEyebrow>How it works</MarketingEyebrow>
        <SectionTitle>Judgement work, done before the bid is written.</SectionTitle>
        <Lead>Five steps, each one traceable to the tender and to your own documents.</Lead>
        <ol className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {STEPS.map((step, index) => {
            const isLast = index === STEPS.length - 1
            return (
              <li
                key={step.title}
                className="rounded-[14px] border border-border-default bg-surface-card p-[22px] shadow-xs"
              >
                <div className="mb-[18px] flex items-center justify-between">
                  <span
                    className={cn(
                      'inline-flex size-11 items-center justify-center rounded-lg',
                      isLast ? 'bg-ink text-white' : 'bg-surface-accent-soft text-text-accent'
                    )}
                  >
                    <Icon name={step.icon} size={22} />
                  </span>
                  <span className="[font:var(--type-mono)] text-text-muted">
                    {String(index + 1).padStart(2, '0')}
                  </span>
                </div>
                <h3 className="mb-2 text-lg font-semibold leading-[1.2] tracking-[-0.02em]">
                  {step.title}
                </h3>
                <p className="text-base leading-[1.55] text-text-secondary">{step.text}</p>
              </li>
            )
          })}
        </ol>
      </Wrap>
    </section>
  )
}
