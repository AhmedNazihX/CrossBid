'use client'

import { useState } from 'react'
import { MenuIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet'
import { NavLink } from './nav-link'
import { NAV_ITEMS } from './nav-items'

/**
 * Phone-width navigation: the same `NAV_ITEMS`, in a stock shadcn/ui sheet.
 *
 * The sheet closes on navigation because the App Router keeps this component
 * mounted across a client-side route change.
 */
export function MobileNav() {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <Sheet open={isOpen} onOpenChange={setIsOpen}>
      <SheetTrigger asChild className="sm:hidden">
        <Button variant="outline" size="icon">
          <MenuIcon />
          <span className="sr-only">Open navigation</span>
        </Button>
      </SheetTrigger>
      <SheetContent side="right" className="gap-0">
        <SheetHeader>
          <SheetTitle>Crossbid</SheetTitle>
          <SheetDescription>Go/no-go qualification for EU tenders.</SheetDescription>
        </SheetHeader>
        <nav aria-label="Main" className="flex flex-col gap-1 px-4 pb-4">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.href}
              item={item}
              size="lg"
              className="justify-start"
              onNavigate={() => setIsOpen(false)}
            />
          ))}
        </nav>
      </SheetContent>
    </Sheet>
  )
}
