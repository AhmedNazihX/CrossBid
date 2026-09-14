/**
 * Every destination the landing page links to, in one place (`Landing.dc.html`, the nav,
 * the hero and CTA buttons, the footer columns). The artboard's links are all `href="#"`;
 * here each one points at a real route or an in-page anchor, and nothing else is listed:
 * pages that do not exist are not linked (docs/project-plan.md S8.2 adds the imprint and
 * privacy notice, and a real demo address, if the site is ever deployed).
 */

/** The start step of the bid flow (`NewBid.dc.html`). */
export const ANALYSE_HREF = '/bids/new'

/** The magic-link sign-in page (S4.1.1). */
export const SIGN_IN_HREF = '/login'

/**
 * No booking or contact route exists yet, so "Book a demo" and "Talk to the team" anchor
 * to the closing call to action rather than to an invented address.
 */
export const CONTACT_HREF = '#get-started'

/** Anchors of the sections a nav or footer link can scroll to. */
export const SECTION_IDS = {
  product: 'product',
  howItWorks: 'how-it-works',
  certificates: 'certificates',
  customers: 'customers',
  advisory: 'advisory',
  getStarted: 'get-started',
} as const

export interface LandingLink {
  readonly label: string
  readonly href: string
}

/**
 * The nav items of `Nav.jsx`, in the artboard's order, minus "Pricing": there is no pricing
 * to show, and a link that scrolls somewhere else pretends otherwise.
 */
export const NAV_LINKS: readonly LandingLink[] = [
  { label: 'Product', href: `#${SECTION_IDS.product}` },
  { label: 'How it works', href: `#${SECTION_IDS.howItWorks}` },
  { label: 'Certificates', href: `#${SECTION_IDS.certificates}` },
  { label: 'Customers', href: `#${SECTION_IDS.customers}` },
]

export interface FooterColumn {
  readonly heading: string
  readonly links: readonly LandingLink[]
}

/**
 * The footer columns of `Footer.jsx`, kept to sections that exist. The kit's Resources
 * and Legal columns are omitted until S8.2 gives them pages.
 */
export const FOOTER_COLUMNS: readonly FooterColumn[] = [
  {
    heading: 'Product',
    links: [
      { label: 'How it works', href: `#${SECTION_IDS.howItWorks}` },
      { label: 'Certificate equivalence', href: `#${SECTION_IDS.certificates}` },
      { label: 'Compliance matrix', href: `#${SECTION_IDS.product}` },
    ],
  },
  {
    heading: 'Company',
    links: [
      { label: 'About', href: `#${SECTION_IDS.advisory}` },
      { label: 'Customers', href: `#${SECTION_IDS.customers}` },
      { label: 'Contact', href: CONTACT_HREF },
    ],
  },
]
