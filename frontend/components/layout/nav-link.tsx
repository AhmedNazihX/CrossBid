'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { cn } from 'cn'

import { Button } from '@/components/ui/button'
import { isSectionActive, type NavItem } from './nav-items'

interface NavLinkProps {
  readonly item: NavItem
  readonly size?: React.ComponentProps<typeof Button>['size']
  readonly className?: string
  /** Called after the link is followed — the mobile sheet closes itself here. */
  readonly onNavigate?: () => void
}

/**
 * One navigation entry, shared by the desktop bar and the mobile sheet so the
 * two cannot disagree about which section is current.
 *
 * `aria-current="page"` is what a screen reader announces; the tinted background
 * is the sighted equivalent, so neither sense carries the state alone. The
 * focus ring comes from the stock shadcn/ui `Button`.
 */
export function NavLink({ item, size, className, onNavigate }: NavLinkProps) {
  const pathname = usePathname()
  const isActive = isSectionActive(pathname, item.href)

  return (
    <Button
      asChild
      size={size}
      variant={item.isPrimary ? 'default' : 'ghost'}
      className={cn(isActive && !item.isPrimary && 'bg-muted text-foreground', className)}
    >
      <Link href={item.href} aria-current={isActive ? 'page' : undefined} onClick={onNavigate}>
        {item.label}
      </Link>
    </Button>
  )
}
