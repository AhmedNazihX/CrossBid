import type { IconName } from '@/components/ui/icons'
import type { DeveloperAccess } from '@/lib/use-developer-access'

/**
 * The shell's navigation — `ui_kits/app/Shell.jsx`'s sidebar, as data (story S4.1.2, rebuilt
 * for ADR-0014).
 *
 * One list, consumed by the desktop sidebar and the phone drawer, so the two can never
 * drift. Two eyebrow groups: WORKFLOW (the bid's path from tender to verdict) and PLATFORM
 * (what supports it). Verdicts is the one solid orange tile per screen region, as the kit
 * draws it; every other tile is an ink glyph on stone.
 */
export type NavGroup = 'workflow' | 'platform'

export interface NavItem {
  readonly key: string
  readonly href: string
  readonly label: string
  readonly icon: IconName
  readonly group: NavGroup
  /** `solid` is the orange tile — used once, for Verdicts. */
  readonly tone?: 'soft' | 'solid'
  /** A trailing chevron, as the kit shows on Company profile. */
  readonly trailing?: boolean
  /** Which paths mark this entry current; defaults to `isSectionActive(pathname, href)`. */
  readonly isActive?: (pathname: string) => boolean
  /** Resolve the href in the browser: `lastBid` links Compliance to the bid last opened. */
  readonly resolveHref?: 'lastBid'
  /**
   * `developer` shows the entry only once `GET /dev/settings` has answered 200 for this
   * account (S4.6.2). The API is the gate — 403 off the developer list, 404 in production —
   * and the browser merely repeats its answer; see `lib/use-developer-access.ts`.
   */
  readonly access?: 'developer'
}

/** The workspace a bid was last opened in, so Compliance can lead back to it. */
export const LAST_BID_STORAGE_KEY = 'crossbid:last-bid'

const BID_WORKSPACE_PATH = /^\/bids\/(?!new$)[^/]+/

export const NAV_ITEMS: readonly NavItem[] = [
  { key: 'dashboard', href: '/dashboard', label: 'Dashboard', icon: 'grid', group: 'workflow' },
  {
    key: 'tenders',
    href: '/bids',
    label: 'Tenders',
    icon: 'file',
    group: 'workflow',
    isActive: (pathname) => pathname === '/bids' || pathname === '/bids/new',
  },
  {
    key: 'compliance',
    href: '/bids',
    label: 'Compliance',
    icon: 'fileCheck',
    group: 'workflow',
    resolveHref: 'lastBid',
    isActive: (pathname) => BID_WORKSPACE_PATH.test(pathname),
  },
  {
    key: 'certificates',
    href: '/certificates',
    label: 'Certificates',
    icon: 'layers',
    group: 'workflow',
  },
  {
    key: 'verdicts',
    href: '/verdicts',
    label: 'Verdicts',
    icon: 'shield',
    group: 'workflow',
    tone: 'solid',
  },
  {
    key: 'runs',
    href: '/runs',
    label: 'Agent runs',
    icon: 'spark',
    group: 'platform',
    access: 'developer',
  },
  {
    key: 'company',
    href: '/company',
    label: 'Company profile',
    icon: 'db',
    group: 'platform',
    trailing: true,
  },
  { key: 'settings', href: '/settings', label: 'Settings', icon: 'sliders', group: 'platform' },
] as const

export const NAV_GROUPS: readonly { readonly id: NavGroup; readonly label: string }[] = [
  { id: 'workflow', label: 'Workflow' },
  { id: 'platform', label: 'Platform' },
]

/** Anchor target of the skip link, and the `id` of the shell's `<main>`. */
export const MAIN_CONTENT_ID = 'main-content'

/**
 * Whether `href` is the section the given path sits in.
 *
 * Exact match, or a descendant path — `/company/documents` keeps "Company profile" current —
 * while `/companies` does not, because the separator is required.
 */
export function isSectionActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`)
}

/** Whether `item` is shown to an account whose developer access is `access`. */
export function isNavItemVisible(item: NavItem, access: DeveloperAccess): boolean {
  return item.access !== 'developer' || access === 'granted'
}

export function isNavItemActive(item: NavItem, pathname: string): boolean {
  return item.isActive === undefined
    ? isSectionActive(pathname, item.href)
    : item.isActive(pathname)
}
