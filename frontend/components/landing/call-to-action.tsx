import { AnalyseTenderLink, ContactLink } from './actions'
import { SECTION_IDS } from './links'
import { Lead, SectionTitle, Wrap } from './section-primitives'

/**
 * The closing call to action of `Landing.dc.html` (`Sections.jsx`'s `CTA`): 128 px above and
 * below, centred title and lead, "Analyse a tender" (inverse, arrow) beside "Talk to the
 * team" (secondary). It is also where "Book a demo", "Pricing" and "Talk to the team"
 * land until a booking route exists (`links.ts`).
 */
export function CallToAction() {
  return (
    <section id={SECTION_IDS.getStarted} className="scroll-mt-[68px] py-20 lg:py-32">
      <Wrap className="text-center">
        <SectionTitle>Bring a tender. Leave with a verdict.</SectionTitle>
        <Lead center>
          Upload one tender and see the compliance matrix in minutes. No integration required.
        </Lead>
        <div className="mt-8 flex flex-wrap justify-center gap-2.5">
          <AnalyseTenderLink />
          <ContactLink>Talk to the team</ContactLink>
        </div>
      </Wrap>
    </section>
  )
}
