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
import { NAV_LINKS, SIGN_IN_HREF, CONTACT_HREF } from './links'

/**
 * The sticky glass nav of `Landing.dc.html` (`Nav.jsx`): 68 px on the canvas colour at 80 %
 * behind `--blur-glass`, a 1 px subtle rule, the lockup at 30 px, five centred links at
 * 14 px medium with 28 px gaps, then "Sign in" (secondary, 32 px) and "Book a demo"
 * (inverse, 32 px).
 *
 * Below `lg` the link row collapses into a 44 px menu button that opens the app's phone
 * drawer (`sheet`) with the same five anchors and the two buttons at 44 px; between `sm`
 * and `lg` the two buttons stay in the bar. "Sign in" opens `/dashboard` for now — sign-in
 * itself is S4.1.1 (see `links.ts`).
 */
export function LandingNav() {
  const [isOpen, setIsOpen] = useState(false)
  const closeMenu = () => setIsOpen(false)

  return (
    <header className="sticky top-0 z-50 border-b border-border-subtle bg-surface-canvas/80 [backdrop-filter:var(--blur-glass)]">
      <div className="mx-auto flex h-[68px] w-full max-w-[var(--marketing-max)] items-center gap-8 px-6">
        <Link
          href="/"
          className="inline-flex min-h-11 shrink-0 items-center rounded-md"
          aria-label="CrossBid — home"
        >
          <Image
            src="/logo-lockup.svg"
            alt="CrossBid"
            width={124}
            height={30}
            priority
            className="block h-[30px] w-auto"
          />
        </Link>

        <nav aria-label="Primary" className="hidden flex-1 justify-center gap-7 lg:flex">
          {NAV_LINKS.map((link) => (
            <Link
              key={link.label}
              href={link.href}
              className="rounded-sm text-base font-medium leading-none text-text-secondary hover:text-text-primary"
            >
              {link.label}
            </Link>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-2 lg:ml-0">
          <Button
            asChild
            variant="secondary"
            size="sm"
            className="hidden hover:no-underline sm:inline-flex"
          >
            <Link href={SIGN_IN_HREF}>Sign in</Link>
          </Button>
          <Button
            asChild
            variant="inverse"
            size="sm"
            className="hidden hover:no-underline sm:inline-flex"
          >
            <Link href={CONTACT_HREF}>Book a demo</Link>
          </Button>

          <Sheet open={isOpen} onOpenChange={setIsOpen}>
            <SheetTrigger
              className="inline-flex size-11 items-center justify-center rounded-md border border-border-default bg-surface-card text-text-primary hover:bg-surface-hover lg:hidden"
              aria-label="Open menu"
            >
              <Icon name="menu" size={20} />
            </SheetTrigger>
            <SheetContent className="px-5 py-7">
              <SheetTitle>CrossBid</SheetTitle>
              <SheetDescription>
                Go / no-go for EU tenders, with a citation for every line.
              </SheetDescription>
              <nav aria-label="Primary" className="mt-6 flex flex-col">
                {NAV_LINKS.map((link) => (
                  <Link
                    key={link.label}
                    href={link.href}
                    onClick={closeMenu}
                    className="flex min-h-11 items-center rounded-md px-2.5 text-[length:var(--text-md)] font-medium text-text-primary hover:bg-surface-hover hover:no-underline"
                  >
                    {link.label}
                  </Link>
                ))}
              </nav>
              <div className="mt-6 flex flex-col gap-2">
                <Button
                  asChild
                  variant="secondary"
                  fullWidth
                  className="h-11 hover:no-underline"
                >
                  <Link href={SIGN_IN_HREF} onClick={closeMenu}>
                    Sign in
                  </Link>
                </Button>
                <Button asChild variant="inverse" fullWidth className="h-11 hover:no-underline">
                  <Link href={CONTACT_HREF} onClick={closeMenu}>
                    Book a demo
                  </Link>
                </Button>
              </div>
            </SheetContent>
          </Sheet>
        </div>
      </div>
    </header>
  )
}
