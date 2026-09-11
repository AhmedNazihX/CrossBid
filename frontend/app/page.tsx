import { MAIN_CONTENT_ID } from '@/components/layout/nav-items'
import { SkipToContent } from '@/components/layout/skip-to-content'
import { AdvisoryBand } from '@/components/landing/advisory-band'
import { CallToAction } from '@/components/landing/call-to-action'
import { CertificateEquivalence } from '@/components/landing/certificate-equivalence'
import { CitedRequirements } from '@/components/landing/cited-requirements'
import { Hero } from '@/components/landing/hero'
import { HowItWorks } from '@/components/landing/how-it-works'
import { LandingFooter } from '@/components/landing/landing-footer'
import { LandingNav } from '@/components/landing/landing-nav'
import { TrustLine } from '@/components/landing/trust-line'

/**
 * The public landing page — `Landing.dc.html` (ADR-0014), the design system's website kit,
 * section by section in the artboard's order. Static marketing content: nothing here calls
 * the API. The way into the app is "Analyse a tender" (`/bids/new`) and, until sign-in
 * lands with S4.1.1, "Sign in" (`/dashboard`).
 */
export default function LandingPage() {
  return (
    <>
      <SkipToContent />
      <LandingNav />
      <main id={MAIN_CONTENT_ID}>
        <Hero />
        <TrustLine />
        <HowItWorks />
        <CitedRequirements />
        <CertificateEquivalence />
        <AdvisoryBand />
        <CallToAction />
      </main>
      <LandingFooter />
    </>
  )
}
