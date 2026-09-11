import { SECTION_IDS } from './links'
import { Wrap } from './section-primitives'

/**
 * The trust line of `Landing.dc.html`: a 14 px muted caption and five customer slots at
 * 17 px semibold, 44 px apart, the whole row at 60 % opacity. The slots stay the artboard's
 * visibly marked placeholders — `[Customer 1]` … `[Customer 5]` in dashed stone-300 boxes —
 * until real names exist; nothing is invented here.
 */
const PLACEHOLDER_COUNT = 5

export function TrustLine() {
  return (
    <section id={SECTION_IDS.customers} className="scroll-mt-[68px] pt-[72px]">
      <Wrap className="text-center">
        <h2 className="mb-6 text-base font-normal leading-none text-text-muted">
          Used by bid teams tendering across borders
        </h2>
        <ul className="flex flex-wrap justify-center gap-x-11 gap-y-3 opacity-60">
          {Array.from({ length: PLACEHOLDER_COUNT }, (_, index) => (
            <li
              key={index}
              className="rounded-sm border border-dashed border-border-strong px-3 py-1.5 text-lg font-semibold leading-none tracking-[-0.02em] text-text-secondary"
            >
              [Customer {index + 1}]
            </li>
          ))}
        </ul>
      </Wrap>
    </section>
  )
}
