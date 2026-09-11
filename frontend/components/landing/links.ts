/**
 * Every destination the landing page links to, in one place (`Landing.dc.html`, the nav,
 * the hero and CTA buttons, the footer columns). The artboard's links are all `href="#"`;
 * here each one points at a real route or an in-page anchor, and the ones with no
 * destination yet are listed without an `href` so the footer renders them as plain text
 * instead of a dead link.
 */

/** The start step of the bid flow (`NewBid.dc.html`). */
export const ANALYSE_HREF = '/bids/new'

/**
 * Sign-in is S4.1.1. Until it lands there is no session, so "Sign in" opens the shell
 * directly — the same door the placeholder page used.
 */
export const SIGN_IN_HREF = '/dashboard'

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
  /** Absent while the destination is not built; the footer shows the label as text. */
  readonly href?: string
}

/**
 * The five nav items of `Nav.jsx`, in the artboard's order. The artboard has no pricing
 * section, so "Pricing" scrolls to the call to action, where "Talk to the team" is the
 * pricing conversation for now.
 */
export const NAV_LINKS: readonly Required<LandingLink>[] = [
  { label: 'Product', href: `#${SECTION_IDS.product}` },
  { label: 'How it works', href: `#${SECTION_IDS.howItWorks}` },
  { label: 'Certificates', href: `#${SECTION_IDS.certificates}` },
  { label: 'Pricing', href: `#${SECTION_IDS.getStarted}` },
  { label: 'Customers', href: `#${SECTION_IDS.customers}` },
]

export interface FooterColumn {
  readonly heading: string
  readonly links: readonly LandingLink[]
}

/** The four link columns of `Footer.jsx`. */
export const FOOTER_COLUMNS: readonly FooterColumn[] = [
  {
    heading: 'Product',
    links: [
      { label: 'How it works', href: `#${SECTION_IDS.howItWorks}` },
      { label: 'Certificate equivalence', href: `#${SECTION_IDS.certificates}` },
      { label: 'Compliance matrix', href: `#${SECTION_IDS.product}` },
      { label: 'Pricing', href: `#${SECTION_IDS.getStarted}` },
    ],
  },
  {
    heading: 'Company',
    links: [
      { label: 'About', href: `#${SECTION_IDS.advisory}` },
      { label: 'Customers', href: `#${SECTION_IDS.customers}` },
      { label: 'Careers' },
      { label: 'Contact', href: CONTACT_HREF },
    ],
  },
  {
    heading: 'Resources',
    links: [
      { label: 'Documentation' },
      { label: 'EU procurement guide' },
      { label: 'Security' },
      { label: 'Status' },
    ],
  },
  {
    heading: 'Legal',
    links: [
      { label: 'Privacy' },
      { label: 'Terms' },
      { label: 'Data processing' },
      { label: 'Imprint' },
    ],
  },
]
