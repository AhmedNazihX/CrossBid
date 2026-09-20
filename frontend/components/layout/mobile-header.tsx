'use client'

import { useState } from 'react'
import Image from 'next/image'
import Link from 'next/link'

import { Button } from '@/components/ui/button'
import { Icon } from '@/components/ui/icons'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet'
import { AccountBlock } from '@/components/auth/account-block'

import { AdvisoryNote } from './advisory-note'
import { NavGroups } from './nav-groups'

/**
 * The phone header of `WorkspacePhone.dc.html`: 56 px, white, 1 px rule below; the lockup
 * at 26 px; an "Analyse" primary button and a 44 px bordered menu button that opens the
 * navigation drawer. Shown below the `shell` breakpoint only.
 *
 * The drawer closes on navigation because the App Router keeps this component mounted
 * across a client-side route change.
 */
export function MobileHeader() {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <header className="flex h-14 items-center justify-between border-b border-border-default bg-surface-card pr-3 pl-4 shell:hidden">
      <Link href="/" className="inline-flex rounded-md" aria-label="CrossBid — home">
        <Image
          src="/logo-lockup.svg"
          alt="CrossBid"
          width={108}
          height={26}
          priority
          className="block h-[26px] w-auto"
        />
      </Link>
      <div className="flex gap-1.5">
        <Button asChild className="h-11">
          <Link href="/bids/new">
            <span className="inline-flex size-4">
              <Icon name="spark" size={16} />
            </span>
            Analyse
          </Link>
        </Button>
        <Sheet open={isOpen} onOpenChange={setIsOpen}>
          <SheetTrigger
            className="inline-flex size-11 items-center justify-center rounded-md border border-border-default bg-surface-card text-text-primary hover:bg-surface-hover"
            aria-label="Open navigation"
          >
            <Icon name="menu" size={20} />
          </SheetTrigger>
          <SheetContent className="px-5 py-7">
            <SheetTitle>CrossBid</SheetTitle>
            <SheetDescription>
              Go / no-go for EU tenders, with a citation for every line.
            </SheetDescription>
            <NavGroups onNavigate={() => setIsOpen(false)} />
            <div className="flex-1" />
            <div className="mt-6">
              <AdvisoryNote />
              <AccountBlock />
            </div>
          </SheetContent>
        </Sheet>
      </div>
    </header>
  )
}
