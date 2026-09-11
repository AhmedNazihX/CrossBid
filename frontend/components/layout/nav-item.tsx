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
  const href = useResolvedHref(item)
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
 */
function useResolvedHref(item: NavItem): string {
  const [href, setHref] = useState(item.href)
  useEffect(() => {
    if (item.resolveHref !== 'lastBid') {
      return
    }
    try {
      const lastBid = window.sessionStorage.getItem(LAST_BID_STORAGE_KEY)
      if (lastBid !== null && lastBid.length > 0) {
        setHref(`/bids/${encodeURIComponent(lastBid)}`)
      }
    } catch {
      // Storage can be unavailable (private mode, blocked site data); the fallback stands.
    }
  }, [item.resolveHref])
  return href
}
