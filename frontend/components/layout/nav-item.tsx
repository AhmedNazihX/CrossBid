'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { cn } from 'cn'

import { Icon } from '@/components/ui/icons'
import { isNavItemActive, LAST_BID_STORAGE_KEY, type NavItem } from './nav-items'

interface NavItemLinkProps {
  readonly item: NavItem
  /** Called after the link is followed — the phone drawer closes itself here. */
  readonly onNavigate?: () => void
}

/**
 * NavItem — `components/app/NavItem.jsx`: a 44 px row with a 32 px icon tile (10 px radius,
 * ink glyph on stone-100; the solid tone is the orange tile with a white glyph), a 15 px
 * medium label and an optional trailing chevron. The current entry sits on a white card with
 * a 1 px border and `--shadow-[var(--shadow-active-nav)]`; hover is `--surface-hover`.
 *
 * `aria-current="page"` is what a screen reader announces; the white card is the sighted
 * equivalent, so neither sense carries the state alone.
 */
export function NavItemLink({ item, onNavigate }: NavItemLinkProps) {
  const pathname = usePathname()
  const isActive = isNavItemActive(item, pathname)
  const href = useResolvedHref(item, pathname, isActive)
  const isSolid = item.tone === 'solid'

  return (
    <Link
      href={href}
      aria-current={isActive ? 'page' : undefined}
      onClick={onNavigate}
      className={cn(
        'flex h-11 w-full items-center gap-3 rounded-md border px-2.5 no-underline transition-colors [transition-duration:var(--duration-fast)] hover:no-underline',
        isActive
          ? 'border-border-default bg-surface-card shadow-[var(--shadow-active-nav)]'
          : 'border-transparent bg-transparent hover:bg-surface-hover'
      )}
    >
      <span
        className={cn(
          'inline-flex size-8 shrink-0 items-center justify-center rounded-[10px]',
          isSolid ? 'bg-surface-accent text-white' : 'bg-blue-100 text-blue-500'
        )}
      >
        <Icon name={item.icon} size={18} />
      </span>
      <span className="flex-1 text-[length:var(--text-md)] font-medium leading-none text-text-primary">
        {item.label}
      </span>
      {item.trailing === true && (
        <span className="inline-flex text-text-muted">
          <Icon name="chev" size={16} />
        </span>
      )}
    </Link>
  )
}

/**
 * Compliance leads to the bid last opened in this tab; before any bid was opened it falls
 * back to the tender list. Read after mount, so server and first client render agree.
 *
 * **Re-read on every navigation, not once.** The `(app)` layout keeps the sidebar mounted
 * across every client-side route change, so an effect keyed on `item.resolveHref` — a module
 * constant — ran exactly once, before any bid had been opened, and the entry pointed at
 * `/bids` (or at the bid of an earlier load) until a hard reload (M9 of the 2026-09-15
 * audit). ADR-0060 defends this entry as "resolves to the last-opened bid"; keying the read
 * on `pathname` is what makes that true. It is the same stale-state class ADR-0042 fixed in
 * `RequireCompany`: a layout that never remounts needs its effects to depend on what changes.
 *
 * **On a workspace the entry is the page you are on.** The workspace writes the key in its
 * own effect (`bid-workspace.tsx`), and React runs passive effects in tree order — the
 * sidebar's before `<main>`'s — so on the very commit that opens a bid this hook would still
 * read the *previous* value. `isActive` is true exactly when `pathname` is a bid workspace,
 * and then the pathname is the answer with no storage read at all.
 */
function useResolvedHref(item: NavItem, pathname: string, isActive: boolean): string {
  const [href, setHref] = useState(item.href)
  useEffect(() => {
    if (item.resolveHref !== 'lastBid') {
      return
    }
    setHref(isActive ? pathname : (readLastBidHref() ?? item.href))
  }, [item.resolveHref, item.href, pathname, isActive])
  return href
}

/** The stored bid's workspace path; `undefined` when nothing is stored or storage is unavailable. */
function readLastBidHref(): string | undefined {
  try {
    const lastBid = window.sessionStorage.getItem(LAST_BID_STORAGE_KEY)
    return lastBid !== null && lastBid.length > 0
      ? `/bids/${encodeURIComponent(lastBid)}`
      : undefined
  } catch {
    // Storage can be unavailable (private mode, blocked site data); the fallback stands.
    return undefined
  }
}
