import Image from 'next/image'
import Link from 'next/link'

import { FOOTER_COLUMNS } from './links'

/**
 * The footer of `Landing.dc.html` (`Footer.jsx`): a 1 px rule, 56 px above and 40 px below;
 * the lockup at 28 px with a 14 px line under it, then the link columns (13 px medium
 * heads, 14 px links 10 px apart) beside a 1.4fr lead column; a second rule and the © line
 * with "Made in the EU · Data stays in the EU". Two columns on the phone, the three-track
 * row at `lg`; links are 44 px tall below `lg`.
 *
 * The kit's four columns are two here: only sections that exist are linked (`links.ts`).
 */
const FOOTER_LINK_CLASSES =
  'inline-flex min-h-11 items-center text-base leading-none text-text-secondary lg:min-h-0'

export function LandingFooter() {
  return (
    <footer className="border-t border-border-default px-6 pt-14 pb-10">
      <div className="mx-auto grid w-full max-w-[var(--marketing-max)] grid-cols-2 gap-8 lg:grid-cols-[1.4fr_repeat(2,minmax(0,1fr))]">
        <div className="col-span-2 lg:col-span-1">
          <Image
            src="/logo-lockup.svg"
            alt="CrossBid"
            width={116}
            height={28}
            className="block h-7 w-auto"
          />
          <p className="mt-3.5 max-w-[280px] text-base leading-[1.55] text-text-secondary">
            Go / no-go for EU public tenders, with a citation for every line.
          </p>
        </div>
        {FOOTER_COLUMNS.map((column) => (
          <nav key={column.heading} aria-label={column.heading}>
            <h2 className="mb-3.5 text-[13px] font-medium leading-none">{column.heading}</h2>
            <ul className="flex flex-col gap-2.5">
              {column.links.map((link) => (
                <li key={link.label}>
                  <Link href={link.href} className={FOOTER_LINK_CLASSES}>
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        ))}
      </div>
      <div className="mx-auto mt-10 flex w-full max-w-[var(--marketing-max)] flex-col gap-2 border-t border-border-default pt-6 text-[13px] leading-none text-text-muted sm:flex-row sm:justify-between">
        <span>© 2026 CrossBid</span>
        <span>Made in the EU · Data stays in the EU</span>
      </div>
    </footer>
  )
}
