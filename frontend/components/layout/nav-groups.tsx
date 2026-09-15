'use client'

import { Eyebrow } from '@/components/ui/eyebrow'
import { useDeveloperAccess } from '@/lib/use-developer-access'
import { NavItemLink } from './nav-item'
import { NAV_GROUPS, NAV_ITEMS, isNavItemVisible } from './nav-items'

interface NavGroupsProps {
  readonly onNavigate?: () => void
}

/**
 * The two eyebrow groups of `Shell.jsx`'s sidebar — WORKFLOW, a 1 px rule, PLATFORM — each a
 * 4 px-gapped column of `NavItemLink`s. Shared by the desktop sidebar and the phone drawer.
 *
 * An entry marked `access: 'developer'` (Agent runs, the developer console of S4.6.2) is
 * listed only once the API has said this account may open it; until then, and for everyone
 * it refuses, the group renders without it.
 */
export function NavGroups({ onNavigate }: NavGroupsProps) {
  const access = useDeveloperAccess()
  return (
    <nav aria-label="Main" className="flex flex-col">
      {NAV_GROUPS.map((group, index) => (
        <div key={group.id}>
          {index > 0 && <div aria-hidden="true" className="mt-6 h-px bg-border-default" />}
          <Eyebrow className="mt-6 mb-2.5 px-2.5">{group.label}</Eyebrow>
          <ul className="m-0 flex list-none flex-col gap-1 p-0">
            {NAV_ITEMS.filter(
              (item) => item.group === group.id && isNavItemVisible(item, access)
            ).map((item) => (
              <li key={item.key}>
                <NavItemLink item={item} onNavigate={onNavigate} />
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  )
}
