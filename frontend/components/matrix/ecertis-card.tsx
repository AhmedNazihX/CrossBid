import { cn } from 'cn'

import { Icon } from '@/components/ui/icons'
import type { EcertisEvidence } from '@/lib/bids'
import { formatCountry, formatList } from '@/lib/format'

export interface EcertisCardProps {
  readonly evidence: EcertisEvidence
  readonly className?: string
}

/**
 * The eCertis note inside an expanded row of `Main.dc.html` ("Evidence in your profile" →
 * the bordered card under the evidence line): a 1 px card on the card surface with the
 * layers glyph, the ESPD criterion in bold, and the sentence naming the national document
 * and its issuer in the bidder's own country. This is the cross-border wedge made visible —
 * the same criterion reads Bescheinigung in Steuersachen in DE and Cerfa n. 3666 in FR.
 *
 * `found === false` is a normal answer, not an error (ADR-0007: France has no national entry
 * for 17 of the 56 criteria), so it is written as a fact about the register rather than as a
 * problem with the bid, and never on a danger tint.
 */
export function EcertisCard({ evidence, className }: EcertisCardProps) {
  const country = formatCountry(evidence.country)
  return (
    <div
      className={cn(
        'flex gap-2 rounded-md border border-border-default bg-surface-card px-3 py-2.5 [font:var(--type-body-sm)] text-text-secondary',
        className
      )}
    >
      <Icon name="layers" size={14} className="mt-px shrink-0" />
      <div className="min-w-0">
        <b className="font-medium text-text-primary">eCertis · {evidence.criterion_name}.</b>{' '}
        {evidence.found ? (
          <EcertisFound evidence={evidence} country={country} />
        ) : (
          <>
            The register lists no national evidence for {country} against this criterion. That
            is an entry {country} does not publish, not a gap in your bid.
          </>
        )}
        {evidence.description !== null && evidence.description !== undefined && (
          <p className="m-0 mt-1.5 text-text-muted">{evidence.description}</p>
        )}
      </div>
    </div>
  )
}

function EcertisFound({
  evidence,
  country,
}: {
  readonly evidence: EcertisEvidence
  readonly country: string
}) {
  if (evidence.evidence_names.length === 0) {
    return (
      <>
        {country} records this criterion, but names no document for it — ask the buyer which
        paper they expect.
      </>
    )
  }
  return (
    <>
      In {country} this criterion is evidenced by {formatList(evidence.evidence_names)}
      {evidence.issuers.length > 0 && <> from {formatList(evidence.issuers)}</>}.
    </>
  )
}
