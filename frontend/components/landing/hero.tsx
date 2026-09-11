import { AnalyseTenderLink, ContactLink } from './actions'
import { BrandReveal } from './brand-reveal'
import { ProductFrame } from './product-frame'

/**
 * The hero of `Landing.dc.html` (`Hero.jsx`): 96 px above a centred column; the pill with
 * the orange "New" chip (the region's one orange); the 64 px / 1.05 headline at -0.035em
 * (`tracking-tighter`) capped at 820 px; the 19 px lead at 620 px; "Analyse a tender"
 * (inverse, arrow) and "Book a demo" (secondary); the 13 px advisory line; the faint 72 px
 * stone-200 grid at 35 % under a radial mask; then the product frame.
 *
 * The headline scales with `clamp(36px, 9vw, 64px)` so it never breaks a 320 px screen, and
 * the pill is allowed to wrap there.
 *
 * `BrandReveal` is the one element here with no artboard behind it — added after the canvas
 * was confirmed (ADR-0014). It is cropped to the mark alone, so the headline below is not
 * repeated by the clip's own tagline. The pill runs **above** it rather than between it and
 * the headline: the artboard's order put the pill first, and with the clip in front of it
 * the two crowded each other.
 */
export function Hero() {
  return (
    <section className="relative overflow-hidden px-6 pt-16 text-center sm:pt-24">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-[linear-gradient(var(--cb-stone-200)_1px,transparent_1px),linear-gradient(90deg,var(--cb-stone-200)_1px,transparent_1px)] bg-[size:72px_72px] opacity-35 [mask-image:radial-gradient(ellipse_70%_60%_at_50%_20%,#000_30%,transparent_100%)]"
      />
      <div className="relative mx-auto w-full max-w-[var(--marketing-max)]">
        <p className="mb-7 inline-flex max-w-full flex-wrap items-center justify-center gap-2 rounded-[var(--radius-pill)] border border-border-default bg-surface-card py-1.5 pr-3 pl-2 text-[13px] font-medium leading-[1.3] text-text-secondary sm:leading-none">
          <span className="rounded-[var(--radius-pill)] bg-surface-accent px-2 py-[3px] text-xs font-semibold leading-[1.2] text-white">
            New
          </span>
          Certificate equivalence via eCertis for all 27 member states
        </p>
        <BrandReveal />
        <h1 className="mx-auto max-w-[820px] text-balance text-[length:clamp(36px,9vw,64px)] font-semibold leading-[1.05] tracking-tighter">
          Know if you can win before you write a word.
        </h1>
        <p className="mx-auto mt-6 max-w-[620px] text-pretty text-[19px] leading-[1.55] text-text-secondary">
          CrossBid reads any EU tender, maps every requirement to your evidence, and gives you a
          go / no-go verdict you can defend — with a citation for each line.
        </p>
        <div className="mt-8 flex flex-wrap justify-center gap-2.5">
          <AnalyseTenderLink />
          <ContactLink>Book a demo</ContactLink>
        </div>
        <p className="mt-4 text-[13px] leading-[1.4] text-text-muted sm:leading-none">
          Advisory by design — CrossBid never submits on your behalf.
        </p>
        <ProductFrame />
      </div>
    </section>
  )
}
