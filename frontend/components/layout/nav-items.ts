/**
 * The authenticated shell's navigation (story S4.1.2).
 *
 * One list, consumed by both the desktop bar and the mobile sheet, so the two can
 * never drift. Adding a section here is the only edit a new route needs.
 *
 * `/company`, `/settings` and `/bids/new` are placeholders until their own stories
 * (S4.2.1, S4.2.2, S4.3.1, S4.6.4) fill them in.
 */
export interface NavItem {
  readonly href: string
  readonly label: string
  /** Rendered as the shell's single call to action rather than a plain nav link. */
  readonly isPrimary?: boolean
}

export const NAV_ITEMS: readonly NavItem[] = [
  { href: '/dashboard', label: 'Dashboard' },
  { href: '/company', label: 'Company' },
  { href: '/settings', label: 'Settings' },
  { href: '/bids/new', label: 'New bid', isPrimary: true },
] as const

/** Anchor target of the skip link, and the `id` of the shell's `<main>`. */
export const MAIN_CONTENT_ID = 'main-content'

/**
 * Whether `href` is the section the given path sits in.
 *
 * Exact match, or a descendant path — `/bids/new/upload` keeps "New bid" current —
 * while `/bids/newest` does not, because the separator is required.
 */
export function isSectionActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`)
}
