import Image from 'next/image'
import Link from 'next/link'

import { AccountBlock } from '@/components/auth/account-block'

import { AdvisoryNote } from './advisory-note'
import { NavGroups } from './nav-groups'

/**
 * The 260 px sidebar of `ui_kits/app/Shell.jsx` (`Sidebar`): canvas-coloured, 28 px × 20 px
 * padding, sticky for the viewport's height; the logo lockup at 30 px, then the WORKFLOW
 * and PLATFORM groups, then the advisory line where the kit shows the account. Hidden below
 * the `shell` breakpoint (900 px), where `MobileHeader` takes over.
 */
export function Sidebar() {
  return (
    <aside className="sticky top-0 hidden h-screen w-[var(--sidebar-width)] shrink-0 flex-col px-5 py-7 shell:flex">
      <div className="flex items-center px-2 py-1">
        <Link href="/" className="inline-flex rounded-md" aria-label="CrossBid — home">
          <Image
            src="/logo-lockup.svg"
            alt="CrossBid"
            width={124}
            height={30}
            priority
            className="block h-[30px] w-auto"
          />
        </Link>
      </div>
      <NavGroups />
      <div className="flex-1" />
      <AdvisoryNote />
      <AccountBlock />
    </aside>
  )
}
