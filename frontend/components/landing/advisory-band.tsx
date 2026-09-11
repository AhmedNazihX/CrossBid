import { SECTION_IDS } from './links'
import { SectionTitle, Wrap } from './section-primitives'

/**
 * The dark advisory band of `Landing.dc.html` (`Sections.jsx`'s `Advisory`): an ink
 * (`--surface-inverse`) panel with a 24 px radius and 72 × 64 px padding; the orange
 * eyebrow (this region's one orange), a white 40 px title and a stone-300 lead on the left;
 * three pillars on the right in 12 px-radius boxes on white at 4 % with a 12 % border,
 * stone-400 body text. Columns 1.1 : 1 at `lg`, stacked below with tighter padding.
 */
interface Pillar {
  readonly title: string
  readonly text: string
}

const PILLARS: readonly Pillar[] = [
  {
    title: 'Never submits',
    text: 'Every verdict is confirmed by a person before anything proceeds.',
  },
  {
    title: 'Never asserts without a source',
    text: 'Each compliance claim points at a page in the tender and a document in your profile.',
  },
  {
    title: 'Refuses when unsupported',
    text: '“Insufficient evidence” is a first-class verdict, not a failure state.',
  },
]

export function AdvisoryBand() {
  return (
    <section id={SECTION_IDS.advisory} className="scroll-mt-[68px] pt-20 lg:pt-32">
      <Wrap>
        <div className="grid gap-10 rounded-2xl bg-surface-inverse px-6 py-12 text-white sm:px-10 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] lg:items-center lg:gap-14 lg:px-16 lg:py-[72px]">
          <div>
            <p className="mb-3.5 text-sm font-medium uppercase leading-none tracking-[0.08em] text-surface-accent">
              Advisory by design
            </p>
            <SectionTitle className="text-white">
              An agent that knows what it does not know.
            </SectionTitle>
            <p className="mt-4 max-w-[520px] text-lg leading-[1.6] text-stone-300">
              CrossBid never submits a bid, never asserts compliance without a source, and
              withholds a verdict when the documents do not support one. Every verdict is
              confirmed by a person.
            </p>
          </div>
          <ul className="grid gap-3">
            {PILLARS.map((pillar) => (
              <li
                key={pillar.title}
                className="rounded-lg border border-[rgba(255,255,255,0.12)] bg-[rgba(255,255,255,0.04)] px-[18px] py-4"
              >
                <p className="text-[length:var(--text-md)] font-medium leading-[1.3]">
                  {pillar.title}
                </p>
                <p className="mt-1 text-base leading-[1.5] text-stone-400">{pillar.text}</p>
              </li>
            ))}
          </ul>
        </div>
      </Wrap>
    </section>
  )
}
