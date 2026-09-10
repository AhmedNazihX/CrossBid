import { NavLink } from './nav-link'
import { NAV_ITEMS } from './nav-items'

/**
 * Desktop navigation. Hidden below `sm` — `display: none` also takes it out of
 * the accessibility tree, so the mobile sheet is never a duplicate landmark.
 */
export function MainNav() {
  return (
    <nav aria-label="Main" className="hidden items-center gap-1 sm:flex">
      {NAV_ITEMS.map((item) => (
        <NavLink key={item.href} item={item} />
      ))}
    </nav>
  )
}
