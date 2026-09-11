import Link from 'next/link'

import { Button } from '@/components/ui/button'
import { Icon } from '@/components/ui/icons'
import { ANALYSE_HREF, CONTACT_HREF } from './links'

/**
 * The two action pairs of `Landing.dc.html`: the inverse 48 px "Analyse a tender" with the
 * 16 px arrow (hero and CTA) and its secondary partner. `Button asChild` keeps each one a
 * real anchor; `hover:no-underline` cancels the base layer's link underline on the
 * button-shaped ones.
 */
export function AnalyseTenderLink() {
  return (
    <Button asChild variant="inverse" size="lg" className="hover:no-underline">
      <Link href={ANALYSE_HREF}>
        Analyse a tender
        <span className="inline-flex size-4 [&_svg]:size-4">
          <Icon name="arrow" size={16} />
        </span>
      </Link>
    </Button>
  )
}

export function ContactLink({ children }: { readonly children: string }) {
  return (
    <Button asChild variant="secondary" size="lg" className="hover:no-underline">
      <Link href={CONTACT_HREF}>{children}</Link>
    </Button>
  )
}
