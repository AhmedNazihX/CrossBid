'use client'

import { Eyebrow } from '@/components/ui/eyebrow'
import { NavItemLink } from './nav-item'
import { NAV_GROUPS, NAV_ITEMS } from './nav-items'

interface NavGroupsProps {
  readonly onNavigate?: () => void
}

/**
 * The two eyebrow groups of `Shell.jsx`'s sidebar — WORKFLOW, a 1 px rule, PLATFORM — each a
 * 4 px-gapped column of `NavItemLink`s. Shared by the desktop sidebar and the phone drawer.
 */
export function NavGroups({ onNavigate }: NavGroupsProps) {
  return (
    <nav aria-label="Main" className="flex flex-col">
      {NAV_GROUPS.map((group, index) => (
        <div key={group.id}>
          {index > 0 && <div aria-hidden="true" className="mt-6 h-px bg-border-default" />}
          <Eyebrow className="mt-6 mb-2.5 px-2.5">{group.label}</Eyebrow>
          <ul className="m-0 flex list-none flex-col gap-1 p-0">
            {NAV_ITEMS.filter((item) => item.group === group.id).map((item) => (
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
